# Output Folder Selection + Download Settings Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在主 UI 加入可編輯的下載資料夾選擇列，並在設定視窗新增「下載」tab 讓使用者調整 retry 次數與間隔。

**Architecture:** `downloader.py` 的 `download_volume` 與 `run_download_all` 改為接受 retry 參數（保留 config.py 預設值），避免 module-level 狀態突變。`main.py` 新增 `resolve_output_dir` 模組層級 helper，App 初始化時從 config 載入所有設定。

**Tech Stack:** Python 3.10+, tkinter, `tkinter.filedialog`, `.tool_config.json`（已有讀寫機制）

---

## 改動檔案總覽

| 檔案 | 動作 |
|------|------|
| `src/downloader.py` | 修改：`download_volume` / `run_download_all` 加 retry 參數 |
| `src/main.py` | 修改：新增 `resolve_output_dir`、`_build_ui` 加第二行、`__init__` 加 path/retry 初始化、`_on_download`/`_on_retry` 改用 config 值、`_open_settings` 加下載 tab、新增 `_on_browse_folder`/`_on_path_confirm` |
| `tests/test_downloader.py` | 修改：新增 retry 參數測試 |
| `tests/test_main_helpers.py` | 新建：測試 `resolve_output_dir` |
| `docs/CHANGELOG.md` | 修改：更新現狀與記錄 |
| `docs/TODO.md` | 修改：刪除 #3，更新 #7 |

---

## Task 1: 更新 downloader.py 接受 retry 參數

**Files:**
- Modify: `src/downloader.py`
- Modify: `tests/test_downloader.py`

- [ ] **Step 1: 在 test_downloader.py 新增 retry 參數測試**

在 `tests/test_downloader.py` 末尾加入：

```python
import inspect
from src.config import RETRY_COUNT, RETRY_DELAY


def test_download_volume_has_retry_params():
    sig = inspect.signature(download_volume)
    assert sig.parameters["retry_count"].default == RETRY_COUNT
    assert sig.parameters["retry_delay"].default == RETRY_DELAY


def test_run_download_all_has_retry_params():
    sig = inspect.signature(run_download_all)
    assert sig.parameters["retry_count"].default == RETRY_COUNT
    assert sig.parameters["retry_delay"].default == RETRY_DELAY


def test_download_volume_respects_custom_retry_count(tmp_path):
    """retry_count=1 時只呼叫一次 session.get（失敗後不重試）"""
    session = _mock_session([Exception("fail")])
    fp = str(tmp_path / "vol.txt")
    with patch("src.downloader._get_session", return_value=session), \
         patch("src.downloader.time.sleep"):
        result = download_volume("1861", 65280, fp, retry_count=1, retry_delay=0)
    assert result is False
    assert session.get.call_count == 1


def test_run_download_all_passes_retry_to_volume(tmp_path):
    """run_download_all 傳入的 retry_count 會影響 log 訊息中顯示的次數"""
    session = MagicMock()
    session.get.side_effect = Exception("fail")
    volumes = [{"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99}]
    q = queue.Queue()
    with patch("src.downloader._get_session", return_value=session), \
         patch("src.downloader.time.sleep"):
        run_download_all("1", "TestBook", volumes, str(tmp_path), q,
                         retry_count=2, retry_delay=0)
    msgs = []
    while not q.empty():
        msgs.append(q.get())
    log_msg = next(m for m in msgs if m[0] == "log")
    assert "2x" in log_msg[4]
```

- [ ] **Step 2: 執行測試確認失敗**

```
cd "C:\Users\CTH\Documents\Code\Wenku8 Downloader"
venv\Scripts\python.exe -m pytest tests/test_downloader.py::test_download_volume_has_retry_params tests/test_downloader.py::test_run_download_all_has_retry_params tests/test_downloader.py::test_download_volume_respects_custom_retry_count tests/test_downloader.py::test_run_download_all_passes_retry_to_volume -v
```

Expected: FAIL（`TypeError` 或 `AssertionError`，因為目前沒有 retry_count 參數）

- [ ] **Step 3: 修改 src/downloader.py**

