import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.main import resolve_output_dir, format_seq_ranges, describe_url
from src.config import OUTPUT_DIR


def test_uses_config_when_set():
    config = {"output_dir": r"C:\custom\path"}
    result = resolve_output_dir(config, r"C:\project")
    assert result == r"C:\custom\path"


def test_falls_back_to_default_when_missing():
    config = {}
    result = resolve_output_dir(config, r"C:\project")
    assert result == os.path.join(r"C:\project", OUTPUT_DIR)


def test_falls_back_when_empty_string():
    config = {"output_dir": ""}
    result = resolve_output_dir(config, r"C:\project")
    assert result == os.path.join(r"C:\project", OUTPUT_DIR)


def test_falls_back_when_whitespace_only():
    config = {"output_dir": "   "}
    result = resolve_output_dir(config, r"C:\project")
    assert result == os.path.join(r"C:\project", OUTPUT_DIR)


# ── format_seq_ranges（更新提示裡「已有 1–10 卷」那串）──

def test_format_seq_ranges_empty():
    assert format_seq_ranges([]) == ""


def test_format_seq_ranges_contiguous():
    assert format_seq_ranges([1, 2, 3, 4]) == "1–4（共 4 卷）"


def test_format_seq_ranges_single_value():
    assert format_seq_ranges([7]) == "7（共 1 卷）"


def test_format_seq_ranges_splits_gaps():
    assert format_seq_ranges([1, 2, 3, 7, 8]) == "1–3、7–8（共 5 卷）"


def test_format_seq_ranges_dedupes_and_sorts():
    assert format_seq_ranges([3, 1, 2, 2]) == "1–3（共 3 卷）"


def test_format_seq_ranges_truncates_when_too_many_spans():
    # 段數超過 max_parts 就不再逐段列，避免狀態列爆掉
    assert format_seq_ranges([1, 3, 5, 7, 9]) == "1、3、5 等 5 卷"


# ── describe_url（貼上網址當下的即時提示）──

def test_describe_url_empty_is_silent():
    assert describe_url("") == ("", "info")
    assert describe_url("   ") == ("", "info")


def test_describe_url_catalog_page():
    text, level = describe_url("https://www.wenku8.net/novel/1/1832/index.htm")
    assert level == "info"
    assert "整套目錄" in text and "1832" in text


def test_describe_url_book_page_and_bare_number():
    assert "整套目錄" in describe_url("https://www.wenku8.net/book/1832.htm")[0]
    assert "整套目錄" in describe_url("1832")[0]


def test_describe_url_single_volume_by_vid():
    text, level = describe_url(
        "https://www.wenku8.net/modules/article/reader.php?aid=1832&vid=63835")
    assert level == "info"
    assert "單卷" in text and "63835" in text


def test_describe_url_single_volume_by_chapter_page():
    text, level = describe_url("https://www.wenku8.net/novel/1/1832/63836.htm")
    assert level == "info"
    assert "單卷" in text and "63836" in text


def test_describe_url_unrecognised():
    text, level = describe_url("https://example.invalid/whatever")
    assert level == "error"
    assert "認不出" in text


def test_describe_url_matches_what_load_actually_does():
    """提示講的必須跟 _on_load 實際採用的判斷一致，不能各算各的。"""
    from src.scraper import parse_vid_from_url, parse_cid_from_url
    for url in ("https://www.wenku8.net/novel/1/1832/index.htm",
                "https://www.wenku8.net/modules/article/reader.php?aid=1832&vid=63835",
                "https://www.wenku8.net/novel/1/1832/63836.htm"):
        is_single = (parse_vid_from_url(url) is not None
                     or parse_cid_from_url(url) is not None)
        assert ("單卷" in describe_url(url)[0]) == is_single
