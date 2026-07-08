# 統一「重試/修復」懶人流程 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan (tasks are tightly coupled within one file's state machine — not independent, so subagent-driven-development's fresh-subagent-per-task model doesn't fit; execute inline in one continuous pass instead). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「重試失敗」「修復亂碼」兩顆按鈕、兩份清單（`_fail_volumes`/`_garbled_volumes`）合併成一個「重試/修復」按鈕與 `_recovery_volumes` 清單，一律用 `run_repair_all`（已內建網路重試+編碼修復）處理。

**Architecture:** 純 `main.py` GUI 狀態機重構，`downloader.py`/`scraper.py` 不動。詳見 `docs/superpowers/specs/2026-07-09-unified-recovery-design.md`。

**Tech Stack:** Python 3.10+, tkinter, pytest（本次無新的可單元測試邏輯，回歸測試 + 程式化驗證）

## Global Constraints

- `downloader.py`、`scraper.py` 不得修改——`run_repair_all` 已是完整超集，直接重用
- 初次下載（`_on_download`／`run_download_all`）流程不變，只有「下載完成後怎麼補救」這段被合併
- `_on_recover()` 不顯示確認對話框（原 `_on_repair` 的 `messagebox.askokcancel` 移除）
- 現有跨批次合併邏輯（用 `_last_batch_vids` 排除本批次涵蓋到的卷再接上新結果）必須保留，只是從兩份清單各自合併改成單一清單合併

---

## File Map

| 動作 | 檔案 |
|------|------|
| Modify | `src/main.py` — 狀態欄位、按鈕、`_on_download`、合併 `_on_retry`+`_on_repair`→`_on_recover`、`_manage_fail_dialog`→`_manage_recovery_dialog`、`"done"` handler |
| Modify | `docs/CHANGELOG.md`、`docs/TODO.md` |

---

## Task 1：合併狀態、按鈕、所有相關 handler（單一連續改動）

**Files:**
- Modify: `src/main.py`

**Interfaces:**
- Consumes: 既有 `run_repair_all`（downloader.py，簽名不變）
- Produces: `self._recovery_volumes: list`、`self.btn_recover`、`self._on_recover()`、`self._manage_recovery_dialog()`

### Step 1：`__init__` 狀態欄位

找到：
```python
        self._fail_volumes: list = []
```
（約第 113 行）改為：
```python
        self._recovery_volumes: list = []
```

找到：
```python
        self._garbled_volumes: list = []
        self._last_batch_vids: set = set()
```
（約第 126-127 行）刪除 `self._garbled_volumes: list = []` 這行，保留 `self._last_batch_vids: set = set()`。

### Step 2：按鈕定義（`_build_ui`）

找到（約第 242-253 行）：
```python
        self.btn_retry = ttk.Button(
            btn_row, text="重試失敗", command=self._on_retry, width=10, state="disabled"
        )
        self.btn_retry.pack(side="right", ipady=4, padx=(0, 6))
        self.btn_manage = ttk.Button(
            btn_row, text="管理", command=self._manage_fail_dialog, width=5, state="disabled"
        )
        self.btn_manage.pack(side="right", ipady=4, padx=(0, 2))
        self.btn_repair = ttk.Button(
            btn_row, text="修復亂碼", command=self._on_repair, width=10, state="disabled"
        )
        self.btn_repair.pack(side="right", ipady=4, padx=(0, 6))
```

改為（移除 `btn_repair`，`btn_retry` 改名 `btn_recover` 並改文字/command）：
```python
        self.btn_recover = ttk.Button(
            btn_row, text="重試/修復", command=self._on_recover, width=10, state="disabled"
        )
        self.btn_recover.pack(side="right", ipady=4, padx=(0, 6))
        self.btn_manage = ttk.Button(
            btn_row, text="管理", command=self._manage_recovery_dialog, width=5, state="disabled"
        )
        self.btn_manage.pack(side="right", ipady=4, padx=(0, 2))
```

### Step 3：`_reset_book_state()`

找到：
```python
    def _reset_book_state(self):
        """清空跟目前這本書相關的狀態：卷列表、失敗/亂碼清單與對應按鈕。
        載入新書、或 Preview 視窗取消時共用，避免舊書的清單/按鈕狀態殘留到下一本書。"""
        self._fail_volumes = []
        self._garbled_volumes = []
        self._build_checkbox_list([])
        self.btn_download.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
        self.btn_retry.config(state="disabled", text="重試失敗")
        self.btn_manage.config(state="disabled")
        self.btn_repair.config(state="disabled", text="修復亂碼")
```

