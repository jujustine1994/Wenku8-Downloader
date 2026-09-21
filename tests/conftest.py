import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


@pytest.fixture(autouse=True)
def _disable_request_pacing(monkeypatch):
    """測試一律不做送出節流，否則每個請求都會真的睡 REQUEST_INTERVAL 秒。

    2026-09-21 加入節流閘（src/ratelimit.py）後，`run_download_all()` 會在批次
    開始時 `reset_limiter()`，預設間隔 2.5 秒。不關掉的話光是既有的 downloader
    測試就要跑好幾分鐘。

    節流本身的行為由 `tests/test_ratelimit.py` 用注入的假時鐘驗證，不靠真的睡。
    """
    from src import downloader
    monkeypatch.setattr(downloader, "REQUEST_INTERVAL", 0.0)
    downloader.reset_limiter(0.0)
