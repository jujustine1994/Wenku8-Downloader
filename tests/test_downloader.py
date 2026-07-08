import os
import queue
import inspect
from unittest.mock import patch, MagicMock
import pytest
from src.downloader import download_volume, build_filepath, run_download_all, check_garbled, repair_volume, run_repair_all
from src.scraper import assign_categories_and_sequence
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


def test_download_strips_utf16_bom(tmp_path):
    """charset=utf-8 實際回傳 UTF-16 LE bytes；BOM 本身不該混進解碼後的文字內容"""
    content = b"\xff\xfe" + ("軟體" * 30).encode("utf-16-le")
    session = _mock_session([_ok_resp(content=content)])
    fp = str(tmp_path / "vol.txt")
    with patch("src.downloader._get_session", return_value=session):
        assert download_volume("1861", 65280, fp) is True
    with open(fp, encoding="utf-8") as f:
        text = f.read()
    assert not text.startswith("﻿")
    assert "軟體" in text


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
    expected = os.path.join("downloads", "01 灼眼的夏娜 第一卷.txt")
    assert path == expected


def test_build_filepath_triple_digit():
    path = build_filepath("downloads", "某書", 1, "第一卷", 100)
    assert "001 某書 第一卷.txt" in path


def test_build_filepath_with_index_prefix():
    path = build_filepath("downloads", "書名", 1, "番外篇·SS", 5,
                          index_prefix="外傳")
    assert path == os.path.join("downloads", "外傳01 書名 番外篇·SS.txt")


def test_build_filepath_index_prefix_default_empty():
    """不傳 index_prefix 時行為跟現有測試完全一致"""
    path = build_filepath("downloads", "書名", 1, "第一卷", 10)
    assert path == os.path.join("downloads", "01 書名 第一卷.txt")


def test_build_filepath_index_prefix_ignored_when_none_fmt():
    path = build_filepath("downloads", "書名", 1, "番外篇·SS", 5,
                          index_fmt="none", index_prefix="外傳")
    assert path == os.path.join("downloads", "書名 番外篇·SS.txt")


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
    assert messages[-1][3] == []      # no garbled volumes


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


def test_build_filepath_plain_index():
    path = build_filepath("downloads", "書名", 1, "第一卷", 10, index_fmt="plain")
    assert path == os.path.join("downloads", "1 書名 第一卷.txt")


def test_build_filepath_no_index():
    path = build_filepath("downloads", "書名", 1, "第一卷", 10, index_fmt="none")
    assert path == os.path.join("downloads", "書名 第一卷.txt")


def test_build_filepath_no_book_name():
    path = build_filepath("downloads", "書名", 1, "第一卷", 10, include_book_name=False)
    assert path == os.path.join("downloads", "01 第一卷.txt")


def test_build_filepath_custom_separator():
    path = build_filepath("downloads", "書名", 1, "第一卷", 10, separator="_")
    assert path == os.path.join("downloads", "01_書名_第一卷.txt")


def test_build_filepath_no_index_no_book():
    path = build_filepath("downloads", "書名", 1, "第一卷", 10,
                          index_fmt="none", include_book_name=False)
    assert path == os.path.join("downloads", "第一卷.txt")


def test_run_download_all_has_naming_params():
    sig = inspect.signature(run_download_all)
    assert sig.parameters["index_fmt"].default == "padded"
    assert sig.parameters["include_book_name"].default is True
    assert sig.parameters["separator"].default == " "