改為：
```python
    def _reset_book_state(self):
        """清空跟目前這本書相關的狀態：卷列表、待處理清單與對應按鈕。
        載入新書、或 Preview 視窗取消時共用，避免舊書的清單/按鈕狀態殘留到下一本書。"""
        self._recovery_volumes = []
        self._build_checkbox_list([])
        self.btn_download.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
        self.btn_recover.config(state="disabled", text="重試/修復")
        self.btn_manage.config(state="disabled")
```

### Step 4：`_on_download()`

找到：
```python
        self._repair_mode = False
        self._last_batch_vids = {v["vid"] for v in selected}
        self._skip_event.clear()
        self.btn_repair.config(state="disabled", text="修復亂碼")
        self.btn_manage.config(state="disabled")
```

改為：
```python
        self._repair_mode = False
        self._last_batch_vids = {v["vid"] for v in selected}
        self._skip_event.clear()
        self.btn_recover.config(state="disabled", text="重試/修復")
        self.btn_manage.config(state="disabled")
```

### Step 5：合併 `_on_retry`＋`_on_repair` → `_on_recover`

找到整個 `_on_retry` 方法：
```python
    def _on_retry(self):
        if not self._fail_volumes:
            return
        output_dir = self._ensure_output_dir()
        if output_dir is None:
            return
        vols = list(self._fail_volumes)
        self._fail_volumes = []
        self._last_batch_vids = {v["vid"] for v in vols}
        self.btn_retry.config(state="disabled", text="重試失敗")
        self.btn_manage.config(state="disabled")
        self.btn_repair.config(state="disabled", text="修復亂碼")
        self._repair_mode = False
        self._skip_event.clear()
        self.btn_skip.config(state="normal")
        self.btn_download.config(state="disabled")
        self.btn_load.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"\n── 重試 {len(vols)} 卷 ──\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = len(vols)
        self._set_status(f"重試中... 共 {len(vols)} 卷", "info")
        threading.Thread(
            target=run_download_all,
            args=(self._aid, self._book_name, vols, output_dir, self.msg_queue,
                  self._retry_count, self._retry_delay,
                  self._fname_index, self._fname_book_name, self._fname_separator),
            kwargs={"skip_event": self._skip_event},
            daemon=True,
        ).start()

    def _on_repair(self):
        if not self._garbled_volumes:
            return
        vols = list(self._garbled_volumes)
        names = "\n".join(f"  · {v['name']}" for v in vols)
        if not messagebox.askokcancel(
            "亂碼修復",
            f"以下 {len(vols)} 卷偵測到亂碼：\n{names}\n\n嘗試換編碼修復？"
        ):
            return
        output_dir = self._ensure_output_dir()
        if output_dir is None:
            return
        self._garbled_volumes = []
        self._last_batch_vids = {v["vid"] for v in vols}
        self._repair_mode = True
        self._skip_event.clear()
        self.btn_repair.config(state="disabled", text="修復亂碼")
        self.btn_retry.config(state="disabled", text="重試失敗")
        self.btn_manage.config(state="disabled")
        self.btn_download.config(state="disabled")
        self.btn_load.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
        self.btn_skip.config(state="normal")
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"\n── 修復亂碼 {len(vols)} 卷 ──\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = len(vols)
        self._set_status(f"修復中... 共 {len(vols)} 卷", "info")
        threading.Thread(
            target=run_repair_all,
            args=(self._aid, self._book_name, vols, output_dir, self.msg_queue,
                  self._retry_count, self._retry_delay,
                  self._fname_index, self._fname_book_name, self._fname_separator),
            kwargs={"skip_event": self._skip_event},
            daemon=True,
        ).start()
```

改為單一 `_on_recover` 方法（沒有確認對話框，一律呼叫 `run_repair_all`）：
```python
    def _on_recover(self):
        if not self._recovery_volumes:
            return
        output_dir = self._ensure_output_dir()
        if output_dir is None:
            return
        vols = list(self._recovery_volumes)
        self._recovery_volumes = []
        self._last_batch_vids = {v["vid"] for v in vols}
        self._repair_mode = True
        self._skip_event.clear()
        self.btn_recover.config(state="disabled", text="重試/修復")
        self.btn_manage.config(state="disabled")
        self.btn_download.config(state="disabled")
        self.btn_load.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
        self.btn_skip.config(state="normal")
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"\n── 重試/修復 {len(vols)} 卷 ──\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = len(vols)
        self._set_status(f"處理中... 共 {len(vols)} 卷", "info")
        threading.Thread(
            target=run_repair_all,
            args=(self._aid, self._book_name, vols, output_dir, self.msg_queue,
                  self._retry_count, self._retry_delay,
                  self._fname_index, self._fname_book_name, self._fname_separator),
            kwargs={"skip_event": self._skip_event},
            daemon=True,
        ).start()
```

