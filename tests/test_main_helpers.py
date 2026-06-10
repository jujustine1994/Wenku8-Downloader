import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.main import resolve_output_dir
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
