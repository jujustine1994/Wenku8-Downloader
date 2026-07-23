# 掃描既有檔案並修復 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增「掃描既有檔案」功能，比對目前已載入書籍的卷列表跟輸出資料夾裡的實際檔案，把缺檔或含亂碼的卷補進既有「重試/修復」待處理清單。

**Architecture:** `src/downloader.py` 新增純函式 `scan_existing_volumes()`（比對卷列表與磁碟檔案，不發網路請求），並讓 `check_garbled()` 對非 UTF-8 檔案容錯（回傳 True 而非拋例外）。`src/main.py` 新增「掃描既有檔案」按鈕與 `_on_scan()` handler，掃描結果跟 `self._recovery_volumes` 用 vid 去重合併，沿用既有的「重試/修復」按鈕與 `run_repair_all` 流程處理，不新增下載邏輯。

**Tech Stack:** Python 3.10+, tkinter, pytest

## Global Constraints

- 向下相容：`scan_existing_volumes` 是全新函式，不影響任何既有呼叫端
- 檔名比對一律照**目前**的命名設定（`index_fmt`/`include_book_name`/`separator`）計算，不嘗試比對舊命名設定下的檔名（設計文件已載明的已知限制）
- 掃描本身純本地檔案操作，不發網路請求、不使用背景執行緒
- 掃描只補進待修復清單，不自動觸發修復

---

## 檔案異動總覽

| 檔案 | 動作 |
|---|---|
| `src/downloader.py` | 修改 `check_garbled()` 容錯；新增 `scan_existing_volumes()` |
| `tests/test_downloader.py` | 新增測試 |
| `src/main.py` | import `scan_existing_volumes`；新增 `btn_scan` 按鈕；新增 `_on_scan()`；`_reset_book_state()`／`_confirm()`／`"done"` handler／`_on_download()`／`_on_recover()` 補上 `btn_scan` 的啟用/停用同步 |

---

### Task 1: `check_garbled()` 對非 UTF-8 檔案容錯

**Files:**
- Modify: `src/downloader.py:102-104`
- Test: `tests/test_downloader.py`

**Interfaces:**
- Consumes: 無
- Produces: `check_garbled(filepath: str) -> bool`（既有函式簽名不變，行為擴充：非 UTF-8/讀取失敗時回傳 `True` 而非拋例外）

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_downloader.py` 檔案尾端加入：

```python
def test_check_garbled_non_utf8_file_treated_as_garbled(tmp_path):
    """既有檔案若不是合法 UTF-8（例如舊版程式殘留），視為需要修復而非拋例外"""
    fp = tmp_path / "bad_encoding.txt"
    fp.write_bytes(b"\xff\xfe\x00\xd8")  # 不是合法 UTF-8 bytes
    assert check_garbled(str(fp)) is True
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest tests/test_downloader.py::test_check_garbled_non_utf8_file_treated_as_garbled -v`
Expected: FAIL（`UnicodeDecodeError` 而不是回傳 `True`）

- [ ] **Step 3: 修改 `check_garbled`**

在 `src/downloader.py` 把：

```python
def check_garbled(filepath: str) -> bool:
    with open(filepath, encoding="utf-8") as f:
        return "�" in f.read()
```

改成：

```python
def check_garbled(filepath: str) -> bool:
    try:
        with open(filepath, encoding="utf-8") as f:
            return "�" in f.read()
    except (UnicodeDecodeError, OSError):
        return True
```

- [ ] **Step 4: 執行測試確認通過**

Run: `pytest tests/test_downloader.py -k check_garbled -v`
Expected: PASS（所有 `check_garbled` 相關測試，含既有的 `test_check_garbled_clean`、`test_check_garbled_with_replacement_char`）

- [ ] **Step 5: Commit**

```bash
git add src/downloader.py tests/test_downloader.py
git commit -m "fix: check_garbled 對非 UTF-8 檔案回傳 True 而非拋例外"
```

---

### Task 2: 新增 `scan_existing_volumes()` 純函式

**Files:**
- Modify: `src/downloader.py`（在 `build_filepath` 定義之後，`run_download_all` 定義之前新增）
- Test: `tests/test_downloader.py`

**Interfaces:**
- Consumes: `build_filepath(output_dir, book_name, volume_index, volume_name, total, index_fmt, include_book_name, separator, index_prefix) -> str`（既有函式，`src/downloader.py:162`）；`check_garbled(filepath) -> bool`（Task 1 修改後版本）
- Produces: `scan_existing_volumes(volumes, output_dir, book_name, index_fmt="padded", include_book_name=True, separator=" ") -> list[dict]`——回傳輸入 `volumes` 中缺檔或含亂碼的項目（保留原始 dict 內容，不修改欄位），Task 3 的 `main.py` `_on_scan()` 會呼叫這個函式

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_downloader.py` 頂部 import 加入 `scan_existing_volumes`：

