# 設計規格：統一「重試/修復」懶人流程

日期：2026-07-09
狀態：已核准

---

## 需求摘要

下載完成後，失敗卷（網路完全抓不到）跟亂碼卷（有抓到但編碼爛掉）目前是兩份清單、兩顆按鈕（「重試失敗」「修復亂碼」）、兩套流程。使用者不想分辨是哪種問題，希望**合併成一個清單、一顆按鈕**：點下去自動同時處理網路重試與編碼修復，直到清單清空或使用者手動跳過。

初次下載（「下載選取」）行為維持不變，不在本次範圍——記錄到 TODO，若有需要再處理。

---

## 架構設計

### 關鍵前提：`repair_volume`/`run_repair_all` 已是完整超集

`repair_volume()`（downloader.py）本來就會做網路重試（`_fetch_best_text` 內建的 retry_count/retry_delay/skip_event），又額外做多輪編碼比對（utf-8/gbk）直到乾淨或停滯。「失敗卷」（`run_download_all` 回傳的 `fail_volumes`，代表整卷都抓不到任何內容）跟「亂碼卷」（`check_garbled` 判定有內容但含 `�`）都能被 `repair_volume` 正確處理——`repair_volume` 回傳 `None`（完全抓不到）或 `True`（仍有亂碼）分別對應這兩種情況。

**結論：`downloader.py` 不需要新函式，`run_repair_all` 直接重複使用即可。** 只需要在 `main.py` 把兩份清單/按鈕合併。

### `main.py` 變更

**狀態合併**：
- `self._fail_volumes` + `self._garbled_volumes` → 合併成 `self._recovery_volumes: list = []`
- `_reset_book_state()`、`"done"` 訊息 handler 的合併邏輯改為對單一清單操作

**按鈕合併**：
- `btn_retry`（"重試失敗"）+ `btn_repair`（"修復亂碼"）→ 合併成 `btn_recover`，文字 `f"重試/修復 {n} 卷"`
- `btn_manage`（"管理"）保留，改操作 `self._recovery_volumes`

**流程合併**：
- `_on_retry()` + `_on_repair()` → 合併成 `_on_recover()`：
  - guard `if not self._recovery_volumes: return`
  - 移除原 `_on_repair` 的 `messagebox.askokcancel` 確認對話框（懶人流程不需要二次確認，跟原本 `_on_retry` 一樣直接執行）
  - `self._repair_mode = True`（固定，因為統一流程一律用 `run_repair_all` 的統計方式）
  - 背景執行緒一律呼叫 `run_repair_all`（不再呼叫 `run_download_all` 做重試）
- `_manage_fail_dialog()` → 改名 `_manage_recovery_dialog()`，操作 `self._recovery_volumes`，標題「管理待處理卷」

**"done" 訊息 handler**：
- 收到的 `fail_volumes`、`garbled_volumes`（`run_download_all`/`run_repair_all` 回傳格式不變）合併寫入 `self._recovery_volumes`（沿用現有的跨批次合併邏輯，用 `_last_batch_vids` 排除本批次涵蓋到的卷再接上新結果）
- 狀態列文字仍可分別列出「失敗：X；亂碼：Y」（這只是訊息文字，不影響狀態儲存方式）

**`_on_download()`**：
- 原本重置 `btn_repair` 的那行改成重置 `btn_recover`

---

## 不在本次範圍內

- 初次下載當下的無限重試阻塞問題（例如自動 fallback、逾時跳過）——記錄到 TODO，標示「若有需要再做」
- `downloader.py` 不需要改動

---

## 測試計畫

這次改動集中在 `main.py`（GUI 狀態機），沒有新的 `downloader.py`/`scraper.py` 純函式邏輯，延續現有慣例（GUI 改動無自動化測試，改完跑 `pytest tests/`（回歸測試）+ `py_compile` + 手動/程式化驗證按鈕狀態與清單合併行為）。
