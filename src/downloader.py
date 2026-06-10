import os
import time
import queue
from curl_cffi import requests as cf_requests
from src.config import DOWNLOAD_BASE_URL, RETRY_COUNT, RETRY_DELAY

_session: cf_requests.Session | None = None


def _get_session() -> cf_requests.Session:
    global _session
    if _session is None:
        _session = cf_requests.Session()
    return _session


def download_volume(aid: str, vid: int, filepath: str) -> bool:
    url = f"{DOWNLOAD_BASE_URL}?aid={aid}&vid={vid}&charset=utf-8"
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            resp = _get_session().get(url, impersonate="chrome120", timeout=30)
            resp.raise_for_status()
            # 回應內容不應是 HTML（< 開頭 = 錯誤頁面）
            if len(resp.content) < 50 or resp.content[:5].strip().startswith(b"<"):
                raise ValueError("Response is HTML error page, not TXT")
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(resp.content)
            return True
        except Exception:
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_DELAY)
    return False


def build_filepath(output_dir: str, book_name: str, volume_index: int,
                   volume_name: str, total: int) -> str:
    pad = max(len(str(total)), 2)
    index_str = str(volume_index).zfill(pad)
    safe = lambda s: "".join(c for c in s if c not in r'\/:*?"<>|')
    filename = f"{index_str} {safe(book_name)} {safe(volume_name)}.txt"
    return os.path.join(output_dir, safe(book_name), filename)


def run_download_all(aid: str, book_name: str, volumes: list[dict],
                     output_dir: str, msg_queue: queue.Queue) -> None:
    total = len(volumes)
    success = 0
    fail_volumes: list[dict] = []
    pad = max(len(str(total)), 2)

    for i, vol in enumerate(volumes, 1):
        msg_queue.put(("progress", i, total, vol["name"]))
        filepath = build_filepath(output_dir, book_name, vol["index"], vol["name"], total)
        ok = download_volume(aid, vol["vid"], filepath)
        index_str = str(vol["index"]).zfill(pad)
        if ok:
            success += 1
            msg_queue.put(("log", "ok", index_str, vol["name"], ""))
        else:
            fail_volumes.append(vol)
            msg_queue.put(("log", "fail", index_str, vol["name"], f"retry {RETRY_COUNT}x 失敗"))

    msg_queue.put(("done", success, fail_volumes))