```python
from src.downloader import (
    download_volume, build_filepath, run_download_all, check_garbled,
    repair_volume, run_repair_all, scan_existing_volumes,
)
```

在檔案尾端加入：

```python
def test_scan_existing_volumes_detects_missing_file(tmp_path):
    """卷對應的檔案不存在 → 列入待修復清單"""
    volumes = [{"index": 1, "name": "第一卷", "vid": 99,
                "category": "main", "seq_index": 1, "seq_total": 1}]
    result = scan_existing_volumes(volumes, str(tmp_path), "書名")
    assert result == volumes


def test_scan_existing_volumes_detects_garbled_file(tmp_path):
    """檔案存在但含亂碼 → 列入待修復清單"""
    volumes = [{"index": 1, "name": "第一卷", "vid": 99,
                "category": "main", "seq_index": 1, "seq_total": 1}]
    fp = build_filepath(str(tmp_path), "書名", 1, "第一卷", 1)
    with open(fp, "w", encoding="utf-8") as f:
        f.write("正常內容�亂碼")
    result = scan_existing_volumes(volumes, str(tmp_path), "書名")
    assert result == volumes


def test_scan_existing_volumes_skips_clean_file(tmp_path):
    """檔案存在且正常 → 不列入"""
    volumes = [{"index": 1, "name": "第一卷", "vid": 99,
                "category": "main", "seq_index": 1, "seq_total": 1}]
    fp = build_filepath(str(tmp_path), "書名", 1, "第一卷", 1)
    with open(fp, "w", encoding="utf-8") as f:
        f.write("這是正常的繁體中文內容")
    result = scan_existing_volumes(volumes, str(tmp_path), "書名")
    assert result == []


def test_scan_existing_volumes_mixed_and_naming_params(tmp_path):
    """多卷混合情況：正常/亂碼/缺檔都正確分類，且命名參數會影響比對到的檔名"""
    volumes = [
        {"index": 1, "name": "第一卷", "vid": 1,
         "category": "main", "seq_index": 1, "seq_total": 3},
        {"index": 2, "name": "第二卷", "vid": 2,
         "category": "main", "seq_index": 2, "seq_total": 3},
        {"index": 3, "name": "番外篇", "vid": 3,
         "category": "side", "seq_index": 1, "seq_total": 1},
    ]
    # 卷1：正常檔案（要用 include_book_name=False 才對得上實際檔名）
    fp1 = build_filepath(str(tmp_path), "書名", 1, "第一卷", 3,
                         include_book_name=False)
    with open(fp1, "w", encoding="utf-8") as f:
        f.write("正常內容")
    # 卷2：不建立檔案 → 缺檔
    # 卷3（外傳）：建立但含亂碼
    fp3 = build_filepath(str(tmp_path), "書名", 1, "番外篇", 1,
                         include_book_name=False, index_prefix="外傳")
    with open(fp3, "w", encoding="utf-8") as f:
        f.write("內容�亂碼")

    result = scan_existing_volumes(volumes, str(tmp_path), "書名",
                                   include_book_name=False)
    result_vids = {v["vid"] for v in result}
    assert result_vids == {2, 3}
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest tests/test_downloader.py -k scan_existing_volumes -v`
Expected: FAIL（`ImportError: cannot import name 'scan_existing_volumes'`）

- [ ] **Step 3: 實作 `scan_existing_volumes`**

在 `src/downloader.py` 的 `build_filepath` 函式定義之後（`run_download_all` 定義之前）加入：

```python
def scan_existing_volumes(volumes: list[dict], output_dir: str, book_name: str,
                          index_fmt: str = "padded",
                          include_book_name: bool = True,
                          separator: str = " ") -> list[dict]:
    """比對卷列表與資料夾實際檔案，回傳缺檔或含亂碼的卷清單。純檢查，不發網路請求。"""
    total = len(volumes)
    missing_or_garbled = []
    for vol in volumes:
        seq_index = vol.get("seq_index", vol["index"])
        seq_total = vol.get("seq_total", total)
        prefix = "外傳" if vol.get("category") == "side" else ""
        filepath = build_filepath(output_dir, book_name, seq_index, vol["name"], seq_total,
                                  index_fmt, include_book_name, separator,
                                  index_prefix=prefix)
        if not os.path.isfile(filepath) or check_garbled(filepath):
            missing_or_garbled.append(vol)
    return missing_or_garbled
```

