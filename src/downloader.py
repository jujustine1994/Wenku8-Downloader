import os
import time
import queue
from curl_cffi import requests as cf_requests
from src.config import DOWNLOAD_BASE_URL, RETRY_COUNT, RETRY_DELAY
from src.converter import convert_to_traditional

_session: cf_requests.Session | None = None


def _get_session() -> cf_requests.Session:
    global _session
    if _session is None:
        _session = cf_requests.Session()
    return _session


def download_volume(aid: str, vid: int, filepath: str,
                    retry_count: int = RETRY_COUNT,
                    retry_delay: float = RETRY_DELAY,
                    skip_event=None) -> bool:
    url = f"{DOWNLOAD_BASE_URL}?aid={aid}&vid={vid}&charset=utf-8"
    for attempt in range(1, retry_count + 1):
        if skip_event and skip_event.is_set():
            return False
        try:
            resp = _get_session().get(url, impersonate="chrome120", timeout=30)
            resp.raise_for_status()
            # 回應內容不應是 HTML（< 開頭 = 錯誤頁面）
            if len(resp.content) < 50 or resp.content[:5].strip().startswith(b"<"):
                raise ValueError("Response is HTML error page, not TXT")
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            text = resp.content.decode("utf-8", errors="replace")
            converted = convert_to_traditional(text)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(converted)
            return True
        except Exception:
            if attempt < retry_count:
                if skip_event and skip_event.is_set():
                    return False
                time.sleep(retry_delay)
    return False


def check_garbled(filepath: str) -> bool:
    with open(filepath, encoding="utf-8") as f:
        return "�" in f.read()


def repair_volume(aid: str, vid: int, filepath: str,
                  retry_count: int = RETRY_COUNT,
                  retry_delay: float = RETRY_DELAY) -> bool | None:
    """
    Returns False = 修復成功（無亂碼）
            True  = 修復後仍有亂碼
            None  = 網路失敗
    """
    def _try_download(charset: str) -> bytes | None:
        url = f"{DOWNLOAD_BASE_URL}?aid={aid}&vid={vid}&charset={charset}"
        for attempt in range(1, retry_count + 1):
            try:
                resp = _get_session().get(url, impersonate="chrome120", timeout=30)
                resp.raise_for_status()
                if len(resp.content) < 50 or resp.content[:5].strip().startswith(b"<"):
                    raise ValueError("Response is HTML error page")
                return resp.content
            except Exception:
                if attempt < retry_count:
                    time.sleep(retry_delay)
        return None

    utf8_bytes = _try_download("utf-8")
    if utf8_bytes is None:
        return None

    utf8_text = utf8_bytes.decode("utf-8", errors="replace")
    best_text = utf8_text

    if "�" in utf8_text:
        gbk_bytes = _try_download("gbk")
        if gbk_bytes is not None:
            gbk_text = gbk_bytes.decode("gbk", errors="replace")
            if gbk_text.count("�") < utf8_text.count("�"):
                best_text = gbk_text

    converted = convert_to_traditional(best_text)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(converted)

    return True if "�" in converted else False


def build_filepath(output_dir: str, book_name: str, volume_index: int,
                   volume_name: str, total: int,
                   index_fmt: str = "padded",
                   include_book_name: bool = True,
                   separator: str = " ") -> str:
    pad = max(len(str(total)), 2)
    safe = lambda s: "".join(c for c in s if c not in r'\/:*?"<>|')
    parts = []
    if index_fmt == "padded":
        parts.append(str(volume_index).zfill(pad))
    elif index_fmt == "plain":
        parts.append(str(volume_index))
    if include_book_name:
        parts.append(safe(book_name))
    parts.append(safe(volume_name))
    safe_sep = safe(separator) or " "
    filename = safe_sep.join(parts) + ".txt"
    return os.path.join(output_dir, safe(book_name), filename)


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
        filepath = build_filepath(output_dir, book_name, vol["index"], vol["name"], total,
                                  index_fmt, include_book_name, separator)
        ok = download_volume(aid, vol["vid"], filepath, retry_count, retry_delay, skip_event)
        index_str = str(vol["index"]).zfill(pad)
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
                msg_queue.put(("log", "fail", index_str, vol["name"], f"retry {retry_count}x 失敗"))

    msg_queue.put(("done", success, fail_volumes, garbled_volumes))


def run_repair_all(aid: str, book_name: str, volumes: list[dict],
                   output_dir: str, msg_queue: queue.Queue,
                   retry_count: int = RETRY_COUNT,
                   retry_delay: float = RETRY_DELAY,
                   index_fmt: str = "padded",
                   include_book_name: bool = True,
                   separator: str = " ") -> None:
    total = len(volumes)
    success = 0
    fail_volumes: list[dict] = []
    garbled_volumes: list[dict] = []
    pad = max(len(str(total)), 2)

    for i, vol in enumerate(volumes, 1):
        msg_queue.put(("progress", i, total, vol["name"]))
        filepath = build_filepath(output_dir, book_name, vol["index"], vol["name"], total,
                                  index_fmt, include_book_name, separator)
        index_str = str(vol["index"]).zfill(pad)
        result = repair_volume(aid, vol["vid"], filepath, retry_count, retry_delay)
        if result is None:
            fail_volumes.append(vol)
            msg_queue.put(("log", "fail", index_str, vol["name"], "修復失敗"))
        elif result is True:
            garbled_volumes.append(vol)
            msg_queue.put(("log", "warn", index_str, vol["name"], "修復後仍有亂碼"))
        else:
            success += 1
            msg_queue.put(("log", "ok", index_str, vol["name"], "已修復"))

    msg_queue.put(("done", success, fail_volumes, garbled_volumes))