將整個 `download_volume` 與 `run_download_all` 替換為：

```python
def download_volume(aid: str, vid: int, filepath: str,
                    retry_count: int = RETRY_COUNT,
                    retry_delay: int = RETRY_DELAY) -> bool:
    url = f"{DOWNLOAD_BASE_URL}?aid={aid}&vid={vid}&charset=utf-8"
    for attempt in range(1, retry_count + 1):
        try:
            resp = _get_session().get(url, impersonate="chrome120", timeout=30)
            resp.raise_for_status()
            if len(resp.content) < 50 or resp.content[:5].strip().startswith(b"<"):
                raise ValueError("Response is HTML error page, not TXT")
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(resp.content)
            return True
        except Exception:
            if attempt < retry_count:
                time.sleep(retry_delay)
    return False


def run_download_all(aid: str, book_name: str, volumes: list[dict],
                     output_dir: str, msg_queue: queue.Queue,
                     retry_count: int = RETRY_COUNT,
                     retry_delay: int = RETRY_DELAY) -> None:
    total = len(volumes)
    success = 0
    fail_volumes: list[dict] = []
    pad = max(len(str(total)), 2)

    for i, vol in enumerate(volumes, 1):
        msg_queue.put(("progress", i, total, vol["name"]))
        filepath = build_filepath(output_dir, book_name, vol["index"], vol["name"], total)
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

- [ ] **Step 4: 執行所有 downloader 測試確認全過**

```
venv\Scripts\python.exe -m pytest tests/test_downloader.py -v
```

Expected: 全部 PASS（舊測試因為有預設值，signature 沒變，應全過）

- [ ] **Step 5: Commit**

```
git add src/downloader.py tests/test_downloader.py
git commit -m "feat: downloader accepts retry_count/retry_delay params"
```

---

## Task 2: 新增 resolve_output_dir helper + 測試

**Files:**
- Modify: `src/main.py`（加 `PROJECT_ROOT` 常數 + `resolve_output_dir` 函式）
- Create: `tests/test_main_helpers.py`

- [ ] **Step 1: 建立 tests/test_main_helpers.py**

```python
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.main import resolve_output_dir


def test_uses_config_when_set():
    config = {"output_dir": r"C:\custom\path"}
    result = resolve_output_dir(config, r"C:\project")
    assert result == r"C:\custom\path"


def test_falls_back_to_default_when_missing():
    config = {}
    result = resolve_output_dir(config, r"C:\project")
    assert result == os.path.join(r"C:\project", "downloads")


def test_falls_back_when_empty_string():
    config = {"output_dir": ""}
    result = resolve_output_dir(config, r"C:\project")
    assert result == os.path.join(r"C:\project", "downloads")
```

- [ ] **Step 2: 執行測試確認失敗**

```
venv\Scripts\python.exe -m pytest tests/test_main_helpers.py -v
```

Expected: FAIL（`ImportError`，`resolve_output_dir` 尚未定義）

- [ ] **Step 3: 在 src/main.py 加入 PROJECT_ROOT 與 resolve_output_dir**

在 `SCRIPT_DIR = ...` 那行下方加入：

```python
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)


def resolve_output_dir(config: dict, project_root: str) -> str:
    raw = config.get("output_dir", "")
    if raw:
        return raw
    return os.path.join(project_root, OUTPUT_DIR)
