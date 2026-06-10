import os
import queue
import inspect
from unittest.mock import patch, MagicMock
import pytest
from src.downloader import download_volume, build_filepath, run_download_all
from src.config import RETRY_COUNT, RETRY_DELAY

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
    assert os.path.exists(fp)
    assert os.path.getsize(fp) > 0


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
    assert messages[-1][1] == 2       # success count
    assert messages[-1][2] == []      # no failures (list of dicts)


def test_download_volume_has_retry_params():
    sig = inspect.signature(download_volume)
    assert sig.parameters["retry_count"].default == RETRY_COUNT
    assert sig.parameters["retry_delay"].default == RETRY_DELAY


def test_run_download_all_has_retry_params():
    sig = inspect.signature(run_download_all)
    assert sig.parameters["retry_count"].default == RETRY_COUNT
    assert sig.parameters["retry_delay"].default == RETRY_DELAY


def test_download_volume_respects_custom_retry_count(tmp_path):
    """retry_count=1 時只呼叫一次 session.get（失敗後不重試）"""
    session = _mock_session([Exception("fail")])
    fp = str(tmp_path / "vol.txt")
    with patch("src.downloader._get_session", return_value=session), \
         patch("src.downloader.time.sleep"):
        result = download_volume("1861", 65280, fp, retry_count=1, retry_delay=0)
    assert result is False
    assert session.get.call_count == 1


def test_run_download_all_passes_retry_to_volume(tmp_path):
    """run_download_all 傳入的 retry_count 會影響 log 訊息中顯示的次數"""
    session = MagicMock()
    session.get.side_effect = Exception("fail")
    volumes = [{"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99}]
    q = queue.Queue()
    with patch("src.downloader._get_session", return_value=session), \
         patch("src.downloader.time.sleep"):
        run_download_all("1", "TestBook", volumes, str(tmp_path), q,
                         retry_count=2, retry_delay=0)
    msgs = []
    while not q.empty():
        msgs.append(q.get())
    log_msg = next(m for m in msgs if m[0] == "log")
    assert "2x" in log_msg[4]
    assert session.get.call_count == 2  # retry_count=2 → called twice


def test_download_converts_to_traditional(tmp_path):
    """下載後內容自動轉為繁體中文"""
    # 60 bytes 以上才能通過 HTML 偵測（< 50 bytes 會被擋）
    simplified_content = ("软件" * 30).encode("utf-8")
    session = _mock_session([_ok_resp(content=simplified_content)])
    fp = str(tmp_path / "vol.txt")
    with patch("src.downloader._get_session", return_value=session):
        assert download_volume("1861", 65280, fp) is True
    with open(fp, encoding="utf-8") as f:
        text = f.read()
    assert "軟體" in text
    assert "软件" not in text
