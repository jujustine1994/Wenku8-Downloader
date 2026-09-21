"""manifest.py — 輸出資料夾的下載紀錄（.wenku8.json）讀寫與比對。

記錄每一卷的識別碼、下載時間、檔案指紋、簡繁狀態與完整性判定結果，
「更新」流程靠它決定哪幾卷要抓、哪幾卷可以跳過。

## 依賴方向

只 import stdlib 與 `src.verify`。**不可以 import `downloader`**——
`downloader` 會 import 這個模組寫紀錄，反過來 import 就是循環。
需要算檔名的地方一律由呼叫端傳 `build_path(vol) -> str` callable 進來
（呼叫端用 `functools.partial` 包 `downloader.build_filepath`）。

## 書本層級欄位

每本書除了 `volumes`，還記 `aid`（書號）、`book_name`、`source_url`（使用者當初
貼的網址）、`updated_at`。有了前三個，資料夾單獨存在時光看這個檔就知道是哪本書、
從哪裡抓的，不用回頭猜。寫入者是 `record_book_meta()`，由 `main.py` 呼叫——
知道網址的是 UI，downloader 只負責卷。

## 三個容易出錯的欄位

- **`vid` 當 key，`cids` 記內容組成。** vid 不受改名、換編號格式影響；
  `cids` 是為了看出「站方補章／重新分卷」——章節組成變了，即使檔案驗得過
  也該讓使用者知道可以重抓。
- **`size` 一定要取寫檔完成後的 `os.path.getsize()` 實測值。**
  `downloader` 寫檔是 `open(..., "w", encoding="utf-8")`，沒有指定
  `newline=""`，Windows text mode 會把 `\n` 翻成 `\r\n`，磁碟 bytes
  ≠ `len(text.encode("utf-8"))`。用記憶體算的值會讓每一卷快篩都判定
  「檔案被動過」而全部重抓。
- **`script`**：`"zh-hant"`（下載時開了簡轉繁）／`"zh-hans"`（關著）／
  `"unknown"`（按檔名回推來的舊檔，不做簡繁偵測，也不觸發重抓）。

## 編碼（三條都實際會咬人）

- 寫：`encoding="utf-8"` + `newline="\\n"` + `ensure_ascii=False`，**不加 BOM**。
  BOM 是 `launcher.ps1` 那種 PS1 檔的規矩，JSON 加了會讓別的工具解析失敗。
- 讀：`encoding="utf-8-sig"`，萬一被記事本編輯過塞了 BOM 也吃得下。
- 壞掉不 raise：回空骨架讓流程退回 `rebuild_from_files()`。

⚠ 這個檔裡的 key 與 `status`／`script`／`reason` 的值都會落檔並拿去比對，
是**資料**不是介面文字，一條都不進 `src/locales/`。
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from src.verify import verify_file

MANIFEST_FILENAME = ".wenku8.json"
SCHEMA_VERSION = 1

SCRIPT_TRADITIONAL = "zh-hant"
SCRIPT_SIMPLIFIED = "zh-hans"
SCRIPT_UNKNOWN = "unknown"

# plan_update() 的分組名稱。也是 UI 顯示分組的排列順序依據。
PLAN_GROUPS = ("new", "incomplete", "changed", "chapters_changed",
               "script_mismatch", "ok")
# 預設勾選的組：另外三組是「使用者可能有意為之」的情況，不預設覆蓋既有檔案
PLAN_DEFAULT_CHECKED = ("new", "incomplete")


def path_for(output_dir: str) -> str:
    return os.path.join(output_dir, MANIFEST_FILENAME)


def empty() -> dict:
    return {"version": SCHEMA_VERSION, "books": {}}


def load(output_dir: str) -> dict:
    """讀 manifest。不存在、壞掉、版本不認得，一律回空骨架，不 raise。"""
    try:
        with open(path_for(output_dir), encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return empty()
    if not isinstance(data, dict) or data.get("version") != SCHEMA_VERSION:
        return empty()
    if not isinstance(data.get("books"), dict):
        return empty()
    return data


def save(output_dir: str, data: dict) -> bool:
    """寫 manifest。寫不進去回 False，不 raise——紀錄掛掉不能拖垮下載。"""
    try:
        os.makedirs(output_dir, exist_ok=True)
        with open(path_for(output_dir), "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def get_book(data: dict, aid: str) -> dict:
    """取某本書的區塊，沒有就建一個空的（會就地寫進 data）。"""
    books = data.setdefault("books", {})
    return books.setdefault(str(aid), {"aid": str(aid), "book_name": "",
                                       "source_url": "", "updated_at": "",
                                       "volumes": {}})


def record_book_meta(output_dir: str, aid: str, book_name: str,
                     source_url: str = "") -> bool:
    """記下書本層級的來源資訊：書號與使用者當初貼的網址。

    刻意跟 `record_volume()` 分開、由 `main.py` 在載入目錄後呼叫一次，而不是
    把 source_url 一路塞進 `run_download_all()` 的參數列：知道網址的是 UI，
    downloader 只負責卷。這樣 downloader 的簽章不用再長一截。

    source_url 傳空字串時**不覆蓋**既有值——後續的下載/修復流程不知道網址，
    不能把先前記好的洗掉。
    """
    data = load(output_dir)
    book = get_book(data, aid)
    book["aid"] = str(aid)
    if book_name:
        book["book_name"] = book_name
    if source_url:
        book["source_url"] = source_url
    book["updated_at"] = _now()
    return save(output_dir, data)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _entry(vol: dict, filepath: str, verdict: dict, script: str,
           downloaded_at: str) -> dict:
    chapters = vol.get("chapters") or []
    try:
        size = os.path.getsize(filepath)
    except OSError:
        size = 0
    return {
        "vid": vol["vid"],
        "name": vol.get("name", ""),
        "category": vol.get("category", "main"),
        "seq_index": vol.get("seq_index", vol.get("index", 0)),
        "cids": [c["cid"] for c in chapters],
        "chapter_count": len(chapters),
        "filename": os.path.basename(filepath),
        "downloaded_at": downloaded_at,
        "size": size,
        "chars": verdict.get("chars", 0),
        "script": script,
        "status": verdict.get("status", "suspect"),
        "reason": verdict.get("reason", ""),
        "anchor_hits": verdict.get("anchor_hits", 0),
        "anchor_total": verdict.get("anchor_total", 0),
    }


def record_volume(output_dir: str, aid: str, book_name: str, vol: dict,
                  filepath: str, verdict: dict, script: str) -> bool:
    """寫入單卷紀錄。每卷開檔→寫→關檔，不持有 handle（同 logs/app.log 的規矩）。

    累積到整批結束才寫的話，中途關視窗就整批丟失，而那正是最需要紀錄的時候。
    """
    data = load(output_dir)
    book = get_book(data, aid)
    book["aid"] = str(aid)
    book["book_name"] = book_name
    book["updated_at"] = _now()
    book.setdefault("volumes", {})[str(vol["vid"])] = _entry(
        vol, filepath, verdict, script, _now()
    )
    return save(output_dir, data)


def median_chars(data: dict, aid: str) -> int | None:
    """同一本書已判定 complete 的卷字數中位數，給沒有錨點的卷當字數基準。

    一卷都還沒有時回 None——此時 verify 只比 FALLBACK_CHARS_FLOOR 絕對下限。
    """
    book = data.get("books", {}).get(str(aid))
    if not book:
        return None
    values = sorted(
        v["chars"] for v in book.get("volumes", {}).values()
        if v.get("status") == "complete" and v.get("chars")
    )
    if not values:
        return None
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) // 2


def rebuild_from_files(output_dir: str, aid: str, book_name: str,
                       volumes: list[dict], build_path) -> dict:
    """沒有 manifest（或壞掉）時按檔名回推建一份，**不重抓**。

    `script` 一律填 "unknown"：用 OpenCC 反推原文是簡是繁很容易誤判（本來就是
    繁體的文字轉完也一樣），誤判代價是幾十卷白抓一遍。unknown 不觸發重抓。

    已知限制：檔名照**目前**命名設定算。下載後改過命名設定的話舊檔對不上，
    會被當成沒下載過（跟 downloader.scan_existing_volumes 同一個限制）。
    """
    data = load(output_dir)
    book = get_book(data, aid)
    book["aid"] = str(aid)
    book["book_name"] = book_name
    book["updated_at"] = _now()
    vols = book.setdefault("volumes", {})

    for vol in volumes:
        key = str(vol["vid"])
        if key in vols:
            continue
        filepath = build_path(vol)
        if not os.path.isfile(filepath):
            continue
        verdict = verify_file(filepath, vol.get("chapters"), None, SCRIPT_UNKNOWN)
        if verdict is None:
            continue
        try:
            mtime = datetime.fromtimestamp(
                os.path.getmtime(filepath)).isoformat(timespec="seconds")
        except OSError:
            mtime = ""
        vols[key] = _entry(vol, filepath, verdict, SCRIPT_UNKNOWN, mtime)

    save(output_dir, data)
    return data


def plan_update(volumes: list[dict], book_entry: dict, build_path,
                want_script: str, median: int | None = None) -> dict:
    """比對卷列表與 manifest／磁碟，把每一卷歸到剛好一組。純比對，不發網路請求。

    兩層驗證：
      1. 快篩——`os.stat` 比 size，相符且紀錄是 complete 就直接過，不讀內容
      2. 重驗——快篩不過／沒紀錄／狀態不是 complete 才讀全文跑 verify

    單卷 300KB 讀+掃約 5–10ms，所以快篩是省心不是省時。
    """
    plan: dict[str, list[dict]] = {g: [] for g in PLAN_GROUPS}
    records = (book_entry or {}).get("volumes", {}) or {}

    for vol in volumes:
        rec = records.get(str(vol["vid"]))
        filepath = build_path(vol)
        exists = os.path.isfile(filepath)

        if not exists:
            plan["new" if rec is None else "incomplete"].append(vol)
            continue

        if rec is None:
            # 檔案在但沒紀錄（manifest 剛壞掉重建、或使用者自己放進來的）→ 現場驗
            verdict = verify_file(filepath, vol.get("chapters"), median,
                                  SCRIPT_UNKNOWN)
            group = "ok" if verdict and verdict["status"] == "complete" else "incomplete"
            plan[group].append(vol)
            continue

        if rec.get("status") != "complete":
            plan["incomplete"].append(vol)
            continue

        try:
            size = os.path.getsize(filepath)
        except OSError:
            plan["incomplete"].append(vol)
            continue
        if rec.get("size") and size != rec["size"]:
            plan["changed"].append(vol)
            continue

        chapters = vol.get("chapters") or []
        rec_cids = rec.get("cids") or []
        if chapters and rec_cids and {c["cid"] for c in chapters} != set(rec_cids):
            plan["chapters_changed"].append(vol)
            continue

        rec_script = rec.get("script", SCRIPT_UNKNOWN)
        if want_script and rec_script not in (SCRIPT_UNKNOWN, "", None, want_script):
            plan["script_mismatch"].append(vol)
            continue

        plan["ok"].append(vol)

    return plan


def script_for(convert_traditional: bool) -> str:
    return SCRIPT_TRADITIONAL if convert_traditional else SCRIPT_SIMPLIFIED
