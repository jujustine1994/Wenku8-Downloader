"""i18n.py — 介面顯示文字的多語言查表。

用法：
    from src.i18n import t
    ttk.Button(text=t("gui.btn.load"))

啟動時呼叫一次 set_lang(cfg["language"])，之後全程式共用。

## 設計約束（改這個檔前先讀）

1. **t() 永不 raise、永不回空字串。** 查找順序是
   `目標語言 → 母語言 → key 本身`。最壞情況畫面顯示 `gui.btn.load` 這串
   key，一眼看得出哪裡漏翻；回空字串會變成看不見的按鈕，那才是災難。

2. **機器鍵不進這裡。** 會被寫進檔案、或拿去跟檔案裡的值比對的字串是
   **資料**不是介面文字。本專案的例子（一律不翻，見 src/sitedata.py）：
   - 從 wenku8 解析出來的書名／卷名／作者
   - 「外傳」檔名前綴、卷名分類用的簡體比對關鍵字、正卷判斷正規表達式
   - 檔名樣板、輸出目錄、config.json 裡存的代號

3. **log 檔不吃這裡的翻譯。** log 是給維護者除錯用的，跟著使用者語言變
   等於自廢。落檔字串一律走 src/logtext.py 的 LOG_TEXT（固定繁中）。
"""

from __future__ import annotations

import importlib

# (代號, 下拉選單顯示名, 字型)
#
# 代號     存進 .tool_config.json 的值，也是 src/locales/<代號>.py 的檔名
# 顯示名   用各語言自己的說法，任何語言下使用者都認得出哪個是哪個
# 字型     本專案介面字型統一寫死 Microsoft JhengHei（既有行為），這一欄
#          目前不被任何程式碼讀取，保留只為與 pattern_i18n.py 的表格形狀一致。
#          真的要跟著語言換字型時再啟用 ui_font()——換字型會改變繁中的既有
#          外觀，違反「繁中行為完全一樣」。
LANGUAGES: list[tuple[str, str, str]] = [
    ("zh_tw", "繁體中文", "Microsoft JhengHei"),
    ("zh_cn", "简体中文", "Microsoft YaHei"),
    ("en",    "English",  "Calibri"),
    ("ja",    "日本語",   "Yu Gothic"),
]

DEFAULT_LANG = "zh_tw"

# 找不到 key 時的最終退路。母語言是其他語言的翻譯來源，所以它一定最完整。
FALLBACK_LANG = "zh_tw"

_LANG_CODES = [code for code, _, _ in LANGUAGES]
_current_lang: str = DEFAULT_LANG
_cache: dict[str, dict[str, str]] = {}


def _strings(lang: str) -> dict[str, str]:
    """載入某語言的字串表。載入失敗回空 dict，讓 t() 自己退回 fallback。"""
    if lang in _cache:
        return _cache[lang]
    try:
        mod = importlib.import_module(f"src.locales.{lang}")
        table = getattr(mod, "STRINGS", {})
    except (ImportError, AttributeError):
        # 語言檔缺失或壞掉不能讓整個程式起不來
        table = {}
    _cache[lang] = table
    return table


def available_languages() -> list[tuple[str, str]]:
    """給選單用：[(代號, 顯示名), ...]，順序即選單順序。"""
    return [(code, name) for code, name, _ in LANGUAGES]


def is_supported(lang: str) -> bool:
    return lang in _LANG_CODES


def set_lang(lang: str | None) -> str:
    """設定目前語言。不認得的代號（含 None、舊 config 的怪值）退回預設。

    回傳實際採用的代號——要顯示「現在是什麼語言」時用回傳值，不要用傳進去
    的參數，兩者在退回時不同。
    """
    global _current_lang
    _current_lang = lang if is_supported(lang or "") else DEFAULT_LANG
    return _current_lang


def get_lang() -> str:
    return _current_lang


def ui_font(lang: str | None = None) -> str:
    """該語言的字型。目前刻意不被呼叫，見 LANGUAGES 的註解。"""
    target = lang if is_supported(lang or "") else _current_lang
    for code, _, font in LANGUAGES:
        if code == target:
            return font
    return LANGUAGES[0][2]


def t(key: str, **fmt) -> str:
    """查表。目標語言 → 母語言 → key 本身。

    **fmt 走 str.format，給帶變數的訊息用：
        t("gui.status.loaded", book="轉生史萊姆", n=12)

    格式化失敗（譯文的 placeholder 打錯）不 raise，回未格式化的原字串——
    畫面上看到 {book} 殘留，比整個程式當掉好處理。
    """
    s = _strings(_current_lang).get(key)
    if s is None:
        s = _strings(FALLBACK_LANG).get(key)
    if s is None:
        return key
    if not fmt:
        return s
    try:
        return s.format(**fmt)
    except (KeyError, IndexError, ValueError):
        return s