```

- [ ] **Step 4: 執行測試確認全過**

```
venv\Scripts\python.exe -m pytest tests/test_main_helpers.py -v
```

Expected: 3 PASS

- [ ] **Step 5: Commit**

```
git add src/main.py tests/test_main_helpers.py
git commit -m "feat: add resolve_output_dir helper"
```

---

## Task 3: 在主 UI 加入下載資料夾列

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: 在 `__init__` 加入 path 與 retry 初始化**

將現有的：
```python
self._current_theme = self._load_config().get("theme", "light")
```
替換為：
```python
_cfg = self._load_config()
self._current_theme = _cfg.get("theme", "light")
self._path_var = tk.StringVar()
self._retry_count = int(_cfg.get("retry_count", RETRY_COUNT))
self._retry_delay = int(_cfg.get("retry_delay", RETRY_DELAY))
```

在 `self._build_ui()` 那行之後、`self._apply_theme(...)` 之前加入：
```python
self._path_var.set(resolve_output_dir(_cfg, PROJECT_ROOT))
```

- [ ] **Step 2: 在 `_build_ui()` 的 URL frame 加第二行**

找到 `url_row.pack(fill="x")` 之後加入（在整個 url_row block 結束後，`frame_volumes` 建立之前）：

```python
        folder_row = ttk.Frame(frame_url)
        folder_row.pack(fill="x", pady=(6, 0))
        folder_row.columnconfigure(1, weight=1)

        ttk.Label(folder_row, text="下載至：", font=FS).grid(row=0, column=0, sticky="w")
        path_entry = ttk.Entry(folder_row, textvariable=self._path_var, font=FS)
        path_entry.grid(row=0, column=1, sticky="ew", padx=(4, 8))
        path_entry.bind("<Return>", self._on_path_confirm)
        path_entry.bind("<FocusOut>", self._on_path_confirm)
        ttk.Button(
            folder_row, text="瀏覽", command=self._on_browse_folder, width=6
        ).grid(row=0, column=2)
```

- [ ] **Step 3: 加入 _on_browse_folder 與 _on_path_confirm 方法**

在 `_set_status` 方法之後加入：

```python
    def _on_browse_folder(self):
        from tkinter import filedialog
        current = self._path_var.get()
        initial = current if os.path.isdir(current) else PROJECT_ROOT
        chosen = filedialog.askdirectory(initialdir=initial, title="選擇下載資料夾")
        if chosen:
            self._path_var.set(chosen)
            self._save_config({"output_dir": chosen})
            self._set_status(f"下載位置：{chosen}", "success")

    def _on_path_confirm(self, event=None):
        path = self._path_var.get().strip()
        if os.path.isdir(path):
            self._save_config({"output_dir": path})
            self._set_status(f"下載位置：{path}", "info")
        else:
            self._set_status(f"路徑不存在：{path}（下載時會自動建立）", "error")
```

- [ ] **Step 4: 更新 _on_download 使用 path_var**

將 `_on_download` 裡的：
```python
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            OUTPUT_DIR,
        )
        threading.Thread(
            target=run_download_all,
            args=(self._aid, self._book_name, selected, output_dir, self.msg_queue),
            daemon=True,
        ).start()
```
替換為：
```python
        output_dir = self._path_var.get()
        threading.Thread(
            target=run_download_all,
            args=(self._aid, self._book_name, selected, output_dir, self.msg_queue,
                  self._retry_count, self._retry_delay),
            daemon=True,
        ).start()
```

- [ ] **Step 5: 更新 _on_retry 使用 path_var**

將 `_on_retry` 裡的：
```python
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            OUTPUT_DIR,
        )
        threading.Thread(
            target=run_download_all,
            args=(self._aid, self._book_name, vols, output_dir, self.msg_queue),
            daemon=True,
        ).start()
```
替換為：
```python
        output_dir = self._path_var.get()
        threading.Thread(
            target=run_download_all,
            args=(self._aid, self._book_name, vols, output_dir, self.msg_queue,
                  self._retry_count, self._retry_delay),
            daemon=True,
        ).start()
