"""GUI 互動路徑的驗收腳本（手動執行，需要網路）。

## 這支腳本驗什麼

用程式驅動**真正的 widget**：建立對話框 → 讀出程式實際算出來的文字 →
呼叫真正的按鈕 callback → 檢查按完之後的狀態。三條路徑：

1. 載入已有檔案的資料夾 → Preview 確認 → 「已有 N 卷」提示與兩個選擇鈕
2. 「更新」的六組分類確認視窗
3. 單卷網址（閱讀器 `?vid=` 與章節頁 `{cid}.htm` 兩種格式）

## 這支腳本驗不到什麼

**視覺層面**——排版、間距、捲動順不順、高 DPI 下會不會擠。那要人眼看。
所以它不能取代 `windows-tool.md` 要求的人工驗收，只能把「邏輯與 callback
有沒有寫錯」這層自動化掉，讓人眼專心看外觀。

## 為什麼不放 tests/

它要連網抓真實目錄，而且會下載檔案到磁碟。`pytest` 那套是純本地、毫秒級的
單元測試，混進來會讓 CI 與日常開發變慢又不穩。

## 用法

    python scripts/gui_acceptance.py --aid 1861 --out "D:\\某個測試資料夾" --setup 10

`--setup N` 會先抓前 N 卷建立「已下載一部分」的情境（路徑 1、2 需要它）。
資料夾已經有檔案的話可以省略。跑完會印 PASS/FAIL 統計，有 FAIL 時 exit 1。

⚠ 視窗全程是隱藏的（`root.withdraw()`），不會跳出來打擾，但**過程中會真的
建立與銷毀 Toplevel**，所以執行時不要同時操作滑鼠鍵盤以免干擾。
"""

from __future__ import annotations

import argparse
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.config import RETRY_COUNT, RETRY_DELAY          # noqa: E402
from src.downloader import run_download_all              # noqa: E402
from src.main import App                                 # noqa: E402
from src.scraper import (                                # noqa: E402
    assign_categories_and_sequence, fetch_catalog, find_volume_by_cid,
    parse_book_title, parse_cid_from_url, parse_vid_from_url, parse_volumes,
)
from src.sitedata import DEFAULT_SIDE_KEYWORDS           # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASSED if cond else FAILED).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  → {detail}" if detail else ""),
          flush=True)


def walk(widget, kind) -> list:
    """遞迴收集某型別的子元件。對話框是動態組出來的，只能用走訪的方式找。"""
    found = []
    for child in widget.winfo_children():
        if isinstance(child, kind):
            found.append(child)
        found += walk(child, kind)
    return found


def dialogs(root) -> list:
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]


def button(widget, text):
    hits = [b for b in walk(widget, ttk.Button) if str(b["text"]) == text]
    return hits[0] if hits else None


def labels_text(widget) -> str:
    return " ".join(str(lbl["text"]) for lbl in walk(widget, ttk.Label))


