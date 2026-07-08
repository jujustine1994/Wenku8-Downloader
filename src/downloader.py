import os
import time
import queue
from curl_cffi import requests as cf_requests
from src.config import DOWNLOAD_BASE_URL, RETRY_COUNT, RETRY_DELAY
from src.converter import convert_to_traditional
from src.scraper import format_index_token

_session: cf_requests.Session | None = None


def _get_session() -> cf_requests.Session:
    global _session
    if _session is None:
        _session = cf_requests.Session()
    return _session


def _fetch_bytes(aid: str, vid: int, charset: str,
                 retry_count: int, retry_delay: float,
                 skip_event=None) -> bytes | None:
    """retry_count <= 0 表示無限重試，直到成功或 skip_event 被觸發。"""
    url = f"{DOWNLOAD_BASE_URL}?aid={aid}&vid={vid}&charset={charset}"
    infinite = retry_count <= 0
    attempt = 0
    while True:
        attempt += 1
        if skip_event and skip_event.is_set():
            return None
        try:
            resp = _get_session().get(url, impersonate="chrome120", timeout=30)
            resp.raise_for_status()
            # 回應內容不應是 HTML（< 開頭 = 錯誤頁面）
            if len(resp.content) < 50 or resp.content[:5].strip().startswith(b"<"):
                raise ValueError("Response is HTML error page, not TXT")
            return resp.content
        except Exception:
            if not infinite and attempt >= retry_count:
                return None
            if skip_event and skip_event.is_set():
                return None
            time.sleep(retry_delay)


def _decode_response(raw: bytes, charset_hint: str) -> str:
    """
    wenku8 的 charset query 參數不可信：實測 charset=utf-8 實際回傳的是
    UTF-16 LE bytes（帶 BOM），charset=big5 實際回傳的是 UTF-8（帶 BOM）。
    一律先偵測 BOM，偵測不到才照參數名稱猜測解碼。
    """
    if raw.startswith(b"\xff\xfe"):
        return raw[2:].decode("utf-16-le", errors="replace")
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", errors="replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace")
    return raw.decode(charset_hint, errors="replace")


def _fetch_best_text(aid: str, vid: int,
                     retry_count: int, retry_delay: float,
                     skip_event=None) -> str | None:
    """先抓 UTF-8，若含亂碼字元就自動改抓 GBK 版本並取亂碼較少者。"""
    utf8_bytes = _fetch_bytes(aid, vid, "utf-8", retry_count, retry_delay, skip_event)
    if utf8_bytes is None:
        return None
    utf8_text = _decode_response(utf8_bytes, "utf-8")

    if "�" not in utf8_text or (skip_event and skip_event.is_set()):
        return utf8_text

    gbk_bytes = _fetch_bytes(aid, vid, "gbk", retry_count, retry_delay, skip_event)
    if gbk_bytes is not None:
        gbk_text = _decode_response(gbk_bytes, "gbk")
        if gbk_text.count("�") < utf8_text.count("�"):
            return gbk_text
    return utf8_text


def download_volume(aid: str, vid: int, filepath: str,
                    retry_count: int = RETRY_COUNT,
                    retry_delay: float = RETRY_DELAY,
                    skip_event=None) -> bool:
    if skip_event and skip_event.is_set():
        return False
    text = _fetch_best_text(aid, vid, retry_count, retry_delay, skip_event)
    if text is None:
        return False
    converted = convert_to_traditional(text)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(converted)
    return True


def check_garbled(filepath: str) -> bool:
    with open(filepath, encoding="utf-8") as f:
        return "�" in f.read()


REPAIR_STALE_LIMIT = 5  # 連續幾輪沒有改善才放棄（避免真的修不好時無限卡住）


def repair_volume(aid: str, vid: int, filepath: str,
                  retry_count: int = RETRY_COUNT,
                  retry_delay: float = RETRY_DELAY,
                  skip_event=None) -> bool | None:
    """
    重複整輪重新下載（utf-8 + gbk 挑亂碼較少者），直到完全無亂碼、或
    skip_event 被觸發才停止。retry_count 為正數（有限重試）時，額外會在
    連續 REPAIR_STALE_LIMIT 輪都沒有改善時提早放棄；retry_count <= 0
    （無限重試）時則完全依照使用者設定，只靠 skip_event 才會停止。

    Returns False = 修復成功（無亂碼）
            True  = 仍有亂碼（放棄前已盡量取最佳結果）
            None  = 從未成功取得任何內容（網路失敗或一開始就被跳過）
    """
    infinite = retry_count <= 0
    best_text: str | None = None
    best_count: int | None = None
    stale_rounds = 0

    while True:
        if skip_event and skip_event.is_set():
            break
        text = _fetch_best_text(aid, vid, retry_count, retry_delay, skip_event)
        if text is not None:
            count = text.count("�")
            if best_count is None or count < best_count:
                best_text, best_count = text, count
                stale_rounds = 0
            else:
                stale_rounds += 1
            if count == 0:
                break
        else:
            stale_rounds += 1

        if skip_event and skip_event.is_set():
            break
        if not infinite and stale_rounds >= REPAIR_STALE_LIMIT:
            break
        time.sleep(retry_delay)

    if best_text is None:
        return None

    converted = convert_to_traditional(best_text)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(converted)

    return True if "�" in converted else False