- [ ] **Step 4: 執行測試確認通過**

Run: `pytest tests/test_downloader.py -k scan_existing_volumes -v`
Expected: PASS（4 個新測試全過）

- [ ] **Step 5: 跑全套 downloader 測試確認沒有回歸**

Run: `pytest tests/test_downloader.py -v`
Expected: PASS（全部通過，含既有測試）

- [ ] **Step 6: Commit**

```bash
git add src/downloader.py tests/test_downloader.py
git commit -m "feat: 新增 scan_existing_volumes 比對卷列表與磁碟既有檔案"
```

---

### Task 3: `main.py` 新增「掃描既有檔案」按鈕與 handler

**Files:**
- Modify: `src/main.py:14`（import）、`src/main.py:242-253`（按鈕列）、`src/main.py:936-946`（`_reset_book_state`）、`src/main.py:1035-1054`（Preview `_confirm`）、`src/main.py:1130-1167`（`_on_download`）、`src/main.py:1168-1201`（`_on_recover` 之後新增 `_on_scan`）、`src/main.py:1319-1345`（`"done"` handler）

**Interfaces:**
- Consumes: `scan_existing_volumes(volumes, output_dir, book_name, index_fmt, include_book_name, separator) -> list[dict]`（Task 2）；既有 `self._ensure_output_dir() -> str | None`、`self._set_status(msg, level)`、`self._recovery_volumes: list`、`self._volumes: list`、`self._book_name: str`、`self._fname_index/_fname_book_name/_fname_separator`
- Produces: `self.btn_scan`（`ttk.Button`）、`self._on_scan()` handler。無其他模組依賴這兩者。

- [ ] **Step 1: import `scan_existing_volumes`**

把 `src/main.py:14`：

```python
from src.downloader import run_download_all, run_repair_all
```

改成：

```python
from src.downloader import run_download_all, run_repair_all, scan_existing_volumes
```

- [ ] **Step 2: 新增按鈕**

把 `src/main.py:242-245`：

```python
        self.btn_recover = ttk.Button(
            btn_row, text="重試/修復", command=self._on_recover, width=10, state="disabled"
        )
        self.btn_recover.pack(side="right", ipady=4, padx=(0, 6))
```

改成（在 `btn_recover` 之前插入 `btn_scan`，維持 `pack(side="right")` 由右往左排列的視覺順序：下載選取 | 重試/修復 | 掃描既有檔案 | 管理 | 跳過目前卷）：

```python
        self.btn_recover = ttk.Button(
            btn_row, text="重試/修復", command=self._on_recover, width=10, state="disabled"
        )
        self.btn_recover.pack(side="right", ipady=4, padx=(0, 6))
        self.btn_scan = ttk.Button(
            btn_row, text="掃描既有檔案", command=self._on_scan, width=12, state="disabled"
        )
        self.btn_scan.pack(side="right", ipady=4, padx=(0, 6))
```

- [ ] **Step 3: `_reset_book_state()` 加入 `btn_scan` 重置**

把 `src/main.py:936-946`：

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

改成：

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
        self.btn_scan.config(state="disabled")
```

- [ ] **Step 4: Preview `_confirm()` 啟用 `btn_scan`**

把 `src/main.py:1048-1050`：

```python
            self.btn_download.config(state="normal")
            self.btn_select_all.config(state="normal")
            self.btn_deselect_all.config(state="normal")
```

改成：

```python
            self.btn_download.config(state="normal")
            self.btn_select_all.config(state="normal")
            self.btn_deselect_all.config(state="normal")
            self.btn_scan.config(state="normal")
```

- [ ] **Step 5: `_on_download()`／`_on_recover()` 開始時停用 `btn_scan`**

把 `src/main.py:1140-1143`（`_on_download` 開頭）：

```python
        self.btn_download.config(state="disabled")
        self.btn_load.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
```

改成：

```python
        self.btn_download.config(state="disabled")
        self.btn_load.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
        self.btn_scan.config(state="disabled")
```

把 `src/main.py:1180-1184`（`_on_recover` 開頭）：

```python
        self.btn_recover.config(state="disabled", text="重試/修復")
        self.btn_manage.config(state="disabled")
        self.btn_download.config(state="disabled")
        self.btn_load.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
```

改成：

```python
        self.btn_recover.config(state="disabled", text="重試/修復")
        self.btn_manage.config(state="disabled")
        self.btn_download.config(state="disabled")
        self.btn_load.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
        self.btn_scan.config(state="disabled")