def setup_partial(aid, book, volumes, out_dir, count):
    """先抓前 count 卷，建立「已下載一部分」的情境。"""
    subset = volumes[:count]
    print(f"[setup] 下載前 {len(subset)} 卷到 {out_dir} ...", flush=True)
    q: queue.Queue = queue.Queue()
    threading.Thread(
        target=run_download_all,
        args=(aid, book, subset, out_dir, q, RETRY_COUNT, RETRY_DELAY,
              "padded", True, " "),
        kwargs={"convert_traditional": True},
        daemon=True,
    ).start()
    start = time.time()
    while True:
        msg = q.get(timeout=1800)
        if msg[0] == "done":
            print(f"[setup] 完成 {msg[1]}/{len(subset)} 卷，"
                  f"耗時 {int(time.time() - start)} 秒", flush=True)
            return len(subset)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aid", required=True, help="書號，例如 1861")
    ap.add_argument("--out", required=True, help="測試用輸出資料夾")
    ap.add_argument("--setup", type=int, default=0,
                    help="先抓前 N 卷建立「已下載一部分」的情境（預設 0 = 不抓）")
    ap.add_argument("--probe-index", type=int, default=3,
                    help="拿第幾卷測單卷網址（1-based，預設 3）")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    soup = fetch_catalog(args.aid)
    book = parse_book_title(soup)
    volumes = assign_categories_and_sequence(parse_volumes(soup), DEFAULT_SIDE_KEYWORDS)
    print(f"書名：{book}｜{len(volumes)} 卷", flush=True)

    have_count = 0
    if args.setup:
        have_count = setup_partial(args.aid, book, volumes, args.out, args.setup)
    else:
        have_count = len([f for f in os.listdir(args.out) if f.endswith(".txt")])
    need_count = len(volumes) - have_count

    root = tk.Tk()
    root.withdraw()
    app = App(root)
    app._path_var.set(args.out)
    app._aid = args.aid

    print("\n① 載入已有檔案的資料夾 → Preview → 已有檔案提示", flush=True)
    app._open_preview_dialog(book, volumes)
    root.update()
    preview = dialogs(root)[-1]
    check("Preview 標題列出現書名", "書名" in labels_text(preview))
    confirm = button(preview, "確認")
    check("Preview 有「確認」按鈕", confirm is not None)
    if confirm:
        confirm.invoke()
        root.update()

    opened = dialogs(root)
    if have_count:
        check("跳出「已有檔案」提示", bool(opened))
        if opened:
            dlg = opened[-1]
            msg = labels_text(dlg)
            print(f"        提示文字：{msg}", flush=True)
            check(f"提示卷數為實際檔案數（共 {have_count} 卷）", f"共 {have_count} 卷" in msg)
            check(f"提示需要下載 {need_count} 卷", str(need_count) in msg)
            names = [str(b["text"]) for b in walk(dlg, ttk.Button)]
            check("兩個選擇鈕都在", names == ["只抓缺的與新的", "全部重抓覆蓋"], str(names))
            only = button(dlg, "只抓缺的與新的")
            if only:
                only.invoke()
                root.update()
                picked = [v for v, var in zip(app._volumes, app._check_vars) if var.get()]
                check(f"按「只抓缺的與新的」後勾 {need_count} 卷",
                      len(picked) == need_count, f"實際 {len(picked)}")
    else:
        check("資料夾沒有檔案時不跳提示（維持既有行為）", not opened)

    print("\n② 更新 → 六組分類確認視窗", flush=True)
    plan = app._make_plan(volumes, args.out)
    app._open_update_dialog(plan, len(volumes))
    root.update()
    upd = dialogs(root)[-1]
    boxes = walk(upd, ttk.Checkbutton)
    checked = sum(1 for b in boxes if b.instate(["selected"]))
    expected = sum(len(plan[g]) for g in ("new", "incomplete"))
    check(f"勾選項總數等於卷數（{len(volumes)}）", len(boxes) == len(volumes),
          f"實際 {len(boxes)}")
    check(f"預設勾 new+incomplete（{expected} 卷）", checked == expected,
          f"實際 {checked}")
    sent: dict = {}
    app._start_download = lambda sel: sent.update(n=len(sel))
    dl = button(upd, "下載選取")
    check("更新視窗有「下載選取」按鈕", dl is not None)
    if dl:
        dl.invoke()
        root.update()
        check(f"按下後送出 {expected} 卷", sent.get("n") == expected,
              f"實際 {sent.get('n')}")

    print("\n③ 單卷網址（兩種格式）", flush=True)
    probe = volumes[min(args.probe_index, len(volumes)) - 1]
    cases = [
        ("閱讀器格式",
         f"https://www.wenku8.net/modules/article/reader.php?aid={args.aid}&vid={probe['vid']}"),
        ("章節頁格式",
         f"https://www.wenku8.net/novel/1/{args.aid}/{probe['first_cid']}.htm"),
    ]
    for label, url in cases:
        app.url_var.set(url)
        root.update()
        hint = str(app._url_hint["text"])
        print(f"  【{label}】{hint}", flush=True)
        check(f"{label} 即時提示辨識為單卷", "單卷" in hint)

        vid = parse_vid_from_url(url)
        if vid is None:
            hit = find_volume_by_cid(volumes, parse_cid_from_url(url))
            vid = hit["vid"] if hit else None
        check(f"{label} 解析到正確的卷", vid == probe["vid"])

        app._reset_book_state()
        app._aid = args.aid
        app._open_preview_dialog(book, volumes, only_vid=vid)
        root.update()
        pv = dialogs(root)[-1]
        check(f"{label} Preview 標示只載入 1 卷", "只載入 1 卷" in labels_text(pv))
        btn = button(pv, "確認")
        if btn:
            btn.invoke()
            root.update()
        check(f"{label} 只帶入 1 卷", len(app._volumes) == 1)
        if app._volumes:
            vol = app._volumes[0]
            # 這條是重點：只拿一卷去 resequence 會被編成 1，檔名就跟其他卷對不上
            check(f"{label} 編號沿用整份目錄（{probe['seq_index']}，非 1）",
                  vol["seq_index"] == probe["seq_index"],
                  f"實際 {vol['seq_index']}/{vol['seq_total']}")
        check(f"{label} 書名列標示（單卷）", "（單卷）" in str(app.title_label["text"]))

    root.destroy()
    print(f"\n結果：PASS {len(PASSED)} / FAIL {len(FAILED)}", flush=True)
    for name in FAILED:
        print("  未通過：", name, flush=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
