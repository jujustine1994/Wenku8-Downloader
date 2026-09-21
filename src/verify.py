"""verify.py — 單卷檔案的完整性判定。

純函式，沒有網路與 UI 依賴。`downloader`（下載完驗收）與 `main`（更新流程
重驗）兩邊都用這裡。

## 為什麼不是只看亂碼

原本的驗收只有 `check_garbled()`：能不能用 UTF-8 讀、含不含 `�`。伺服器回
HTTP 200 但內容不完整時，檔案是合法 UTF-8、也沒有 `�`，一律判定成功。
（真正的傳輸中斷 curl 多半直接拋例外，已被 downloader 的 retry 接住，
不是這裡要解的問題。）

判定改用**目錄頁的章節標題當錨點**：完整的卷，每個章節標題都會出現在 txt 裡；
斷檔的卷，後半段的標題會整批消失。

## 門檻的由來（2026-09-21 實測 aid=1861 第 1／21／57 卷）

- 標題原樣出現在 txt（縮排兩個全形空格），第 1 卷 9/9、第 57 卷 7/7 命中
- **標點會對不上**：第 21 卷有一章目錄與 txt 用了不同的間隔符號，全等比對
  誤判缺章，但該卷實際完整（153,309 字／8,193 行）→ 所以要先 `normalize()`
- **短標題會誤命中**：2 字標題（插圖、後記之類）會命中正文裡的同字，
  第 21 卷該章命中在第 862 行而非檔尾 → 所以只有長度 ≥ 4 的標題能當錨點
- 完整檔的最後錨點位置：第 1 卷 99.2%、第 57 卷 99.6%、第 21 卷 70.0%
  → `ANCHOR_TAIL_POSITION = 0.5` 對完整檔有充足餘裕

⚠ `NORMALIZE_MAP` 裡的符號是**拿去跟網站抓下來的內容比對的資料**，性質同
`src/sitedata.py`，永遠不翻譯、不「順手改成繁體」。動了就會靜默誤判。
"""

from __future__ import annotations

# 錨點門檻。改這些數字前先看上面「門檻的由來」。
ANCHOR_MIN_LEN = 4          # 正規化後短於此的章節標題不當錨點（會誤命中正文）
ANCHOR_MIN_COUNT = 3        # 錨點少於這個數量就不採信，改走字數判定（理由見下）
ANCHOR_HIT_RATIO = 0.8      # 錨點命中率門檻
ANCHOR_TAIL_POSITION = 0.5  # 最後一個命中錨點必須落在檔案後半

# ANCHOR_MIN_COUNT 的由來（2026-09-21 實測 aid=1832 艾梅洛閣下II世事件簿）：
# 那本書的章節標題全是「序章 / 第一章 / 終章 / 後記 / 插圖」這種 2–3 字的光禿
# 標題，85 章裡只有 2 個 >= 4 字。第一卷因此只剩 1 個錨點「主要人物」——那是書
# 最前面的人物介紹頁，命中在檔案 0% 的位置，tail 測試就判定「後半段標題整批
# 消失」＝斷檔。但檔案是完整的 155,614 字。
#
# 教訓：**1–2 個錨點的位置資訊沒有意義**，拿它判斷檔案結不結尾等於擲骰子。
# 錨點不足就誠實承認沒有證據，退回字數判定，不要用薄弱證據下強結論。

# 錨點不足（全短標題卷、單章卷）時退回字數判定
FALLBACK_CHARS_RATIO = 0.2   # 同書已完成卷字數中位數的比例
FALLBACK_CHARS_FLOOR = 3000  # 絕對下限，median 算不出來時只用這個

GARBLED_CHAR = "�"

# 正規化對照表：同義符號統一成單一字元。比對前標題與內文都過這張表。
NORMALIZE_MAP = {
    # 間隔號（實測踩到的那一類）
    "•": "·", "・": "·", "‧": "·", "∙": "·", "⋅": "·", "･": "·", "●": "·",
    # 引號／括號
    "『": "「", "』": "」",
    "〖": "【", "〗": "】",
    "（": "(", "）": ")",
    "［": "[", "］": "]",
    "〈": "《", "〉": "》",
    # 破折號與連字號
    "—": "-", "–": "-", "─": "-", "－": "-", "～": "~",
}

_WHITESPACE = " \t\r\n　\xa0   "


def normalize(text: str) -> str:
    """去掉所有空白、把同義符號收斂成單一字元。標題與內文都走這個再比對。"""
    out = []
    for ch in text:
        if ch in _WHITESPACE:
            continue
        out.append(NORMALIZE_MAP.get(ch, ch))
    return "".join(out)