```

- [ ] **Step 6: `"done"` handler 重新啟用 `btn_scan`**

把 `src/main.py:1333-1336`：

```python
                    self.btn_load.config(state="normal")
                    self.btn_download.config(state="normal")
                    self.btn_select_all.config(state="normal")
                    self.btn_deselect_all.config(state="normal")
```

改成：

```python
                    self.btn_load.config(state="normal")
                    self.btn_download.config(state="normal")
                    self.btn_select_all.config(state="normal")
                    self.btn_deselect_all.config(state="normal")
                    self.btn_scan.config(state="normal")
```

- [ ] **Step 7: 新增 `_on_scan()` handler**

在 `src/main.py` 的 `_on_recover()` 方法結束之後、`_on_skip()` 方法之前（約 `src/main.py:1200-1202` 之間）加入：

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

- [ ] **Step 8: 語法檢查**

Run: `python -m py_compile src/main.py`
Expected: 無輸出（無語法錯誤）

- [ ] **Step 9: 跑全套測試確認沒有回歸**

Run: `pytest tests/ -v`
Expected: PASS（全部通過，含 `tests/test_main_helpers.py`）

- [ ] **Step 10: 手動驗證（啟動程式）**

Run: `python -m src.main`（或用現有的 `Wenku8下載器啟動器.bat`）

驗證步驟：
1. 載入一本書、確認分類 → 「掃描既有檔案」按鈕應變為可點擊狀態
2. 在輸出資料夾手動刪掉其中一卷已下載的 txt，或手動把某卷內容改成含 `�` 的文字
3. 點「掃描既有檔案」→ 狀態列應顯示「掃描完成，發現 N 卷缺檔/亂碼」，「重試/修復」按鈕文字更新為對應卷數
4. 點「重試/修復」→ 該卷應被重新下載修復
5. 都正常後再點一次「掃描既有檔案」→ 狀態列應顯示「掃描完成，沒有發現問題」

- [ ] **Step 11: Commit**

```bash
git add src/main.py
git commit -m "feat: 新增「掃描既有檔案」按鈕，比對磁碟檔案補進重試/修復清單"
```

---

### Task 4: 更新文件

**Files:**
- Modify: `docs/CHANGELOG.md`

**Interfaces:**
- Consumes: 無
- Produces: 無（純文件更新）

- [ ] **Step 1: 在「現狀」清單補上新功能**

在 `docs/CHANGELOG.md` 的「已完成功能」清單最後一行（目前是 Preview 分類那行）之後加入一行：

```
- 「掃描既有檔案」按鈕：比對目前已載入書籍的卷列表跟輸出資料夾實際檔案，把缺檔或含亂碼的卷補進「重試/修復」待處理清單（不含網路請求，純本地檔案比對；檔名比對依照目前的命名設定計算，命名設定變更後的舊檔案可能被誤判為缺檔）
```

- [ ] **Step 2: 在「更新記錄」加入新版本條目**

在 `docs/CHANGELOG.md` 的「## 更新記錄」標題之後（目前第一條是 `### 2026-07-17 — 文件修正`）插入新的一條：

```markdown
### 2026-07-23（v17）
- 新增：「掃描既有檔案」按鈕，比對目前已載入書籍的卷列表跟輸出資料夾實際檔案狀態（缺檔或含亂碼），結果併入既有「重試/修復」待處理清單，沿用現有修復流程，不新增下載邏輯
- 技術：`downloader.py` 新增 `scan_existing_volumes()`；`check_garbled()` 改為對非 UTF-8 檔案回傳 `True` 而非拋例外（掃描既有檔案時可能遇到舊格式殘留檔）
```

- [ ] **Step 3: Commit**

```bash
git add docs/CHANGELOG.md
git commit -m "docs: 記錄「掃描既有檔案」功能到 CHANGELOG"
```

---

## 自我檢查（實作前）

- **spec 涵蓋度**：spec 的三大部分（核心掃描邏輯／UI 按鈕／測試）分別對應 Task 2、Task 3、Task 1+2（測試）；spec 提到的 `check_garbled` 容錯，對應 Task 1。已知限制（命名設定變更後檔名對不上）已寫進 Task 4 的 CHANGELOG 條目與本文件 Global Constraints，不需要額外任務。
- **型別/簽名一致性**：`scan_existing_volumes` 在 Task 2 定義的簽名 `(volumes, output_dir, book_name, index_fmt="padded", include_book_name=True, separator=" ")`，跟 Task 3 `_on_scan()` 的呼叫方式（位置參數對應 `self._fname_index`／`self._fname_book_name`／`self._fname_separator`）一致。
