# Filename Format Customization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在設定視窗新增「命名」tab，讓使用者可以自訂序號格式、書名開關、分隔符號，設定持久化至 config.json。

**Architecture:** 擴充 `build_filepath` 與 `run_download_all` 接收三個命名參數；`App` 從 config 讀入並透傳給下載函式；設定視窗加入第三個 tab 含即時預覽。

**Tech Stack:** Python 3.10+, tkinter, pytest

---

## File Map

| 動作 | 檔案 |
|------|------|
| Modify | `src/downloader.py` — `build_filepath` 與 `run_download_all` 加三個命名參數 |
| Modify | `src/main.py` — `App.__init__` 讀 config、`_on_download`/`_on_retry` 透傳、`_open_settings` 加命名 tab |
| Modify | `tests/test_downloader.py` — 新增命名參數相關測試 |
| Modify | `docs/CHANGELOG.md` |
| Modify | `docs/TODO.md` |

---

## Task 1: 擴充 `build_filepath` 的命名參數

**Files:**
- Modify: `src/downloader.py`
- Test: `tests/test_downloader.py`

- [ ] **Step 1: 在 `tests/test_downloader.py` 末尾加入五個失敗測試**

```python
def test_build_filepath_plain_index():
    path = build_filepath("downloads", "書名", 1, "第一卷", 10, index_fmt="plain")
    assert path == os.path.join("downloads", "書名", "1 書名 第一卷.txt")


def test_build_filepath_no_index():
    path = build_filepath("downloads", "書名", 1, "第一卷", 10, index_fmt="none")
    assert path == os.path.join("downloads", "書名", "書名 第一卷.txt")


def test_build_filepath_no_book_name():
    path = build_filepath("downloads", "書名", 1, "第一卷", 10, include_book_name=False)
    assert path == os.path.join("downloads", "書名", "01 第一卷.txt")


def test_build_filepath_custom_separator():
    path = build_filepath("downloads", "書名", 1, "第一卷", 10, separator="_")
    assert path == os.path.join("downloads", "書名", "01_書名_第一卷.txt")


def test_build_filepath_no_index_no_book():
    path = build_filepath("downloads", "書名", 1, "第一卷", 10,
                          index_fmt="none", include_book_name=False)
    assert path == os.path.join("downloads", "書名", "第一卷.txt")
```

- [ ] **Step 2: 執行測試，確認五個新測試失敗**

```
venv\Scripts\python -m pytest tests/test_downloader.py::test_build_filepath_plain_index tests/test_downloader.py::test_build_filepath_no_index tests/test_downloader.py::test_build_filepath_no_book_name tests/test_downloader.py::test_build_filepath_custom_separator tests/test_downloader.py::test_build_filepath_no_index_no_book -v
```

Expected: 5 FAILED（TypeError: unexpected keyword argument）

- [ ] **Step 3: 將 `src/downloader.py` 中的 `build_filepath` 改為以下實作**

```python
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
    filename = separator.join(parts) + ".txt"
    return os.path.join(output_dir, safe(book_name), filename)
```

- [ ] **Step 4: 執行全部 downloader 測試，確認全過**

```
venv\Scripts\python -m pytest tests/test_downloader.py -v
```

Expected: 全部 PASSED（含舊測試，因預設值維持現行行為）

- [ ] **Step 5: Commit**

```
git add tests/test_downloader.py src/downloader.py
git commit -m "feat: extend build_filepath with index_fmt/include_book_name/separator params"
```

---

## Task 2: 擴充 `run_download_all` 的命名參數

**Files:**
- Modify: `src/downloader.py`
- Test: `tests/test_downloader.py`

- [ ] **Step 1: 在 `tests/test_downloader.py` 末尾加入兩個失敗測試**

```python
def test_run_download_all_has_naming_params():
    sig = inspect.signature(run_download_all)
    assert sig.parameters["index_fmt"].default == "padded"
    assert sig.parameters["include_book_name"].default is True
    assert sig.parameters["separator"].default == " "


def test_run_download_all_naming_params_applied(tmp_path):
    """命名參數確實影響輸出檔名"""
    session = MagicMock()
    session.get.return_value = _ok_resp()
    volumes = [{"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99}]
    q = queue.Queue()
    with patch("src.downloader._get_session", return_value=session):
        run_download_all("1", "書名", volumes, str(tmp_path), q,
                         index_fmt="none", include_book_name=False, separator="_")
    expected = os.path.join(str(tmp_path), "書名", "第一卷.txt")
    assert os.path.exists(expected)
```

- [ ] **Step 2: 執行測試，確認兩個新測試失敗**