**注意**：`messagebox` import 可能在其他地方也有用到（例如未來的對話框），先用 `grep -n "messagebox\." src/main.py` 確認移除確認對話框後這個 import 是否還有其他用途，若沒有其他用途則不要移除 import（避免無關改動），若確認完全沒用到才移除 `from tkinter import ttk, scrolledtext, messagebox` 裡的 `messagebox`。

### Step 6：`_manage_fail_dialog` → `_manage_recovery_dialog`

找到整個 `_manage_fail_dialog` 方法（含內部的 `_apply`），把方法名稱、標題、內部變數名稱、`self._fail_volumes` 全部改成對應的 `_recovery_volumes` 版本：

找到：
```python
    def _manage_fail_dialog(self):
        if not self._fail_volumes:
            return
        fail_list = list(self._fail_volumes)
        win = tk.Toplevel(self.root)
        win.title("管理失敗卷")
```
改為：
```python
    def _manage_recovery_dialog(self):
        if not self._recovery_volumes:
            return
        fail_list = list(self._recovery_volumes)
        win = tk.Toplevel(self.root)
        win.title("管理待處理卷")
```

（`fail_list` 這個區域變數名稱可以保留不用全部重新命名，減少不必要的 diff——只要它裝的是 `self._recovery_volumes` 的複本即可，語意上代表「這次要處理的清單」）

找到 `_apply()` 內部：
```python
        def _apply():
            kept = [v for v, var in zip(fail_list, check_vars) if var.get()]
            self._fail_volumes = kept
            n = len(kept)
            if n:
                self.btn_retry.config(state="normal", text=f"重試 {n} 卷失敗")
                self.btn_manage.config(state="normal")
            else:
                self.btn_retry.config(state="disabled", text="重試失敗")
                self.btn_manage.config(state="disabled")
            win.destroy()
```
改為：
```python
        def _apply():
            kept = [v for v, var in zip(fail_list, check_vars) if var.get()]
            self._recovery_volumes = kept
            n = len(kept)
            if n:
                self.btn_recover.config(state="normal", text=f"重試/修復 {n} 卷")
                self.btn_manage.config(state="normal")
            else:
                self.btn_recover.config(state="disabled", text="重試/修復")
                self.btn_manage.config(state="disabled")
            win.destroy()
```

### Step 7：`"done"` 訊息 handler

找到：
```python
                elif kind == "done":
                    _, success_count, fail_volumes, garbled_volumes = msg
                    batch_fail_count = len(fail_volumes)
                    batch_garbled_count = len(garbled_volumes)
                    if self._repair_mode:
                        total = success_count + batch_fail_count + batch_garbled_count
                    else:
                        total = success_count + batch_fail_count
                    # 合併而非覆蓋：保留其他批次尚未解決的失敗/亂碼卷，只更新本批次涵蓋到的卷
                    attempted = self._last_batch_vids
                    self._fail_volumes = [
                        v for v in self._fail_volumes if v["vid"] not in attempted
                    ] + fail_volumes
                    self._garbled_volumes = [
                        v for v in self._garbled_volumes if v["vid"] not in attempted
                    ] + garbled_volumes
                    fail_count = len(self._fail_volumes)
                    garbled_count = len(self._garbled_volumes)
                    self.btn_load.config(state="normal")
                    self.btn_download.config(state="normal")
                    self.btn_select_all.config(state="normal")
                    self.btn_deselect_all.config(state="normal")
                    self.btn_skip.config(state="disabled")
                    if fail_count:
                        self.btn_retry.config(
                            state="normal", text=f"重試 {fail_count} 卷失敗"
                        )
                        self.btn_manage.config(state="normal")
                    else:
                        self.btn_retry.config(state="disabled", text="重試失敗")
                        self.btn_manage.config(state="disabled")
                    if garbled_count:
                        self.btn_repair.config(
                            state="normal", text=f"修復亂碼 {garbled_count} 卷"
                        )
                    else:
                        self.btn_repair.config(state="disabled", text="修復亂碼")
                    self.progress_bar["value"] = total
                    self.progress_label.config(text=f"完成 {success_count}/{total} 卷")
```

