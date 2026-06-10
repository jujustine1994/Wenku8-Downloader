import os
import time
import queue
import requests
from src.config import DOWNLOAD_BASE_URL, HEADERS, RETRY_COUNT, RETRY_DELAY


def download_volume(aid: str, vid: int, filepath: str) -> bool:
    url = f"{DOWNLOAD_BASE_URL}?aid={aid}&vid={vid}&charset=utf-8"
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            if len(resp.content) < 50:
                raise ValueError("Response too short — likely an error page")
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
    fail_list = []
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
            fail_list.append(vol["name"])
            msg_queue.put(("log", "fail", index_str, vol["name"], "retry 3x 失敗"))

    msg_queue.put(("done", success, fail_list))