```
venv\Scripts\python -m pytest tests/test_downloader.py::test_run_download_all_has_naming_params tests/test_downloader.py::test_run_download_all_naming_params_applied -v
```

Expected: 2 FAILED

- [ ] **Step 3: 將 `src/downloader.py` 中的 `run_download_all` 改為以下實作**

整個函式替換（注意 `build_filepath` 呼叫多了三個參數）：

```python
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
```

- [ ] **Step 4: 執行全部 downloader 測試，確認全過**

```
venv\Scripts\python -m pytest tests/test_downloader.py -v
```

Expected: 全部 PASSED

- [ ] **Step 5: Commit**

```
git add tests/test_downloader.py src/downloader.py
git commit -m "feat: extend run_download_all with naming params, pass-through to build_filepath"
```

---

## Task 3: `App` 讀入命名設定並透傳給下載函式

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: 在 `App.__init__` 的 `_cfg = self._load_config()` 之後，加入三行讀取命名設定**

找到這段（約 line 108-113）：
```python
        _cfg = self._load_config()
        self._current_theme = _cfg.get("theme", "light")
        self._path_var = tk.StringVar()
        self._retry_count = int(_cfg.get("retry_count", RETRY_COUNT))
        self._retry_delay = int(_cfg.get("retry_delay", RETRY_DELAY))
        self._browsing = False
```

改為：
```python
        _cfg = self._load_config()
        self._current_theme = _cfg.get("theme", "light")
        self._path_var = tk.StringVar()
        self._retry_count = int(_cfg.get("retry_count", RETRY_COUNT))
        self._retry_delay = int(_cfg.get("retry_delay", RETRY_DELAY))
        self._fname_index = _cfg.get("filename_index", "padded")
        self._fname_book_name = bool(_cfg.get("filename_book_name", True))
        self._fname_separator = _cfg.get("filename_separator", " ")
        self._browsing = False
```

- [ ] **Step 2: 在 `_on_download` 中，找到 `run_download_all` 的呼叫（約 line 669-672）**

```python
        threading.Thread(
            target=run_download_all,
            args=(self._aid, self._book_name, selected, output_dir, self.msg_queue,
                  self._retry_count, self._retry_delay),
            daemon=True,
        ).start()
```

改為：
```python
        threading.Thread(
            target=run_download_all,
            args=(self._aid, self._book_name, selected, output_dir, self.msg_queue,
                  self._retry_count, self._retry_delay,
                  self._fname_index, self._fname_book_name, self._fname_separator),
            daemon=True,
        ).start()
```

- [ ] **Step 3: 在 `_on_retry` 中，找到 `run_download_all` 的呼叫（約 line 693-697）**

```python
        threading.Thread(
            target=run_download_all,
            args=(self._aid, self._book_name, vols, output_dir, self.msg_queue,
                  self._retry_count, self._retry_delay),
            daemon=True,
        ).start()
```

改為：
```python
        threading.Thread(
            target=run_download_all,
            args=(self._aid, self._book_name, vols, output_dir, self.msg_queue,
                  self._retry_count, self._retry_delay,
                  self._fname_index, self._fname_book_name, self._fname_separator),
            daemon=True,
        ).start()
```

- [ ] **Step 4: 執行測試，確認現有測試不受影響**

```
venv\Scripts\python -m pytest tests/ -v
```

Expected: 全部 PASSED

- [ ] **Step 5: Commit**

```
git add src/main.py
git commit -m "feat: App reads naming config and passes to run_download_all"
```

---

## Task 4: Settings 視窗加入「命名」tab

**Files:**
- Modify: `src/main.py` — `_open_settings` 方法

- [ ] **Step 1: 在 `_open_settings` 中，找到 `_apply` 函式定義前的 `tab_download` 設定區塊結尾，加入命名 tab**

找到 `tab_download` 區塊最後幾行（`retry_delay_var` 的 Spinbox 和 Label 之後），在 `def _apply():` 之前插入整個命名 tab 程式碼：