def test_run_download_all_naming_params_applied(tmp_path):
    """命名參數確實影響輸出檔名"""
    session = MagicMock()
    session.get.return_value = _ok_resp()
    volumes = [{"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99}]
    q = queue.Queue()
    with patch("src.downloader._get_session", return_value=session):
        run_download_all("1", "書名", volumes, str(tmp_path), q,
                         index_fmt="none", include_book_name=False, separator="_")
    expected = os.path.join(str(tmp_path), "第一卷.txt")
    assert os.path.exists(expected)


def test_build_filepath_unsafe_separator_stripped():
    """Windows-illegal chars in separator are stripped (not silently misrouted)"""
    path = build_filepath("downloads", "書名", 1, "第一卷", 10, separator="/")
    # "/" stripped → separator becomes "" → falls back to " "
    assert path == os.path.join("downloads", "01 書名 第一卷.txt")

    path2 = build_filepath("downloads", "書名", 1, "第一卷", 10, separator=":")
    assert path2 == os.path.join("downloads", "01 書名 第一卷.txt")


def test_check_garbled_clean(tmp_path):
    fp = tmp_path / "clean.txt"
    fp.write_text("這是正常的繁體中文內容。", encoding="utf-8")
    assert check_garbled(str(fp)) is False


def test_check_garbled_with_replacement_char(tmp_path):
    fp = tmp_path / "garbled.txt"
    fp.write_text("正常內容�亂碼", encoding="utf-8")
    assert check_garbled(str(fp)) is True


def test_repair_volume_uses_gbk_when_utf8_garbled(tmp_path):
    """UTF-8 下載有亂碼時，改用 GBK 下載且結果更乾淨"""
    invalid_utf8 = b"\x80" * 100           # 100 bytes, invalid UTF-8 → all �
    clean_gbk = ("软件" * 30).encode("gbk") # 120 bytes, valid GBK

    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.content = invalid_utf8 if "charset=utf-8" in url else clean_gbk
        return resp

    session = MagicMock()
    session.get.side_effect = mock_get
    fp = str(tmp_path / "書名" / "vol.txt")
    os.makedirs(os.path.dirname(fp), exist_ok=True)

    with patch("src.downloader._get_session", return_value=session):
        result = repair_volume("1", 99, fp)

    assert result is False
    with open(fp, encoding="utf-8") as f:
        assert "�" not in f.read()


def test_repair_volume_returns_true_when_both_encodings_garbled(tmp_path):
    """兩種編碼都有亂碼時回傳 True"""
    # \x80*100: invalid UTF-8 → all U+FFFD (does not collide with any BOM prefix)
    invalid_for_utf8 = b"\x80" * 100
    # \xff*60: invalid GBK → all U+FFFD (avoid \xff\xfe, which is a UTF-16 LE BOM)
    invalid_for_gbk = b"\xff" * 60

    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.content = invalid_for_utf8 if "charset=utf-8" in url else invalid_for_gbk
        return resp

    session = MagicMock()
    session.get.side_effect = mock_get
    fp = str(tmp_path / "書名" / "vol.txt")
    os.makedirs(os.path.dirname(fp), exist_ok=True)

    with patch("src.downloader._get_session", return_value=session), \
         patch("src.downloader.time.sleep"):
        result = repair_volume("1", 99, fp)

    assert result is True


def test_repair_volume_returns_none_on_network_failure(tmp_path):
    """網路失敗（all retries exhausted）回傳 None"""
    session = MagicMock()
    session.get.side_effect = Exception("network error")
    fp = str(tmp_path / "書名" / "vol.txt")
    os.makedirs(os.path.dirname(fp), exist_ok=True)

    with patch("src.downloader._get_session", return_value=session), \
         patch("src.downloader.time.sleep"):
        result = repair_volume("1", 99, fp, retry_count=1)

    assert result is None


def test_run_download_all_detects_garbled(tmp_path):
    """下載後含 U+FFFD 的卷發出 warn log 並出現在 done[3]"""
    garbled_bytes = b"\x80" * 100  # invalid UTF-8 → decoded to U+FFFD chars by download_volume

    session = MagicMock()
    session.get.return_value = _ok_resp(content=garbled_bytes)
    volumes = [{"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99}]
    q = queue.Queue()
    with patch("src.downloader._get_session", return_value=session):
        run_download_all("1", "書名", volumes, str(tmp_path), q)
    msgs = []
    while not q.empty():
        msgs.append(q.get())
    log_msg = next(m for m in msgs if m[0] == "log")
    assert log_msg[1] == "warn"
    assert log_msg[4] == "偵測到亂碼"
    done_msg = msgs[-1]
    assert done_msg[0] == "done"
    assert done_msg[3] == [{"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99}]


def test_run_download_all_done_has_four_elements(tmp_path):
    """done 訊息永遠是 4-tuple，無亂碼時 done[3] 為空 list"""
    session = MagicMock()
    session.get.return_value = _ok_resp()
    volumes = [{"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99}]
    q = queue.Queue()
    with patch("src.downloader._get_session", return_value=session):
        run_download_all("1", "書名", volumes, str(tmp_path), q)
    msgs = []
    while not q.empty():
        msgs.append(q.get())
    done_msg = msgs[-1]
    assert done_msg[0] == "done"
    assert len(done_msg) == 4
    assert done_msg[3] == []


def test_run_repair_all_ok_when_repaired(tmp_path):
    """repair_volume 回傳 False → ok log，done success=1"""
    volumes = [{"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99}]
    q = queue.Queue()
    with patch("src.downloader.repair_volume", return_value=False):
        run_repair_all("1", "書名", volumes, str(tmp_path), q)
    msgs = []
    while not q.empty():
        msgs.append(q.get())
    log_msg = next(m for m in msgs if m[0] == "log")
    assert log_msg[1] == "ok"
    assert log_msg[4] == "已修復"
    done = msgs[-1]
    assert done[1] == 1
    assert done[2] == []
    assert done[3] == []


def test_run_repair_all_warn_when_still_garbled(tmp_path):
    """repair_volume 回傳 True → warn log，done garbled_volumes 有該卷"""
    vol = {"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99}
    q = queue.Queue()
    with patch("src.downloader.repair_volume", return_value=True):
        run_repair_all("1", "書名", [vol], str(tmp_path), q)
    msgs = []
    while not q.empty():
        msgs.append(q.get())
    log_msg = next(m for m in msgs if m[0] == "log")
    assert log_msg[1] == "warn"
    assert log_msg[4] == "修復後仍有亂碼"
    done = msgs[-1]
    assert done[3] == [vol]


def test_run_repair_all_fail_on_network_error(tmp_path):
    """repair_volume 回傳 None → fail log，done fail_volumes 有該卷"""
    vol = {"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99}
    q = queue.Queue()
    with patch("src.downloader.repair_volume", return_value=None):
        run_repair_all("1", "書名", [vol], str(tmp_path), q)
    msgs = []
    while not q.empty():
        msgs.append(q.get())
    log_msg = next(m for m in msgs if m[0] == "log")
    assert log_msg[1] == "fail"
    done = msgs[-1]
    assert done[2] == [vol]
    assert done[3] == []


def test_download_volume_skip_before_retry(tmp_path):
    """skip_event 已設時，download_volume 在第一次嘗試前立即回傳 False"""
    import threading
    skip_event = threading.Event()
    skip_event.set()

    session = MagicMock()
    session.get.return_value = _ok_resp()
    fp = str(tmp_path / "書名" / "vol.txt")
    os.makedirs(os.path.dirname(fp), exist_ok=True)

    with patch("src.downloader._get_session", return_value=session):
        result = download_volume("1", 99, fp, skip_event=skip_event)

    assert result is False
    session.get.assert_not_called()   # 沒有實際發出請求


def test_download_volume_skip_between_retries(tmp_path):
    """download_volume 第一次失敗後，sleep 前 skip_event 被設 → 不繼續 retry"""
    import threading
    skip_event = threading.Event()
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        skip_event.set()   # 第一次失敗後設定 skip
        raise Exception("network error")

    session = MagicMock()
    session.get.side_effect = side_effect
    fp = str(tmp_path / "書名" / "vol.txt")
    os.makedirs(os.path.dirname(fp), exist_ok=True)

    with patch("src.downloader._get_session", return_value=session), \
         patch("src.downloader.time.sleep"):
        result = download_volume("1", 99, fp, retry_count=3, skip_event=skip_event)

    assert result is False
    assert call_count == 1   # 只嘗試了一次，沒有 retry


def test_run_download_all_skip_goes_to_fail(tmp_path):
    """skip_event 觸發後，該卷進入 fail_volumes，log status 為 skip"""
    import threading
    skip_event = threading.Event()

    call_count = 0
    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        skip_event.set()
        raise Exception("network error")

    session = MagicMock()
    session.get.side_effect = side_effect
    volumes = [{"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99}]
    q = queue.Queue()
    with patch("src.downloader._get_session", return_value=session), \
         patch("src.downloader.time.sleep"):
        run_download_all("1", "書名", volumes, str(tmp_path), q,
                         retry_count=3, skip_event=skip_event)
    msgs = []
    while not q.empty():
        msgs.append(q.get())
    log_msg = next(m for m in msgs if m[0] == "log")
    assert log_msg[1] == "skip"
    assert log_msg[4] == "已跳過"
    done = msgs[-1]
    assert done[2] == [{"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99}]


def test_run_download_all_skip_clears_event_for_next_volume(tmp_path):
    """跳過第一卷後，skip_event 被清除，第二卷正常下載"""
    import threading
    skip_event = threading.Event()

    call_count = 0
    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            skip_event.set()
            raise Exception("network error")
        return _ok_resp()

    session = MagicMock()
    session.get.side_effect = side_effect
    volumes = [
        {"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99},
        {"index": 2, "name": "第二卷", "first_cid": 200, "vid": 100},
    ]
    q = queue.Queue()
    with patch("src.downloader._get_session", return_value=session), \
         patch("src.downloader.time.sleep"):
        run_download_all("1", "書名", volumes, str(tmp_path), q,
                         retry_count=3, skip_event=skip_event)
    msgs = []
    while not q.empty():
        msgs.append(q.get())
    log_msgs = [m for m in msgs if m[0] == "log"]
    assert log_msgs[0][1] == "skip"   # 第一卷被跳過
    assert log_msgs[1][1] in ("ok", "warn")   # 第二卷下載成功
    done = msgs[-1]
    assert done[1] == 1   # 第二卷成功
    assert len(done[2]) == 1   # 第一卷在 fail_volumes


def test_run_download_all_uses_side_prefix(tmp_path):
    """帶 category='side' 的卷，檔名要有「外傳」前綴，且編號跟 main 分開算"""
    session = MagicMock()
    session.get.return_value = _ok_resp()
    volumes = [
        {"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99,
         "category": "main", "seq_index": 1, "seq_total": 1},
        {"index": 2, "name": "番外篇·SS", "first_cid": 200, "vid": 199,
         "category": "side", "seq_index": 1, "seq_total": 1},
    ]
    q = queue.Queue()
    with patch("src.downloader._get_session", return_value=session):
        run_download_all("1", "書名", volumes, str(tmp_path), q)
    main_path = os.path.join(str(tmp_path), "01 書名 第一卷.txt")
    side_path = os.path.join(str(tmp_path), "外傳01 書名 番外篇·SS.txt")
    assert os.path.exists(main_path)
    assert os.path.exists(side_path)


def test_run_download_all_backward_compatible_without_category(tmp_path):
    """volumes 沒有 category/seq_index/seq_total 時沿用舊行為，不報錯"""
    session = MagicMock()
    session.get.return_value = _ok_resp()
    volumes = [{"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99}]
    q = queue.Queue()
    with patch("src.downloader._get_session", return_value=session):
        run_download_all("1", "書名", volumes, str(tmp_path), q)
    expected = os.path.join(str(tmp_path), "01 書名 第一卷.txt")
    assert os.path.exists(expected)


def test_classify_to_download_end_to_end(tmp_path):
    """整合測試：raw volumes 經 assign_categories_and_sequence 真跑一遍分類+編號，
    再把真實輸出餵給 run_download_all，驗證檔名 main/side 編號與「外傳」前綴正確。
    這條路徑確保 classify→resequence→filename 三段接起來不會因欄位改名而斷掉。"""
    session = MagicMock()
    session.get.return_value = _ok_resp()
    raw_volumes = [
        {"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99},
        {"index": 2, "name": "番外篇·SS", "first_cid": 200, "vid": 199},
        {"index": 3, "name": "第二卷", "first_cid": 300, "vid": 299},
    ]
    # 不手工塞 category/seq_index/seq_total，全部交給真實分類函式產生
    volumes = assign_categories_and_sequence(raw_volumes, ["番外", "SS"])
    q = queue.Queue()
    with patch("src.downloader._get_session", return_value=session):
        run_download_all("1", "書名", volumes, str(tmp_path), q)
    # main 卷：01、02；side 卷：外傳01
    assert os.path.exists(os.path.join(str(tmp_path), "01 書名 第一卷.txt"))
    assert os.path.exists(os.path.join(str(tmp_path), "02 書名 第二卷.txt"))
    assert os.path.exists(os.path.join(str(tmp_path), "外傳01 書名 番外篇·SS.txt"))