def build_filepath(output_dir: str, book_name: str, volume_index: int,
                   volume_name: str, total: int,
                   index_fmt: str = "padded",
                   include_book_name: bool = True,
                   separator: str = " ",
                   index_prefix: str = "") -> str:
    safe = lambda s: "".join(c for c in s if c not in r'\/:*?"<>|')
    parts = []
    token = format_index_token(volume_index, total, index_fmt, index_prefix)
    if token:
        parts.append(safe(token))
    if include_book_name:
        parts.append(safe(book_name))
    parts.append(safe(volume_name))
    safe_sep = safe(separator) or " "
    filename = safe_sep.join(parts) + ".txt"
    return os.path.join(output_dir, filename)


def run_download_all(aid: str, book_name: str, volumes: list[dict],
                     output_dir: str, msg_queue: queue.Queue,
                     retry_count: int = RETRY_COUNT,
                     retry_delay: float = RETRY_DELAY,
                     index_fmt: str = "padded",
                     include_book_name: bool = True,
                     separator: str = " ",
                     skip_event=None) -> None:
    total = len(volumes)
    success = 0
    fail_volumes: list[dict] = []
    garbled_volumes: list[dict] = []
    pad = max(len(str(total)), 2)

    for i, vol in enumerate(volumes, 1):
        msg_queue.put(("progress", i, total, vol["name"]))
        index_str = str(vol["index"]).zfill(pad)
        try:
            filepath = build_filepath(output_dir, book_name, vol["index"], vol["name"], total,
                                      index_fmt, include_book_name, separator)
            ok = download_volume(aid, vol["vid"], filepath, retry_count, retry_delay, skip_event)
            if ok:
                if skip_event and skip_event.is_set():
                    skip_event.clear()
                success += 1
                if check_garbled(filepath):
                    garbled_volumes.append(vol)
                    msg_queue.put(("log", "warn", index_str, vol["name"], "偵測到亂碼"))
                else:
                    msg_queue.put(("log", "ok", index_str, vol["name"], ""))
            else:
                skipped = skip_event is not None and skip_event.is_set()
                fail_volumes.append(vol)
                if skipped:
                    skip_event.clear()
                    msg_queue.put(("log", "skip", index_str, vol["name"], "已跳過"))
                else:
                    retry_label = "無限次" if retry_count <= 0 else f"{retry_count}x"
                    msg_queue.put(("log", "fail", index_str, vol["name"], f"retry {retry_label} 失敗"))
        except Exception as e:
            # 單一卷發生非預期錯誤（例如路徑無法寫入）不應讓整批下載卡死
            fail_volumes.append(vol)
            msg_queue.put(("log", "fail", index_str, vol["name"], f"錯誤：{e}"))

    msg_queue.put(("done", success, fail_volumes, garbled_volumes))


def run_repair_all(aid: str, book_name: str, volumes: list[dict],
                   output_dir: str, msg_queue: queue.Queue,
                   retry_count: int = RETRY_COUNT,
                   retry_delay: float = RETRY_DELAY,
                   index_fmt: str = "padded",
                   include_book_name: bool = True,
                   separator: str = " ",
                   skip_event=None) -> None:
    total = len(volumes)
    success = 0
    fail_volumes: list[dict] = []
    garbled_volumes: list[dict] = []
    pad = max(len(str(total)), 2)

    for i, vol in enumerate(volumes, 1):
        msg_queue.put(("progress", i, total, vol["name"]))
        index_str = str(vol["index"]).zfill(pad)
        try:
            filepath = build_filepath(output_dir, book_name, vol["index"], vol["name"], total,
                                      index_fmt, include_book_name, separator)
            result = repair_volume(aid, vol["vid"], filepath, retry_count, retry_delay, skip_event)
            skipped = skip_event is not None and skip_event.is_set()
            if skipped:
                skip_event.clear()
                garbled_volumes.append(vol)
                msg_queue.put(("log", "skip", index_str, vol["name"], "已跳過"))
            elif result is None:
                fail_volumes.append(vol)
                msg_queue.put(("log", "fail", index_str, vol["name"], "修復失敗"))
            elif result is True:
                garbled_volumes.append(vol)
                msg_queue.put(("log", "warn", index_str, vol["name"], "修復後仍有亂碼"))
            else:
                success += 1
                msg_queue.put(("log", "ok", index_str, vol["name"], "已修復"))
        except Exception as e:
            # 單一卷發生非預期錯誤（例如路徑無法寫入）不應讓整批修復卡死
            fail_volumes.append(vol)
            msg_queue.put(("log", "fail", index_str, vol["name"], f"錯誤：{e}"))

    msg_queue.put(("done", success, fail_volumes, garbled_volumes))
