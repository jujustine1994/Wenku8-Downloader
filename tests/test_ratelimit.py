"""ratelimit.py 的單元測試。

時鐘與 sleep 都是注入的，所以測試不會真的睡——整份跑完是毫秒級。
"""

import threading

import pytest

from src.ratelimit import (
    RateLimiter,
    parse_retry_after,
    retry_after_from,
    MAX_RETRY_AFTER,
)


class FakeClock:
    """可控時鐘：sleep 只是把時間往前推。"""

    def __init__(self):
        self.now = 1000.0
        self.slept = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        self.slept += seconds


def _limiter(interval=2.5, **kw):
    clock = FakeClock()
    return RateLimiter(interval, sleep=clock.sleep, clock=clock.time, **kw), clock


# ── 基礎間隔 ──

def test_first_request_goes_out_immediately():
    lim, clock = _limiter()
    assert lim.wait() is True
    assert clock.slept == 0


def test_interval_enforced_between_requests():
    lim, clock = _limiter(interval=2.5)
    lim.wait()
    lim.ok()
    lim.wait()
    assert clock.slept == pytest.approx(2.5, abs=0.25)


def test_zero_interval_never_sleeps():
    lim, clock = _limiter(interval=0)
    for _ in range(5):
        lim.wait()
        lim.ok()
    assert clock.slept == 0


# ── 429 退避 ──

def test_throttle_applies_minimum_penalty():
    lim, clock = _limiter(interval=2.5, min_penalty=5.0)
    lim.wait()
    lim.throttled()
    assert lim.penalty == 5.0
    lim.wait()
    # 間隔 + 懲罰
    assert clock.slept == pytest.approx(7.5, abs=0.25)


def test_penalty_doubles_on_repeated_throttling():
    lim, _ = _limiter(min_penalty=5.0, max_penalty=60.0)
    seen = []
    for _ in range(5):
        lim.throttled()
        seen.append(lim.penalty)
    assert seen == [5.0, 10.0, 20.0, 40.0, 60.0]


def test_penalty_caps_at_max():
    lim, _ = _limiter(min_penalty=5.0, max_penalty=60.0)
    for _ in range(20):
        lim.throttled()
    assert lim.penalty == 60.0


def test_penalty_decays_on_success():
    lim, _ = _limiter(min_penalty=8.0)
    lim.throttled()
    assert lim.penalty == 8.0
    lim.ok()
    assert lim.penalty == 4.0
    lim.ok()
    assert lim.penalty == 2.0


def test_penalty_reaches_zero_eventually():
    lim, _ = _limiter(min_penalty=8.0)
    lim.throttled()
    for _ in range(10):
        lim.ok()
    assert lim.penalty == 0.0


def test_retry_after_overrides_exponential_backoff():
    lim, _ = _limiter(min_penalty=5.0)
    lim.throttled(retry_after=42)
    assert lim.penalty == 42


def test_retry_after_is_capped():
    """伺服器叫我們睡一小時也不照做。"""
    lim, _ = _limiter()
    lim.throttled(retry_after=99999)
    assert lim.penalty == MAX_RETRY_AFTER


# ── 非限流失敗 ──

def test_other_failure_does_not_change_penalty():
    """網路不穩不該被誤當成限流而越退越久，也不該衰減既有懲罰。"""
    lim, _ = _limiter(min_penalty=8.0)
    lim.throttled()
    lim.failed()
    assert lim.penalty == 8.0


def test_other_failure_still_schedules_next_slot():
    lim, clock = _limiter(interval=2.5)
    lim.wait()
    lim.failed()
    lim.wait()
    assert clock.slept == pytest.approx(2.5, abs=0.25)


# ── 跳過 ──

def test_wait_returns_false_when_skip_event_already_set():
    lim, clock = _limiter(interval=10)
    ev = threading.Event()
    ev.set()
    assert lim.wait(ev) is False
    assert clock.slept == 0


def test_long_backoff_can_be_interrupted_by_skip():
    """被限流要等 60 秒時，按「跳過目前卷」必須馬上有反應，
    不能卡在一個長 sleep 裡。"""
    clock = FakeClock()
    ev = threading.Event()
    calls = {"n": 0}

    def sleep(seconds):
        calls["n"] += 1
        clock.sleep(seconds)
        if calls["n"] == 3:      # 睡到第三段時使用者按了跳過
            ev.set()

    lim = RateLimiter(2.5, sleep=sleep, clock=clock.time)
    lim.throttled(retry_after=60)
    assert lim.wait(ev) is False
    # 分段睡眠：沒有一次睡掉整個 62.5 秒
    assert clock.slept < 5


# ── Retry-After 解析 ──

@pytest.mark.parametrize("value,expected", [
    ("30", 30.0),
    (" 12 ", 12.0),
    (7, 7.0),
    ("2.5", 2.5),
])
def test_parse_retry_after_accepts_seconds(value, expected):
    assert parse_retry_after(value) == expected


@pytest.mark.parametrize("value", [
    None, "", "不是數字", "Wed, 21 Oct 2026 07:28:00 GMT", "0", "-5",
])
def test_parse_retry_after_rejects_everything_else(value):
    """HTTP-date 格式不解析——拿不到就走指數退避，不值得為此拖進日期處理。
    解析不出來一律回 None，絕不 raise。"""
    assert parse_retry_after(value) is None


def test_retry_after_from_response():
    class Resp:
        headers = {"Retry-After": "15"}
    assert retry_after_from(Resp()) == 15.0


def test_retry_after_from_response_without_header():
    class Resp:
        headers = {}
    assert retry_after_from(Resp()) is None


def test_retry_after_from_none_response():
    assert retry_after_from(None) is None


def test_retry_after_from_broken_response_does_not_raise():
    class Resp:
        @property
        def headers(self):
            raise RuntimeError("boom")
    assert retry_after_from(Resp()) is None


# ── 預算：60 卷要落在 5 分鐘內 ──

def test_sixty_requests_fit_in_five_minutes_when_not_throttled():
    """使用者可接受的標準：60 檔 / 5 分鐘。

    這裡只算閘門本身的開銷（不含實際抓取時間），確認節流設定沒有把預算吃光。
    """
    lim, clock = _limiter(interval=2.5)
    for _ in range(60):
        lim.wait()
        lim.ok()
    assert clock.slept <= 150      # 60 × 2.5 = 150 秒，剩 150 秒給實際抓取
