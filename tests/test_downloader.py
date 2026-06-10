import os
import queue
from unittest.mock import patch
import pytest
from src.downloader import download_volume, build_filepath, run_download_all

DOWNLOAD_URL = "http://dl.wenku8.com/packtxt.php?aid=1861&vid=65280&charset=utf-8"
CONTENT = "A" * 500


def test_download_success(tmp_path, requests_mock):
    requests_mock.get(DOWNLOAD_URL, text=CONTENT)
    fp = str(tmp_path / "vol.txt")
    assert download_volume("1861", 65280, fp) is True
    assert open(fp, encoding="utf-8").read() == CONTENT


def test_download_retry_then_success(tmp_path, requests_mock):
    requests_mock.get(DOWNLOAD_URL, [
        {"exc": Exception("timeout")},
        {"exc": Exception("timeout")},
        {"text": CONTENT},
    ])
    fp = str(tmp_path / "retry.txt")
    with patch("src.downloader.time.sleep"):
        assert download_volume("1861", 65280, fp) is True


def test_download_all_fail(tmp_path, requests_mock):
    requests_mock.get(DOWNLOAD_URL, exc=Exception("unreachable"))
    fp = str(tmp_path / "fail.txt")
    with patch("src.downloader.time.sleep"):
        assert download_volume("1861", 65280, fp) is False


def test_build_filepath_basic():
    path = build_filepath("downloads", "灼眼的夏娜", 1, "第一卷", 18)
    expected = os.path.join("downloads", "灼眼的夏娜", "01 灼眼的夏娜 第一卷.txt")
    assert path == expected


def test_build_filepath_triple_digit():
    path = build_filepath("downloads", "某書", 1, "第一卷", 100)
    assert "001 某書 第一卷.txt" in path


def test_run_download_all_messages(tmp_path, requests_mock):
    url1 = "http://dl.wenku8.com/packtxt.php?aid=1&vid=99&charset=utf-8"
    url2 = "http://dl.wenku8.com/packtxt.php?aid=1&vid=199&charset=utf-8"
    requests_mock.get(url1, text="X" * 500)
    requests_mock.get(url2, text="Y" * 500)

    volumes = [
        {"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99},
        {"index": 2, "name": "第二卷", "first_cid": 200, "vid": 199},
    ]
    q = queue.Queue()
    run_download_all("1", "TestBook", volumes, str(tmp_path), q)

    messages = []
    while not q.empty():
        messages.append(q.get())

    types = [m[0] for m in messages]
    assert "progress" in types
    assert "log" in types
    assert messages[-1][0] == "done"
    assert messages[-1][1] == 2  # success count
