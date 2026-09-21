import pytest
from bs4 import BeautifulSoup
from src.scraper import (
    parse_aid_from_url,
    parse_volumes,
    parse_book_title,
    format_index_token,
    classify_volumes,
    resequence_by_category,
    assign_categories_and_sequence,
    parse_vid_from_url,
    parse_cid_from_url,
    find_volume_by_cid,
)

SAMPLE_HTML = """
<html>
<head><title>Re:從零開始的異世界生活 - 輕小說文庫</title></head>
<body>
<h2>Re:從零開始的異世界生活</h2>
<table>
  <tr><td colspan="4">第一卷</td></tr>
  <tr>
    <td><a href="reader.php?aid=1861&cid=65281">序章</a></td>
    <td><a href="reader.php?aid=1861&cid=65282">第一章</a></td>
  </tr>
  <tr><td colspan="4">第二卷</td></tr>
  <tr>
    <td><a href="reader.php?aid=1861&cid=67829">序章</a></td>
  </tr>
  <tr><td colspan="4">第三卷</td></tr>
  <tr>
    <td><a href="reader.php?aid=1861&cid=70001">第一章</a></td>
  </tr>
</table>
</body></html>
"""


def test_parse_aid_basic():
    url = "https://www.wenku8.net/modules/article/reader.php?aid=1861"
    assert parse_aid_from_url(url) == "1861"


def test_parse_aid_with_cid():
    url = "https://www.wenku8.net/modules/article/reader.php?aid=1861&cid=65281"
    assert parse_aid_from_url(url) == "1861"


def test_parse_aid_missing_raises():
    with pytest.raises(ValueError):
        parse_aid_from_url("https://www.wenku8.net/modules/article/reader.php")


def test_parse_volumes_count():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    volumes = parse_volumes(soup)
    assert len(volumes) == 3


def test_parse_volumes_first():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    v = parse_volumes(soup)[0]
    assert v["index"] == 1
    assert v["name"] == "第一卷"
    assert v["first_cid"] == 65281
    assert v["vid"] == 65280


def test_parse_volumes_no_prelude():
    # Third volume has 第一章 instead of 序章 — must still work
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    v = parse_volumes(soup)[2]
    assert v["first_cid"] == 70001
    assert v["vid"] == 70000


def test_parse_book_title_h2():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    assert parse_book_title(soup) == "Re:從零開始的異世界生活"


def test_parse_book_title_fallback():
    html = "<html><head><title>灼眼的夏娜 - 輕小說文庫</title></head><body></body></html>"
    soup = BeautifulSoup(html, "lxml")
    assert parse_book_title(soup) == "灼眼的夏娜"


def test_format_index_token_padded_no_prefix():
    assert format_index_token(1, 18, "padded", "") == "01"


def test_format_index_token_padded_with_prefix():
    assert format_index_token(1, 5, "padded", "外傳") == "外傳01"


def test_format_index_token_plain_with_prefix():
    assert format_index_token(1, 5, "plain", "外傳") == "外傳1"


def test_format_index_token_none_ignores_prefix():
    assert format_index_token(1, 5, "none", "外傳") == ""


def test_format_index_token_triple_digit_padding():
    assert format_index_token(1, 100, "padded", "") == "001"


