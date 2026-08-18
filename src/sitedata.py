"""sitedata.py — **資料**字串，永遠不翻譯。

判斷準則（general.md / windows-tool.md）：
    這個字串會不會被寫進檔案、或拿去跟檔案／網站抓下來的值比對？
    會 → 它是資料，永遠不翻。不會 → 它是介面文字，走 i18n.t()。

這個檔裡的每一條都「會」，所以一條都不進 locales/。翻了會怎樣：

- SIDE_INDEX_PREFIX（「外傳」）進檔名。翻了之後，使用者切一次語言，同一本書
  的外傳就存到另一組檔名去，舊檔案對不起來，掃描既有檔案也全部判定成缺檔，
  然後整批重抓一次。
- DEFAULT_SIDE_KEYWORDS 是拿去跟 **wenku8 抓下來的卷名**（簡體）做 `in` 比對的
  關鍵字，而且會存進 .tool_config.json。翻了＝分類靜默失效，全部卷變成正卷。
- MAIN_VOLUME_RE / TITLE_TRIM_RE 是解析網站 HTML 用的樣式。wenku8 是**簡體**
  站，裡面的簡體字是比對用的資料，不是「該翻成繁中的介面文字」。動了就抓不到。
- UNKNOWN_BOOK_TITLE 會變成 book_name，直接進檔名。

⚠ 這個檔在 tests/test_i18n.py 的 ALLOWLIST 裡（豁免「不可有寫死中日文」那條
測試），理由就是上面這段。新增條目前先確認它真的屬於「會落檔／會比對」。
"""

from __future__ import annotations

import re

# 卷名裡出現這些樣式就判定為「正式卷」（白名單優先於外傳關鍵字）。
# 簡繁字形都要涵蓋：wenku8 是簡體站，但使用者也可能貼繁體來源。
MAIN_VOLUME_RE = re.compile(
    r'第[一二三四五六七八九十百千萬\d]+[卷册冊部篇章]'
    r'|Vol\.?\s*\d+'
    r'|卷[一二三四五六七八九十百千萬\d]+'
    r'|\d+[卷册冊部篇章]',
    re.IGNORECASE,
)

# wenku8 的 <title> 格式："書名小说在线阅读与TXT电子书下载-作者-出版社-網站名"
# 取書名關鍵字前的部分。這裡的簡體字是**網站原文**，不可改成繁體。
TITLE_TRIM_RE = re.compile(r"^(.+?)(?:小说|TXT|全文|在线|电子书)", re.IGNORECASE)

# 解析不到書名時的替代書名。會直接變成檔名的一部分。
UNKNOWN_BOOK_TITLE = "未知書名"

# 外傳卷的檔名編號前綴，例如「外傳01 書名 番外篇.txt」。進檔名，不可翻。
SIDE_INDEX_PREFIX = "外傳"

# 判斷卷名是否為外傳的預設關鍵字。拿去跟網站抓下來的卷名做小寫 `in` 比對，
# 並且會存進 .tool_config.json 的 side_keywords。不可翻。
DEFAULT_SIDE_KEYWORDS = [
    "外傳", "番外", "特典", "SS", "EX", "Extra", "Side Story",
    "幕間", "插話", "間章", "附錄", "後記", "後日談", "後日譚",
    "特別篇", "短篇", "短篇集", "Epilogue",
]
