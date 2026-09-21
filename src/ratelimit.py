"""ratelimit.py — 整批共用的送出節流閘。

## 為什麼需要

2026-09-21 從 `logs/app.log` 確認：一次 57 卷的下載任務裡出現 **115 次
HTTP 429**（Too Many Requests）。手動下載從來不會遇到，因為人工點擊之間隔
了幾秒到幾分鐘；工具是連續打——57 卷約 3 分鐘跑完，而 `run_download_all()`
卷與卷之間**完全沒有延遲**。

而且原本的重試讓情況更糟：`_fetch_bytes()` 對所有例外一視同仁，固定睡
`retry_delay`（預設 2 秒）就重試。對 429 來說 2 秒遠遠不夠，等於持續敲門
讓限流一直續命；無限重試模式下可以看到同一個 vid 每 2 秒撞一次 429。

## 為什麼是「閘門」而不是「每卷 sleep」

一卷不只發一次請求：`_fetch_best_text()` 抓到亂碼會再抓一次 GBK 版本，
修復流程還會重抓。每卷插 sleep 管得到卷、管不到卷內那幾次。

更重要的是**限流是全域的，退避也必須是全域的**。原本每一卷各自燒掉自己的
retry 次數去撞同一道牆，撞完標記失敗進修復清單，修復流程再撞一次。所有請求
共用同一道閘門後，一次 429 就讓整批慢下來，這才是對的形狀。

## 測試

`sleep` 與 `clock` 都可以注入，測試不會真的睡。見 `tests/test_ratelimit.py`。
"""

from __future__ import annotations

import threading
import time

# 每次送出之間的基礎間隔（秒）。使用者可在「設定」調整。
#
# 預算依據：使用者可接受 60 檔 / 5 分鐘 = 每卷 5 秒。單卷抓取約 1.5–2.5 秒，
# 所以 2.5 秒的閘門間隔讓 60 卷落在 240–300 秒，壓在預算內還留一點餘裕。
# 被限流時會超過 5 分鐘，但那符合「成功優先、慢一點可接受」的排序。
DEFAULT_INTERVAL = 2.5

# 收到 429 後的額外等待（秒）。第一次至少停這麼久，之後每次翻倍到上限為止。
MIN_PENALTY = 5.0
MAX_PENALTY = 60.0

# 伺服器給的 Retry-After 也要設上限，避免它叫我們睡一小時
MAX_RETRY_AFTER = 300.0

# wait() 的分段睡眠長度。不一次睡到底才能及時回應「跳過目前卷」。
_TICK = 0.2


class RateLimiter:
    """送出節流閘。所有請求送出前先 `wait()`，結束後回報 `ok()` / `throttled()`。

    狀態只有兩個：
      _next_at  下一次可以送出的時間點（monotonic）
      _penalty  429 造成的額外等待，成功就衰減、再被擋就翻倍
    """

    def __init__(self, interval: float = DEFAULT_INTERVAL,
                 min_penalty: float = MIN_PENALTY,
                 max_penalty: float = MAX_PENALTY,
                 sleep=time.sleep, clock=time.monotonic):
        self.interval = max(0.0, float(interval))
        self.min_penalty = min_penalty
        self.max_penalty = max_penalty
        self._sleep = sleep
        self._clock = clock
        self._penalty = 0.0
        self._next_at = 0.0
        self._lock = threading.Lock()

    # ---- 狀態查詢（給 UI / 測試用）----

    @property
    def penalty(self) -> float:
        return self._penalty

    def delay_now(self) -> float:
        """還要等幾秒才能送出。已經可以送出時回 0。"""
        return max(0.0, self._next_at - self._clock())

    # ---- 主流程 ----

    def wait(self, skip_event=None) -> bool:
        """睡到可以送出為止。回傳 False 代表等待期間被 skip_event 打斷。

        分段睡眠而不是一次睡到底：被限流時可能要等 60 秒，使用者按「跳過
        目前卷」應該要馬上有反應，不能卡在一個長 sleep 裡。
        """
        while True:
            if skip_event is not None and skip_event.is_set():
                return False
            remaining = self.delay_now()
            if remaining <= 0:
                return True
            self._sleep(min(_TICK, remaining))

    def ok(self) -> None:
        """請求成功。懲罰減半衰減，並排下一次可送出時間。"""
        with self._lock:
            self._penalty = 0.0 if self._penalty < 1.0 else self._penalty / 2
            self._schedule()

    def failed(self) -> None:
        """非限流的失敗（連線錯誤之類）。不加懲罰，但一樣要排下一次。

        跟 ok() 分開是因為這種失敗不代表我們打太快，不該衰減懲罰；
        也不該加重，否則網路不穩會被誤當成限流而越退越久。
        """
        with self._lock:
            self._schedule()

    def throttled(self, retry_after: float | None = None) -> None:
        """被限流（HTTP 429）。伺服器有講 Retry-After 就照它，否則指數退避。"""
        with self._lock:
            if retry_after is not None and retry_after > 0:
                self._penalty = min(float(retry_after), MAX_RETRY_AFTER)
            else:
                doubled = self._penalty * 2 if self._penalty else 0.0
                self._penalty = min(max(doubled, self.min_penalty),
                                    self.max_penalty)
            self._schedule()

    def _schedule(self) -> None:
        self._next_at = self._clock() + self.interval + self._penalty


def parse_retry_after(value) -> float | None:
    """把 Retry-After header 轉成秒數。

    HTTP 規格允許兩種格式：秒數，或 HTTP-date。這裡只解析秒數——wenku8 若給
    的是日期格式，回 None 讓呼叫端走指數退避就好，不值得為此拖進日期解析。
    解析不出來一律回 None，絕不 raise。
    """
    if value is None:
        return None
    try:
        seconds = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return seconds if seconds > 0 else None


def retry_after_from(resp) -> float | None:
    """從 response 取 Retry-After。拿不到就回 None（header 缺失是常態，不是錯誤）。"""
    if resp is None:
        return None
    try:
        headers = resp.headers
    except Exception:
        return None
    for key in ("Retry-After", "retry-after"):
        try:
            if key in headers:
                return parse_retry_after(headers[key])
        except Exception:
            continue
    try:
        return parse_retry_after(headers.get("Retry-After"))
    except Exception:
        return None
