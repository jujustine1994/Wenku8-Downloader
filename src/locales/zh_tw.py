"""locales/zh_tw.py — 繁體中文（母表）

改這裡的譯文不影響任何邏輯：程式一律用 key 比對。改錯最壞的情況只是
畫面顯示怪怪的。

⚠ 這裡只放**顯示在畫面上**的字。會落進檔名／檔案內容、或拿去跟網站抓下來
的文字比對的字串，一律在 src/sitedata.py，不進這張表。
"""

from __future__ import annotations

STRINGS: dict[str, str] = {
    # ── 設定分頁 ──
    "gui.settings.appearance": "外觀",
}
