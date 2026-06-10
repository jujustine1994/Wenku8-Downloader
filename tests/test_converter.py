import os
import queue
import pytest
from src.converter import convert_to_traditional, run_convert_all


def test_converts_simplified_software():
    assert convert_to_traditional("软件") == "軟體"


def test_converts_network_term():
    assert convert_to_traditional("网络") == "網路"


def test_converts_common_terms():
    result = convert_to_traditional("软件 硬件 网络 文件")
    assert "軟體" in result
    assert "硬體" in result
    assert "網路" in result
    assert "檔案" in result


def test_traditional_input_unchanged():
    assert convert_to_traditional("軟體網路") == "軟體網路"


def test_empty_string():
    assert convert_to_traditional("") == ""


def test_mixed_content_preserved():
    result = convert_to_traditional("Hello 软件 123")
    assert "Hello" in result
    assert "軟體" in result
    assert "123" in result


def test_run_convert_all_overwrite(tmp_path):
    fp = tmp_path / "test.txt"
    fp.write_text("软件", encoding="utf-8")
    q = queue.Queue()
    run_convert_all([str(fp)], "overwrite", q)
    assert fp.read_text(encoding="utf-8") == "軟體"
    msgs = []
    while not q.empty():
        msgs.append(q.get())
    assert msgs[-1] == ("conv_done", 1, 0)


def test_run_convert_all_new_file(tmp_path):
    fp = tmp_path / "test.txt"
    fp.write_text("软件", encoding="utf-8")
    q = queue.Queue()
    run_convert_all([str(fp)], "new_file", q)
    new_fp = tmp_path / "test_TC.txt"
    assert new_fp.exists()
    assert new_fp.read_text(encoding="utf-8") == "軟體"
    assert fp.read_text(encoding="utf-8") == "软件"


def test_run_convert_all_log_messages(tmp_path):
    fp = tmp_path / "test.txt"
    fp.write_text("软件", encoding="utf-8")
    q = queue.Queue()
    run_convert_all([str(fp)], "overwrite", q)
    msgs = []
    while not q.empty():
        msgs.append(q.get())
    assert ("conv_log", True, "test.txt", "") in msgs
    assert msgs[-1] == ("conv_done", 1, 0)


def test_run_convert_all_handles_missing_file(tmp_path):
    q = queue.Queue()
    run_convert_all([str(tmp_path / "nonexistent.txt")], "overwrite", q)
    msgs = []
    while not q.empty():
        msgs.append(q.get())
    assert msgs[-1] == ("conv_done", 0, 1)
    assert msgs[0][0] == "conv_log"
    assert msgs[0][1] is False


def test_run_convert_all_multiple_files(tmp_path):
    files = []
    for i in range(3):
        fp = tmp_path / f"vol{i}.txt"
        fp.write_text("软件", encoding="utf-8")
        files.append(str(fp))
    q = queue.Queue()
    run_convert_all(files, "overwrite", q)
    msgs = []
    while not q.empty():
        msgs.append(q.get())
    assert msgs[-1] == ("conv_done", 3, 0)
    log_msgs = [m for m in msgs if m[0] == "conv_log"]
    assert len(log_msgs) == 3