改為：
```python
                elif kind == "done":
                    _, success_count, fail_volumes, garbled_volumes = msg
                    batch_fail_count = len(fail_volumes)
                    batch_garbled_count = len(garbled_volumes)
                    if self._repair_mode:
                        total = success_count + batch_fail_count + batch_garbled_count
                    else:
                        total = success_count + batch_fail_count
                    # 合併而非覆蓋：保留其他批次尚未解決的卷，只更新本批次涵蓋到的卷
                    attempted = self._last_batch_vids
                    self._recovery_volumes = [
                        v for v in self._recovery_volumes if v["vid"] not in attempted
                    ] + fail_volumes + garbled_volumes
                    recovery_count = len(self._recovery_volumes)
                    self.btn_load.config(state="normal")
                    self.btn_download.config(state="normal")
                    self.btn_select_all.config(state="normal")
                    self.btn_deselect_all.config(state="normal")
                    self.btn_skip.config(state="disabled")
                    if recovery_count:
                        self.btn_recover.config(
                            state="normal", text=f"重試/修復 {recovery_count} 卷"
                        )
                        self.btn_manage.config(state="normal")
                    else:
                        self.btn_recover.config(state="disabled", text="重試/修復")
                        self.btn_manage.config(state="disabled")
                    self.progress_bar["value"] = total
                    self.progress_label.config(text=f"完成 {success_count}/{total} 卷")
```

（下面緊接著的 `if fail_volumes or garbled_volumes: ... suffix = ...` 那段狀態列文字組裝邏輯**維持不動**——它是用當次訊息裡的 `fail_volumes`/`garbled_volumes` 原始變數組「失敗：X；亂碼：Y」的說明文字，不是狀態儲存，不需要跟著改。)

### Step 8：驗證

```
venv\Scripts\python -m py_compile src\main.py
venv\Scripts\python -m pytest tests\ -v
```
Expected: compile 無錯誤；測試維持全過（本次沒有新增/刪除任何 pytest 測試，這是純回歸檢查）。

再跑一次 `grep -n "_fail_volumes\|_garbled_volumes\|btn_retry\|btn_repair\|_on_retry\|_on_repair\|_manage_fail_dialog" src\main.py`，確認完全沒有殘留（除了本次刻意保留、語意相符的地方）。

- [ ] **Step 9: 程式化驗證**（main.py 無自動化測試，仿照先前 bug 修復時的驗證方式）

寫一個暫時性驗證腳本（放在 scratchpad，不要 commit）：
1. 建立 `App`，模擬「下載完成後有 1 卷失敗、1 卷亂碼」→ 確認 `self._recovery_volumes` 有 2 筆、`btn_recover` 顯示「重試/修復 2 卷」且可點擊
2. 呼叫 `_on_recover()` → 確認 `run_repair_all` 被呼叫（可用 `unittest.mock.patch("src.main.run_repair_all")` 攔截），且傳入的 `vols` 剛好是那 2 卷
3. 呼叫 `_manage_recovery_dialog()` → 確認能開啟且對應 `self._recovery_volumes`
4. 確認全部跑完沒有 exception，清乾淨背景程序

- [ ] **Step 10: Commit**

```
git add src/main.py
git commit -m "feat: merge retry-failed and repair-garbled into one recovery flow"
```

---

## Task 2：文件更新

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TODO.md`

- [ ] **Step 1：更新 CHANGELOG**

在「已完成功能」加一行，並在「更新記錄」頂部加新版本區塊（版本號接續現有最新版）：
```
- 「重試失敗」「修復亂碼」合併成單一「重試/修復」按鈕與待處理清單，一律用既有的 repair 邏輯（網路重試+編碼修復）處理，使用者不用分辨失敗類型
```

- [ ] **Step 2：更新 TODO**

加入一項（標示「若有需要再做」，非急件）：
```
- **初次下載時的無限重試阻塞問題**：目前初次下載若開啟「無限重試」，單一卷卡住會擋住整批後續卷下載，只能靠手動「跳過目前卷」化解，沒有自動 fallback（例如逾時或次數門檻自動跳過）。若後續實際使用中常遇到，再評估要不要加自動化保險機制
```

- [ ] **Step 3: Commit**

```
git add docs/CHANGELOG.md docs/TODO.md
git commit -m "docs: update CHANGELOG and TODO for unified recovery flow"
```
