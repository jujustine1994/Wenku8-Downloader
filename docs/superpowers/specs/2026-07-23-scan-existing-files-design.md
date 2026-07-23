# 設計規格：掃描既有檔案並修復

日期：2026-07-23
狀態：已核准

---

## 需求摘要

目前「重試/修復」清單（`self._recovery_volumes`）只會累積**本次程式執行期間**下載/修復流程親眼偵測到的失敗卷/亂碼卷。如果使用者關掉程式重開、或漏看某次下載結果，資料夾裡既有的缺檔/亂碼檔案不會自動被抓到，也沒有辦法補進待修復清單。

新增功能：讓使用者可以主動「掃描目前已載入這本書」的輸出資料夾，比對卷列表跟資料夾實際檔案狀態，把缺檔或含亂碼的卷補進既有的「重試/修復」清單，沿用現有的修復流程處理，不用另外寫一套下載邏輯。

**範圍限制**：只掃描「目前已載入這本書」，不支援選任意資料夾反推是哪本書哪一卷（vid 反推不可靠，不做）。

---

## 架構設計

### `src/downloader.py` 新增純函式

```python
def scan_existing_volumes(volumes: list[dict], output_dir: str, book_name: str,
                          index_fmt: str = "padded",
                          include_book_name: bool = True,
                          separator: str = " ") -> list[dict]:
    """比對卷列表與資料夾實際檔案，回傳缺檔或含亂碼的卷清單。純檢查，不發網路請求。"""
```

- 對每一卷，用現有 `build_filepath`（帶入 `seq_index`/`seq_total`/`category` 算出的 `index_prefix`，邏輯跟 `run_download_all`/`run_repair_all` 內算檔名的方式一致）算出「目前命名設定下應該存在的檔名」
- 檔案不存在 → 列入回傳清單
- 檔案存在，呼叫 `check_garbled` 檢查：
  - 含 `�` → 列入
  - 讀取/解碼拋例外（例如非 UTF-8 的舊格式殘留檔）→ 視為需要修復，列入（`check_garbled` 需要包 `try/except`，或在 `scan_existing_volumes` 內包）
- 檔案存在且正常 → 略過
- 回傳的 dict 沿用輸入 `volumes` 裡的原始卷資料（含 `vid`/`category`/`seq_index`/`seq_total`），格式跟 `run_download_all` 回傳的 `fail_volumes`/`garbled_volumes` 一致，可以直接餵給 `run_repair_all`

**已知限制**：檔名比對是照**目前**命名設定（序號格式/書名開關/分隔符號）算的。如果下載後又改了命名設定，舊檔案的實際檔名對不上，會被誤判成「缺檔」。刻意不處理（自動偵測所有可能命名組合太複雜），先這樣。

### `check_garbled` 小改動

現有 `check_garbled`：
```python
def check_garbled(filepath: str) -> bool:
    with open(filepath, encoding="utf-8") as f:
        return "�" in f.read()
```
只在剛寫入的自家檔案上呼叫，一定是合法 UTF-8。但掃描既有檔案時，檔案可能是舊版本程式留下的、或使用者手動放進去的非 UTF-8 檔案，直接開會拋 `UnicodeDecodeError`。改成：
```python
def check_garbled(filepath: str) -> bool:
    try:
        with open(filepath, encoding="utf-8") as f:
            return "�" in f.read()
    except (UnicodeDecodeError, OSError):
        return True
```
呼叫端行為不變（`run_download_all`/`run_repair_all` 呼叫時機都是剛寫入成功之後，不會觸發這個新分支）。

### `src/main.py` 新增

**按鈕**：「掃描既有檔案」`self.btn_scan`，放在下載 tab、跟 `btn_recover`/`btn_manage` 同一排。

**啟用條件**：跟 `btn_download` 同步——只要 `self._volumes` 非空（已載入書）且目前沒有下載/修復在跑，就可以按；`_on_download`/`_on_recover` 開始時 disable，"done" handler 裡跟其他按鈕一起 re-enable。

**Handler** `_on_scan()`：
```python
def _on_scan(self):
    if not self._volumes:
        return
    output_dir = self._ensure_output_dir()
    if output_dir is None:
        return
    found = scan_existing_volumes(
        self._volumes, output_dir, self._book_name,
        self._fname_index, self._fname_book_name, self._fname_separator,
    )
    existing_vids = {v["vid"] for v in self._recovery_volumes}
    self._recovery_volumes += [v for v in found if v["vid"] not in existing_vids]
    n = len(self._recovery_volumes)
    if n:
        self.btn_recover.config(state="normal", text=f"重試/修復 {n} 卷")
        self.btn_manage.config(state="normal")
    if found:
        self._set_status(f"掃描完成，發現 {len(found)} 卷缺檔/亂碼", "info")
    else:
        self._set_status("掃描完成，沒有發現問題", "success")
```

- 掃描結果跟現有 `self._recovery_volumes` **合併**（用 vid 去重），不覆蓋，避免蓋掉使用者還沒處理的舊項目
- 只負責「掃描 + 補進待修復清單」，**不會自動開始修復**——使用者要另外按「重試/修復」才會真的重新下載。同步的（scan 是純本地檔案操作，不用背景執行緒）

**`_reset_book_state()`**：`btn_scan` 加入跟其他按鈕一樣的 disable 重置。

---

## 不在本次範圍內

- 選任意資料夾反推書籍/卷（vid 無法可靠反推，不做）
- 命名設定變更後自動比對舊檔名（列為已知限制，不處理）
- 掃描完自動觸發修復（刻意保留手動確認這一步）

---

## 測試計畫

- `scan_existing_volumes`：在 `tests/` 新增測試，用 tmp 目錄寫幾個假檔案（正常內容／含亂碼／不存在／非 UTF-8 內容）驗證回傳清單正確
- `check_garbled` 補一個測試案例：非 UTF-8 檔案應回傳 `True` 而不是拋例外
- `main.py` 部分延續現有慣例（GUI 改動無自動化測試），改完跑 `pytest tests/` 回歸 + `py_compile` + 手動驗證按鈕啟用/合併行為