```

- [ ] **Step 6: 手動驗證 UI**

啟動程式：
```
venv\Scripts\python.exe -m src.main
```

驗證：
1. 主視窗的「書籍目錄網址」框下方出現「下載至：」+ Entry + 「瀏覽」按鈕
2. Entry 顯示預設路徑（專案根目錄下的 `downloads`）
3. 點「瀏覽」能開啟資料夾選擇對話框，選完後 Entry 更新
4. 手動輸入一個不存在的路徑 + 按 Enter，status bar 顯示 error 提示
5. 手動輸入合法路徑 + 按 Enter，status bar 顯示 info

- [ ] **Step 7: Commit**

```
git add src/main.py
git commit -m "feat: add output folder row to main UI"
```

---

## Task 4: 設定視窗加「下載」tab

**Files:**
- Modify: `src/main.py`（`_open_settings`）

- [ ] **Step 1: 在 _open_settings 加「下載」tab**

找到 `notebook = ttk.Notebook(win)` 以及 `tab_appearance` 整個 block 結束後（`theme_var.trace_add` 那行之前），加入新 tab：

```python
        tab_download = ttk.Frame(notebook, padding=12)
        notebook.add(tab_download, text="  下載  ")

        row1 = ttk.Frame(tab_download)
        row1.pack(fill="x", pady=(0, 12))
        ttk.Label(row1, text="重試次數：", font=F).pack(side="left")
        retry_count_var = tk.IntVar(value=self._retry_count)
        ttk.Spinbox(
            row1, from_=1, to=10, textvariable=retry_count_var,
            width=5, font=F
        ).pack(side="left", padx=(8, 4))
        ttk.Label(row1, text="次", font=F).pack(side="left")

        row2 = ttk.Frame(tab_download)
        row2.pack(fill="x")
        ttk.Label(row2, text="重試間隔：", font=F).pack(side="left")
        retry_delay_var = tk.IntVar(value=self._retry_delay)
        ttk.Spinbox(
            row2, from_=1, to=30, textvariable=retry_delay_var,
            width=5, font=F
        ).pack(side="left", padx=(8, 4))
        ttk.Label(row2, text="秒", font=F).pack(side="left")
```

- [ ] **Step 2: 更新 _apply 函式同時儲存 retry 設定**

找到 settings 視窗裡的 `_apply` 函式：
```python
        def _apply():
            self._apply_theme(theme_var.get())
            self._save_config({"theme": theme_var.get()})
            win.destroy()
```
替換為：
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

- [ ] **Step 3: 手動驗證設定視窗**

啟動程式，點 ⚙ 按鈕：
1. 設定視窗出現兩個 tab：「外觀」「下載」
2. 切到「下載」tab，看到重試次數（預設 3）和重試間隔（預設 2）的 Spinbox
3. 改成次數 5、間隔 5，按「套用」，關閉
4. 再開設定視窗，確認「下載」tab 顯示 5 / 5
5. 關閉程式重開，確認設定持久化

- [ ] **Step 4: Commit**

```
git add src/main.py
git commit -m "feat: add download settings tab with retry controls"
```

---

## Task 5: 更新 CHANGELOG 和 TODO

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TODO.md`

- [ ] **Step 1: 更新 docs/TODO.md**

將 `docs/TODO.md` 改為：

```markdown
# TODO

1. **簡轉繁**：下載後自動將簡體中文轉換為繁體中文
2. **亂碼檢查**：下載完成後驗證內容是否有亂碼或編碼錯誤（optional）
4. **檔案命名格式客製化**：自訂命名樣板（是否含書名、分隔符號等）（optional）
5. **正式卷 vs 外傳自動識別**：系統判斷卷名屬於正式卷或外傳，分別編號或分資料夾存放（optional）
6. **下載隊列 + 暫停/繼續/取消**：個別卷可控制（optional）
```

（移除已完成的 #3 輸出資料夾選擇與 #7 失敗卷重試）

- [ ] **Step 2: 在 docs/CHANGELOG.md 頂部現狀區新增完成項目，並加一筆更新記錄**

在「已完成功能」清單加入：
```
- 輸出資料夾選擇（主 UI 直接顯示 + 可編輯 + 瀏覽按鈕）
- 設定視窗「下載」tab：retry 次數與間隔可調整（持久化至 config.json）
```

在更新記錄最上方加入新條目（日期 2026-06-10，v4）：
```
### 2026-06-10（v4）
- 新增：主 UI「書籍目錄網址」框加「下載至」列，可直接輸入或瀏覽選擇輸出資料夾
- 新增：設定視窗加「下載」tab，支援調整重試次數（1–10）與重試間隔（1–30 秒）
- 改善：downloader 的 retry 設定改為參數傳入，不再依賴 module-level hardcode
```

- [ ] **Step 3: Commit**

```
git add docs/CHANGELOG.md docs/TODO.md
git commit -m "docs: update CHANGELOG and TODO for v4 features"
```
