import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.main import resolve_output_dir, format_seq_ranges
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