```python
        tab_naming = ttk.Frame(notebook, padding=12)
        notebook.add(tab_naming, text="  命名  ")

        # 序號格式
        ttk.Label(tab_naming, text="序號格式", font=FB).pack(anchor="w", pady=(0, 6))
        fname_index_var = tk.StringVar(value=self._fname_index)
        for val, label in [("padded", "零補位（01, 02…）"),
                            ("plain",  "純數字（1, 2…）"),
                            ("none",   "不顯示")]:
            ttk.Radiobutton(
                tab_naming, text=label,
                variable=fname_index_var, value=val
            ).pack(anchor="w", pady=2)

        ttk.Separator(tab_naming, orient="horizontal").pack(fill="x", pady=10)

        # 書名開關
        fname_book_var = tk.BooleanVar(value=self._fname_book_name)
        ttk.Checkbutton(
            tab_naming, text="檔名含書名", variable=fname_book_var
        ).pack(anchor="w")

        ttk.Separator(tab_naming, orient="horizontal").pack(fill="x", pady=10)

        # 分隔符號
        sep_row = ttk.Frame(tab_naming)
        sep_row.pack(anchor="w")
        ttk.Label(sep_row, text="分隔符號：", font=F).pack(side="left")
        fname_sep_var = tk.StringVar(value=self._fname_separator)
        ttk.Entry(sep_row, textvariable=fname_sep_var, width=5, font=FM).pack(side="left")
        ttk.Label(sep_row, text="（空白 = 空格）", font=FH, foreground="gray").pack(
            side="left", padx=(6, 0)
        )

        ttk.Separator(tab_naming, orient="horizontal").pack(fill="x", pady=10)

        # 即時預覽
        preview_label = ttk.Label(tab_naming, text="", font=FM)
        preview_label.pack(anchor="w")

        def _update_naming_preview(*_):
            idx = fname_index_var.get()
            book = fname_book_var.get()
            sep = fname_sep_var.get() or " "
            parts = []
            if idx == "padded":
                parts.append("01")
            elif idx == "plain":
                parts.append("1")
            if book:
                parts.append("書名")
            parts.append("第一卷")
            preview_label.config(text="預覽：" + sep.join(parts) + ".txt")

        fname_index_var.trace_add("write", _update_naming_preview)
        fname_book_var.trace_add("write", _update_naming_preview)
        fname_sep_var.trace_add("write", _update_naming_preview)
        _update_naming_preview()
```

- [ ] **Step 2: 在 `_apply` 函式中，加入命名設定的儲存邏輯**

找到：
```python
        def _apply():
            self._apply_theme(theme_var.get())
            self._retry_count = retry_count_var.get()
            self._retry_delay = retry_delay_var.get()
            self._save_config({
                "theme": theme_var.get(),
                "retry_count": self._retry_count,
                "retry_delay": self._retry_delay,
            })
            win.destroy()
```

改為：
```python
        def _apply():
            self._apply_theme(theme_var.get())
            self._retry_count = retry_count_var.get()
            self._retry_delay = retry_delay_var.get()
            self._fname_index = fname_index_var.get()
            self._fname_book_name = fname_book_var.get()
            self._fname_separator = fname_sep_var.get() or " "
            self._save_config({
                "theme": theme_var.get(),
                "retry_count": self._retry_count,
                "retry_delay": self._retry_delay,
                "filename_index": self._fname_index,
                "filename_book_name": self._fname_book_name,
                "filename_separator": self._fname_separator,
            })
            win.destroy()
```

- [ ] **Step 3: 啟動 App，打開設定視窗，確認「命名」tab 正常顯示**

```
venv\Scripts\python src\main.py
```

驗證：
- ⚙ → 設定視窗有「外觀」「下載」「命名」三個 tab
- 命名 tab 有序號格式（3 個 radio）、書名 checkbox、分隔符號輸入框
- 預覽即時更新，例如選「純數字」→ 預覽變 `1 書名 第一卷.txt`
- 分隔符號改為 `_` → 預覽變 `01_書名_第一卷.txt`
- 套用後重開設定視窗，設定值仍保留

- [ ] **Step 4: 執行全部測試**

```
venv\Scripts\python -m pytest tests/ -v
```

Expected: 全部 PASSED

- [ ] **Step 5: Commit**

```
git add src/main.py
git commit -m "feat: add naming tab to settings window with live preview"
```

---

## Task 5: 更新文件

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TODO.md`

- [ ] **Step 1: 在 `docs/CHANGELOG.md` 頂部「已完成功能」清單加一行，並在「更新記錄」加入今日條目**

在「已完成功能」末尾加：
```
- 設定視窗「命名」tab：序號格式（零補位/純數字/不顯示）、書名開關、分隔符號客製化，含即時預覽
```

在「更新記錄」頂部加：
```markdown
### 2026-06-11（v6）
- 新增：設定視窗「命名」tab，支援自訂序號格式（零補位/純數字/不顯示）、書名開關、分隔符號
```

- [ ] **Step 2: 在 `docs/TODO.md` 刪除第 2 項（檔案命名格式客製化）**

將：
```
2. **檔案命名格式客製化**：自訂命名樣板（是否含書名、分隔符號等）（optional）
```

刪除，並將後續項目重新編號（3→2、4→3）。

- [ ] **Step 3: Commit**

```
git add docs/CHANGELOG.md docs/TODO.md
git commit -m "docs: update CHANGELOG and TODO for filename format feature (v6)"
```
