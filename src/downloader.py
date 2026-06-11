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
                    retry_delay: float = RETRY_DELAY) -> bool:
    url = f"{DOWNLOAD_BASE_URL}?aid={aid}&vid={vid}&charset=utf-8"
    for attempt in range(1, retry_count + 1):
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
                time.sleep(retry_delay)
    return False


def check_garbled(filepath: str) -> bool:
    with open(filepath, encoding="utf-8") as f:
        return "�" in f.read()


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
                     separator: str = " ") -> None:
    total = len(volumes)
    success = 0
    fail_volumes: list[dict] = []
    pad = max(len(str(total)), 2)

    for i, vol in enumerate(volumes, 1):
        msg_queue.put(("progress", i, total, vol["name"]))
        filepath = build_filepath(output_dir, book_name, vol["index"], vol["name"], total,
                                  index_fmt, include_book_name, separator)
        ok = download_volume(aid, vol["vid"], filepath, retry_count, retry_delay)
        index_str = str(vol["index"]).zfill(pad)
        if ok:
            success += 1
            msg_queue.put(("log", "ok", index_str, vol["name"], ""))
        else:
            fail_volumes.append(vol)
            msg_queue.put(("log", "fail", index_str, vol["name"], f"retry {retry_count}x 失敗"))

    msg_queue.put(("done", success, fail_volumes))
