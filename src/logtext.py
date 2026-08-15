"""logtext.py — 落進 logs/app.log 的字串，**固定繁體中文**。

跟 src/i18n.py 是刻意分開的兩套：

- i18n.STRINGS  給使用者看的介面文字，跟著使用者選的語言走
- logtext.LOG_TEXT  給維護者看的執行紀錄，永遠繁中

log 跟著使用者語言變，等於自廢——使用者回報問題時附上的 log 你自己看不懂。
所以同一條訊息若同時要推 UI 又要落檔，UI 那條走 t()、落檔那條走這裡，
不共用字串。

帶變數一律用**具名** placeholder（{book} 而不是 {0}）。
"""

from __future__ import annotations

LOG_TEXT: dict[str, str] = {
    # ── 任務起始行（=== 行，唯一有完整日期的行）──
    "hdr.download": "下載 {book} | {total}卷 | retry:{retry}",
    "hdr.repair":   "修復 {book} | {total}卷 | retry:{retry}",

    # ── 任務結束行 ──
    "result.ok":      "成功 {success}/{total} 卷",
    "result.partial": "成功 {success}/{total} 卷，失敗 {failed} 卷",
    "result.elapsed": "{result}，耗時 {minutes}分{seconds}秒",

    # ── 錯誤行：只記 exception 類型 + HTTP status code + 重試次數 ──
    # 絕不記 URL / response 全文 / f"...{e}"（見 windows-tool.md「錯誤行怎麼寫」）
    "err.fetch":   "vid={vid} charset={charset} -> {etype}: HTTP {status} | 重試 {retry}",
    "err.volume":  "{book} {index} -> {etype}: HTTP {status}",
    "err.catalog": "載入目錄 aid={aid} -> {etype}: HTTP {status}",

    # 重試次數欄位在無限重試模式下的寫法
    "retry.infinite": "無限次",
}


def log_t(key: str, **fmt) -> str:
    """查 LOG_TEXT。跟 i18n.t() 一樣永不 raise，查不到回 key 本身。"""
    s = LOG_TEXT.get(key)
    if s is None:
        return key
    if not fmt:
        return s
    try:
        return s.format(**fmt)
    except (KeyError, IndexError, ValueError):
        return s
