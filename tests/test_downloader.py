import os
import queue
from unittest.mock import patch, MagicMock
import pytest
from src.downloader import download_volume, build_filepath, run_download_all

CONTENT = b"A" * 500


def _ok_resp(content=CONTENT):
    resp = MagicMock()
    resp.content = content
    resp.raise_for_status = MagicMock()
    return resp


def _mock_session(side_effect):
    session = MagicMock()
    session.get.side_effect = side_effect
    return session


def test_download_success(tmp_path):
    session = _mock_session([_ok_resp()])
    fp = str(tmp_path / "vol.txt")
    with patch("src.downloader._get_session", return_value=session):
        assert download_volume("1861", 65280, fp) is True
    assert open(fp, "rb").read() == CONTENT


def test_download_retry_then_success(tmp_path):
    session = _mock_session([
        Exception("timeout"),
        Exception("timeout"),
        _ok_resp(),
    ])
    fp = str(tmp_path / "retry.txt")
    with patch("src.downloader._get_session", return_value=session), \
         patch("src.downloader.time.sleep"):
        assert download_volume("1861", 65280, fp) is True


def test_download_all_fail(tmp_path):
    session = MagicMock()
    session.get.side_effect = Exception("unreachable")
    fp = str(tmp_path / "fail.txt")
    with patch("src.downloader._get_session", return_value=session), \
         patch("src.downloader.time.sleep"):
        assert download_volume("1861", 65280, fp) is False


def test_build_filepath_basic():
    path = build_filepath("downloads", "灼眼的夏娜", 1, "第一卷", 18)
    expected = os.path.join("downloads", "灼眼的夏娜", "01 灼眼的夏娜 第一卷.txt")
    assert path == expected


def test_build_filepath_triple_digit():
    path = build_filepath("downloads", "某書", 1, "第一卷", 100)
    assert "001 某書 第一卷.txt" in path


def test_run_download_all_messages(tmp_path):
    session = MagicMock()
    session.get.return_value = _ok_resp()

    volumes = [
        {"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99},
        {"index": 2, "name": "第二卷", "first_cid": 200, "vid": 199},
    ]
    q = queue.Queue()
    with patch("src.downloader._get_session", return_value=session):
        run_download_all("1", "TestBook", volumes, str(tmp_path), q)

    messages = []
    while not q.empty():
        messages.append(q.get())

    types = [m[0] for m in messages]
    assert "progress" in types
    assert "log" in types
    assert messages[-1][0] == "done"
    assert messages[-1][1] == 2  # success count
