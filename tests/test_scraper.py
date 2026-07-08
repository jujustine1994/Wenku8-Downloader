import pytest
from bs4 import BeautifulSoup
from src.scraper import (
    parse_aid_from_url,
    parse_volumes,
    parse_book_title,
    format_index_token,
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
