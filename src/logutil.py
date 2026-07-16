"""執行紀錄（logs/app.log）共用小模組。

主程式（main.py）與爬蟲/下載模組（downloader.py）共用同一個 app.log，
靠來源標籤（任務描述欄位）區分，不分割、不輪替。

規則見 C:\\Users\\CTH\\.claude\\project-rules\\windows-tool.md「執行紀錄」章節：
- 錯誤行只記 exception 類型 + HTTP status code + 重試次數，絕不記 URL / response 全文 / f"...{e}"
- 每次寫入開檔→寫→關檔，不持有 handle（跟 launcher.ps1 共用同一檔案）
"""

import os
import time


def _find_project_root() -> str:
    """往上找 launcher.ps1 所在目錄＝專案根目錄。

    不可寫死 os.path.join(SCRIPT_DIR, "..", "logs")：主程式在根目錄的專案會算到
    專案外層（Documents\\Code\\logs），污染其他專案。用這個函式，主程式在根目錄
    或 src/ 都對，日後把 .py 搬進 src/ 也不會壞。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    d = here
    while True:
        if os.path.exists(os.path.join(d, "launcher.ps1")):
            return d
        parent = os.path.dirname(d)
        if parent == d:      # 找到磁碟根目錄仍沒找到，退回自己所在目錄，至少不寫到專案外
            return here
        d = parent


LOG_DIR = os.path.join(_find_project_root(), "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")


def _write_log(msg: str, level: str = "INFO"):
    """寫一行到 logs/app.log。每次開檔→寫→關檔，不持有 handle（地雷十）"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] [{level:<5}] {msg}\n")
    except OSError:
        pass   # log 掛掉不能拖垮主程式；也涵蓋兩個實例同時跑撞在一起


def _write_log_header(msg: str):
    """任務起始行，唯一有完整日期的行"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} {msg} ===\n")
    except OSError:
        pass


def _extract_status(e: Exception):
    """從 requests/curl_cffi 例外物件取 HTTP status code；取不到就回傳 None。
    絕不從 e 取 URL 或 response 全文。"""
    resp = getattr(e, "response", None)
    return getattr(resp, "status_code", None) if resp is not None else None