def _anchor_titles(chapters: list[dict]) -> list[str]:
    """正規化後長度 >= ANCHOR_MIN_LEN 的章節標題。短標題排除，會誤命中正文。"""
    seen: set[str] = set()
    anchors = []
    for c in chapters or []:
        title = normalize(c.get("title", ""))
        if len(title) < ANCHOR_MIN_LEN or title in seen:
            continue
        seen.add(title)
        anchors.append(title)
    return anchors


def _to_traditional(titles: list[str]) -> list[str]:
    """把章節標題轉繁，用來比對已經轉過繁的磁碟檔案。

    轉標題比轉全文便宜得多。OpenCC 載不起來時回原值——驗證退化成比較不準，
    但不該讓整個流程掛掉。
    """
    try:
        from src.converter import convert_to_traditional
        return [normalize(convert_to_traditional(s)) for s in titles]
    except Exception:
        return titles


def _match(norm_text: str, anchors: list[str]) -> tuple[int, float]:
    """回傳 (命中數, 最後一個命中錨點的位置比例)。"""
    if not norm_text:
        return 0, 0.0
    positions = []
    for a in anchors:
        pos = norm_text.find(a)
        if pos >= 0:
            positions.append(pos)
    if not positions:
        return 0, 0.0
    # 取最大位置而非「清單最後一個」：少數標題可能在正文被提前命中，
    # 取最大值對「後半段整批消失」這個真正要抓的樣態更穩。
    return len(positions), max(positions) / len(norm_text)


def verify_volume(text: str, chapters: list[dict] | None = None,
                  median_chars: int | None = None,
                  script: str | None = None) -> dict:
    """判定一卷的內容完整性。

    script 說明 text 目前是什麼字體，決定章節標題（一律簡體原文）要不要先轉繁：
        "zh-hans" / None  → 標題直接比
        "zh-hant"         → 標題轉繁再比
        "unknown"         → 兩種都試，取命中多的那種（回推來的舊檔用）

    回傳 dict，status 為 "complete" / "suspect" / "garbled"。
    reason 是機器可讀代號（"anchor_ratio" / "anchor_tail" / "too_short"），
    不是給人看的句子——要顯示時由呼叫端自己查表翻譯。
    """
    chars = len(text)
    result = {
        "status": "complete",
        "chars": chars,
        "anchor_total": 0,
        "anchor_hits": 0,
        "tail_position": 0.0,
        "reason": "",
    }

    if GARBLED_CHAR in text:
        result["status"] = "garbled"
        result["reason"] = "garbled"
        return result

    norm_text = normalize(text)
    anchors = _anchor_titles(chapters or [])

    if len(anchors) >= ANCHOR_MIN_COUNT:
        candidates = []
        if script == "zh-hant":
            candidates.append(_to_traditional(anchors))
        elif script == "unknown":
            candidates.append(anchors)
            candidates.append(_to_traditional(anchors))
        else:
            candidates.append(anchors)

        best_hits, best_tail = 0, 0.0
        for cand in candidates:
            hits, tail = _match(norm_text, cand)
            if hits > best_hits:
                best_hits, best_tail = hits, tail

        result["anchor_total"] = len(anchors)
        result["anchor_hits"] = best_hits
        result["tail_position"] = round(best_tail, 4)
        ratio = best_hits / len(anchors)
        if ratio < ANCHOR_HIT_RATIO:
            result["status"] = "suspect"
            result["reason"] = "anchor_ratio"
        elif best_tail < ANCHOR_TAIL_POSITION:
            result["status"] = "suspect"
            result["reason"] = "anchor_tail"
        return result

    # 錨點不足（< ANCHOR_MIN_COUNT）：沒有足夠證據，退回字數判定
    threshold = FALLBACK_CHARS_FLOOR
    if median_chars:
        threshold = max(int(median_chars * FALLBACK_CHARS_RATIO), FALLBACK_CHARS_FLOOR)
    if chars < threshold:
        result["status"] = "suspect"
        result["reason"] = "too_short"
    return result


def verify_file(filepath: str, chapters: list[dict] | None = None,
                median_chars: int | None = None,
                script: str | None = None) -> dict | None:
    """讀檔後跑 verify_volume()。讀不到回 None，讓呼叫端自己決定怎麼歸類。

    用 errors="replace" 開檔：非 UTF-8 的舊檔會解出 `�`，正好被判成 garbled，
    跟 downloader.check_garbled() 對非 UTF-8 檔案的既有語意一致。
    """
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    return verify_volume(text, chapters, median_chars, script)