def test_classify_volumes_detects_side_keyword():
    volumes = [
        {"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99},
        {"index": 2, "name": "番外篇·SS", "first_cid": 200, "vid": 199},
    ]
    result = classify_volumes(volumes, ["番外", "SS"])
    assert result[0]["category"] == "main"
    assert result[1]["category"] == "side"


def test_classify_volumes_empty_keywords_all_main():
    volumes = [{"index": 1, "name": "任何名字", "first_cid": 100, "vid": 99}]
    result = classify_volumes(volumes, [])
    assert result[0]["category"] == "main"


def test_classify_volumes_does_not_mutate_input():
    volumes = [{"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99}]
    classify_volumes(volumes, [])
    assert "category" not in volumes[0]


def test_classify_volumes_preserves_order():
    volumes = [
        {"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99},
        {"index": 2, "name": "第二卷", "first_cid": 200, "vid": 199},
    ]
    result = classify_volumes(volumes, [])
    assert [v["name"] for v in result] == ["第一卷", "第二卷"]


def test_resequence_by_category_mixed():
    volumes = [
        {"index": 1, "name": "第一卷", "category": "main"},
        {"index": 2, "name": "番外·SS", "category": "side"},
        {"index": 3, "name": "第二卷", "category": "main"},
    ]
    result = resequence_by_category(volumes)
    assert result[0]["seq_index"] == 1 and result[0]["seq_total"] == 2
    assert result[1]["seq_index"] == 1 and result[1]["seq_total"] == 1
    assert result[2]["seq_index"] == 2 and result[2]["seq_total"] == 2


def test_resequence_by_category_all_same_category():
    volumes = [
        {"index": 1, "name": "第一卷", "category": "main"},
        {"index": 2, "name": "第二卷", "category": "main"},
    ]
    result = resequence_by_category(volumes)
    assert [v["seq_index"] for v in result] == [1, 2]
    assert all(v["seq_total"] == 2 for v in result)


def test_resequence_by_category_preserves_order():
    volumes = [
        {"index": 1, "name": "A", "category": "side"},
        {"index": 2, "name": "B", "category": "main"},
    ]
    result = resequence_by_category(volumes)
    assert [v["name"] for v in result] == ["A", "B"]


def test_resequence_by_category_does_not_change_category():
    volumes = [{"index": 1, "name": "第一卷", "category": "main"}]
    result = resequence_by_category(volumes)
    assert result[0]["category"] == "main"


def test_assign_categories_and_sequence_combines_both_steps():
    volumes = [
        {"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99},
        {"index": 2, "name": "番外篇·SS", "first_cid": 200, "vid": 199},
        {"index": 3, "name": "第二卷", "first_cid": 300, "vid": 299},
    ]
    result = assign_categories_and_sequence(volumes, ["番外", "SS"])
    assert result[0]["category"] == "main"
    assert result[0]["seq_index"] == 1
    assert result[0]["seq_total"] == 2
    assert result[1]["category"] == "side"
    assert result[1]["seq_index"] == 1
    assert result[1]["seq_total"] == 1
    assert result[2]["category"] == "main"
    assert result[2]["seq_index"] == 2


# ── 章節清單擷取（供 src/verify.py 做完整性判定）──

# index.htm 版型：卷標題 td 帶 vid 屬性，章節連結是**相對路徑、沒有 query**，
# 而且一個 <tr> 裝 4 個 <td>、每個 td 一章。
INDEX_HTML = """
<html><body><table>
  <tr><td class="vcss" colspan="4" vid="65280">第一卷</td></tr>
  <tr>
    <td class="ccss"><a href="65281.htm">序章</a></td>
    <td class="ccss"><a href="65282.htm">第一章</a></td>
    <td class="ccss"><a href="65283.htm">第二章</a></td>
    <td class="ccss"><a href="65284.htm">第三章</a></td>
  </tr>
  <tr>
    <td class="ccss"><a href="65640.htm">插圖</a></td>
    <td class="ccss"></td><td class="ccss"></td><td class="ccss"></td>
  </tr>
  <tr><td class="vcss" colspan="4" vid="67828">第二卷</td></tr>
  <tr><td class="ccss"><a href="67829.htm">序章</a></td></tr>
</table></body></html>
"""


def test_index_layout_collects_all_chapters_in_a_row():
    volumes = parse_volumes(BeautifulSoup(INDEX_HTML, "lxml"))
    assert [c["cid"] for c in volumes[0]["chapters"]] == [
        65281, 65282, 65283, 65284, 65640
    ]
    assert volumes[0]["chapters"][0]["title"] == "序章"


def test_index_layout_vid_still_from_header_attribute():
    volumes = parse_volumes(BeautifulSoup(INDEX_HTML, "lxml"))
    assert [v["vid"] for v in volumes] == [65280, 67828]
    assert volumes[0]["first_cid"] == 65281


def test_reader_layout_still_derives_vid_from_first_cid():
    volumes = parse_volumes(BeautifulSoup(SAMPLE_HTML, "lxml"))
    assert [v["vid"] for v in volumes] == [65280, 67828, 70000]
    assert [v["first_cid"] for v in volumes] == [65281, 67829, 70001]


def test_reader_layout_collects_chapters_too():
    volumes = parse_volumes(BeautifulSoup(SAMPLE_HTML, "lxml"))
    assert [c["cid"] for c in volumes[0]["chapters"]] == [65281, 65282]


# ── 單卷網址 ──

def test_parse_vid_from_url_reads_query():
    url = "https://www.wenku8.net/modules/article/reader.php?aid=1861&vid=65280"
    assert parse_vid_from_url(url) == 65280


def test_parse_vid_from_url_returns_none_for_catalog_url():
    assert parse_vid_from_url("https://www.wenku8.net/book/1861.htm") is None


def test_parse_cid_from_url_reads_chapter_page():
    assert parse_cid_from_url("https://www.wenku8.net/novel/0/1861/65281.htm") == 65281


def test_parse_cid_from_url_ignores_book_page():
    """/book/1861.htm 的數字是 aid 不是 cid，不可誤認成章節。"""
    assert parse_cid_from_url("https://www.wenku8.net/book/1861.htm") is None
    assert parse_cid_from_url("https://www.wenku8.net/novel/0/1861/index.htm") is None


def test_find_volume_by_cid():
    volumes = parse_volumes(BeautifulSoup(INDEX_HTML, "lxml"))
    assert find_volume_by_cid(volumes, 65640)["vid"] == 65280
    assert find_volume_by_cid(volumes, 67829)["vid"] == 67828
    assert find_volume_by_cid(volumes, 999) is None
