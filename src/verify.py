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

## 樣本限制（動判定邏輯前務必先讀）

所有觀察到的規律都只來自 **aid=1861 與 1832 兩本書**。每本小說的卷名、章節
標題命名習慣本來就可能不同，站方版型也會改。所以這個模組的設計原則是：

**任何「格式假設」都只能當候選，不能當必要條件。** 兩組錨點（純標題、卷名＋
標題）並列計算、取命中高的那組，格式對不上的書會自動落到另一組或字數判定，
而不是被判成斷檔。薄弱證據只能用來「確認完整」，不能用來「宣告損壞」——
誤判損壞的代價是使用者整套重抓，比漏掉一個斷檔嚴重得多。

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


def _anchor_titles(chapters: list[dict], convert=None) -> list[str]:
    """純標題錨點：正規化後長度 >= ANCHOR_MIN_LEN 的章節標題。

    短標題排除，它們會誤命中正文。這組跟 `_composite_anchors()` **並列當候選**，
    由 `verify_volume()` 取命中高的那組，沒有誰優先——哪一組適用取決於那本書
    的命名格式，而我們的樣本不足以斷定哪種格式比較常見。
    """
    conv = convert or (lambda s: s)
    seen: set[str] = set()
    anchors = []
    for c in chapters or []:
        title = normalize(conv(c.get("title", "")))
        if len(title) < ANCHOR_MIN_LEN or title in seen:
            continue
        seen.add(title)
        anchors.append(title)
    return anchors


def _composite_anchors(chapters: list[dict], volume_name: str,
                       convert=None) -> list[str]:
    """複合錨點：卷名 + 章節標題。**只是候選之一，不是格式定律。**

    2026-09-21 在 aid=1832 與 1861 觀察到章節標題行長這樣：

        　　{卷名} {章節標題}

    標題行前綴了卷名，所以把兩者接起來當錨點，「序章」這種 2 字標題也會變成
    十幾字的獨特字串，短標題誤命中正文的問題就消失了。實測命中率：aid=1832
    第 1／5／10 卷、aid=1861 第 1 卷全部 100%，零重複命中。

    ⚠ **樣本只有兩本書，不可以當成所有小說都成立。** 每本書的命名習慣不同，
    站方版型也會改。所以 verify_volume() 把這組跟純標題錨點**並列當候選**，
    取命中高的那組，而不是寫死一定用複合錨點——格式對不上的書如果被強制用
    這組判定，完好的檔案會被判成斷檔。

    拿不到卷名就回空 list，呼叫端自然會用另一組，這不是錯誤狀態。
    """
    conv = convert or (lambda s: s)
    vol = normalize(conv(volume_name or ""))
    if not vol:
        return []
    seen: set[str] = set()
    anchors = []
    for c in chapters or []:
        title = normalize(conv(c.get("title", "")))
        if not title:
            continue
        comp = vol + title
        if comp in seen:
            continue
        seen.add(comp)
        anchors.append(comp)
    return anchors


def _to_traditional(s: str) -> str:
    """把單一標題/卷名轉繁，用來比對已經轉過繁的磁碟檔案。

    轉標題比轉全文便宜得多。OpenCC 載不起來時回原值——驗證退化成比較不準，
    但不該讓整個流程掛掉。

    轉換要在**組合成錨點之前**對每一段各自做：先接起來再轉，OpenCC 會把
    「卷名尾字＋標題首字」當成一個詞去查詞庫，轉出來可能跟實際檔案不同。
    """
    try:
        from src.converter import convert_to_traditional
        return convert_to_traditional(s)
    except Exception:
        return s


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
                  script: str | None = None,
                  volume_name: str = "") -> dict:
    """判定一卷的內容完整性。

    script 說明 text 目前是什麼字體，決定章節標題（一律簡體原文）要不要先轉繁：
        "zh-hans" / None  → 標題直接比
        "zh-hant"         → 標題轉繁再比
        "unknown"         → 兩種都試，取命中多的那種（回推來的舊檔用）

    volume_name 有給的話會多算一組「卷名＋標題」的複合錨點當候選。給空字串
    只會少一組候選，不會判錯——**不可以**把它當成必要條件。

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

    # 檔案目前是什麼字體，決定標題要不要先轉繁。unknown 兩種都試，取命中多的。
    if script == "zh-hant":
        converters = [_to_traditional]
    elif script == "unknown":
        converters = [None, _to_traditional]
    else:
        converters = [None]

    # 兩組錨點都算，取命中數最高的那組來判定。
    #
    # ⚠ 這裡**刻意不預設任何一種命名格式**。複合錨點（卷名＋標題）只在 aid=1832
    # 與 1861 兩本書上驗證過，樣本太小，不能當定律——每本小說的命名習慣本來就
    # 可能不同，站方版型也會變。寫死「一定用複合錨點」的話，遇到標題行沒有卷名
    # 前綴的書，複合錨點會 0 命中，然後把完好的檔案判成斷檔。
    #
    # 「取命中最高」在這裡是**辨識格式**，不是放寬標準：真正的斷檔會讓兩組錨點
    # 的尾段同時消失，命中率一起掉，選哪組都一樣會被抓出來。只有「格式對不上」
    # 這種結構性不適用的情況才會被這條救回去，那正是我們要的。
    candidates = []
    for conv in converters:
        for anchors in (_composite_anchors(chapters or [], volume_name, conv),
                        _anchor_titles(chapters or [], conv)):
            if anchors:
                hits, tail = _match(norm_text, anchors)
                candidates.append((len(anchors), hits, tail))

    if candidates:
        total, hits, tail = max(candidates, key=lambda r: r[1])
        if total >= ANCHOR_MIN_COUNT:
            result["anchor_total"] = total
            result["anchor_hits"] = hits
            result["tail_position"] = round(tail, 4)
            if hits / total < ANCHOR_HIT_RATIO:
                result["status"] = "suspect"
                result["reason"] = "anchor_ratio"
            elif tail < ANCHOR_TAIL_POSITION:
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
                script: str | None = None,
                volume_name: str = "") -> dict | None:
    """讀檔後跑 verify_volume()。讀不到回 None，讓呼叫端自己決定怎麼歸類。

    用 errors="replace" 開檔：非 UTF-8 的舊檔會解出 `�`，正好被判成 garbled，
    跟 downloader.check_garbled() 對非 UTF-8 檔案的既有語意一致。
    """
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    return verify_volume(text, chapters, median_chars, script, volume_name)
