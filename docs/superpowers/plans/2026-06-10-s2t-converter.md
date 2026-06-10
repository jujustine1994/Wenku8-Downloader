# 簡轉繁功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 下載時自動轉繁體，並在主視窗新增「轉換」tab 支援批次轉換現有 TXT 檔。

**Architecture:** 新建 `src/converter.py` 集中轉換邏輯（`convert_to_traditional` + `run_convert_all`）；`downloader.py` 下載後呼叫轉換；`main.py` 的 `_build_ui()` 改為 Notebook 結構，現有下載流程包進「下載」tab，新增「轉換」tab。

**Tech Stack:** Python 3.10+, tkinter, `opencc-python-reimplemented`（s2twp 轉換方向）

---

## 改動檔案總覽

| 檔案 | 動作 |
|------|------|
| `src/converter.py` | 新建：`convert_to_traditional`、`run_convert_all` |
| `src/downloader.py` | 修改：`download_volume` 寫檔後呼叫轉換 |
| `src/main.py` | 修改：`_build_ui` 加 Notebook、`__init__` 加 `_conv_files`、`_poll_queue` 加 conv 訊息、新增 `_build_convert_tab` / `_on_conv_select` / `_conv_remove_file` / `_refresh_conv_file_list` / `_on_conv_start` |
| `requirements.txt` | 修改：加 `opencc-python-reimplemented` |
| `tests/test_converter.py` | 新建：converter 與 run_convert_all 測試 |
| `tests/test_downloader.py` | 修改：加下載後轉繁驗證測試 |
| `docs/CHANGELOG.md` | 修改：加 v5 記錄 |
| `docs/TODO.md` | 修改：移除 #1 簡轉繁 |

---

## Task 1: 安裝套件 + 新建 src/converter.py

**Files:**
- Create: `src/converter.py`
- Create: `tests/test_converter.py`
- Modify: `requirements.txt`

- [ ] **Step 1: 在 requirements.txt 加套件**

在 `requirements.txt` 末尾加一行：
```
opencc-python-reimplemented>=1.0.0
```

- [ ] **Step 2: 安裝套件**

```powershell
cd "C:\Users\CTH\Documents\Code\Wenku8 Downloader"
venv\Scripts\python.exe -m pip install opencc-python-reimplemented
```

Expected: 顯示 `Successfully installed opencc-python-reimplemented-...`

- [ ] **Step 3: 建立 tests/test_converter.py（TDD：先寫測試）**

```python
import os
import queue
import pytest
from src.converter import convert_to_traditional, run_convert_all


def test_converts_simplified_software():
    assert convert_to_traditional("软件") == "軟體"


def test_converts_network_term():
    assert convert_to_traditional("网络") == "網路"


def test_converts_common_terms():
    result = convert_to_traditional("软件 硬件 网络 文件")
    assert "軟體" in result
    assert "硬體" in result
    assert "網路" in result
    assert "檔案" in result


def test_traditional_input_unchanged():
    assert convert_to_traditional("軟體網路") == "軟體網路"


def test_empty_string():
    assert convert_to_traditional("") == ""


def test_mixed_content_preserved():
    result = convert_to_traditional("Hello 软件 123")
    assert "Hello" in result
    assert "軟體" in result
    assert "123" in result


def test_run_convert_all_overwrite(tmp_path):
    fp = tmp_path / "test.txt"
    fp.write_text("软件", encoding="utf-8")
    q = queue.Queue()
    run_convert_all([str(fp)], "overwrite", q)
    assert fp.read_text(encoding="utf-8") == "軟體"
    msgs = []
    while not q.empty():
        msgs.append(q.get())
    assert msgs[-1] == ("conv_done", 1, 0)


def test_run_convert_all_new_file(tmp_path):
    fp = tmp_path / "test.txt"
    fp.write_text("软件", encoding="utf-8")
    q = queue.Queue()
    run_convert_all([str(fp)], "new_file", q)
    new_fp = tmp_path / "test_TC.txt"
    assert new_fp.exists()
    assert new_fp.read_text(encoding="utf-8") == "軟體"
    assert fp.read_text(encoding="utf-8") == "软件"


def test_run_convert_all_log_messages(tmp_path):
    fp = tmp_path / "test.txt"
    fp.write_text("软件", encoding="utf-8")
    q = queue.Queue()
    run_convert_all([str(fp)], "overwrite", q)
    msgs = []
    while not q.empty():
        msgs.append(q.get())
    assert ("conv_log", True, "test.txt", "") in msgs
    assert msgs[-1] == ("conv_done", 1, 0)


def test_run_convert_all_handles_missing_file(tmp_path):
    q = queue.Queue()
    run_convert_all([str(tmp_path / "nonexistent.txt")], "overwrite", q)
    msgs = []
    while not q.empty():
        msgs.append(q.get())
    assert msgs[-1] == ("conv_done", 0, 1)
    assert msgs[0][0] == "conv_log"
    assert msgs[0][1] is False


def test_run_convert_all_multiple_files(tmp_path):
    files = []
    for i in range(3):
        fp = tmp_path / f"vol{i}.txt"
        fp.write_text("软件", encoding="utf-8")
        files.append(str(fp))
    q = queue.Queue()
    run_convert_all(files, "overwrite", q)
    msgs = []
    while not q.empty():
        msgs.append(q.get())
    assert msgs[-1] == ("conv_done", 3, 0)
    log_msgs = [m for m in msgs if m[0] == "conv_log"]
    assert len(log_msgs) == 3
```

- [ ] **Step 4: 執行測試確認全部失敗**

```powershell
venv\Scripts\python.exe -m pytest tests/test_converter.py -v
```

Expected: FAIL（ImportError，`src.converter` 不存在）

- [ ] **Step 5: 建立 src/converter.py**

```python
import os
import queue

from opencc import OpenCC

_cc = OpenCC("s2twp")


def convert_to_traditional(text: str) -> str:
    return _cc.convert(text)


def run_convert_all(
    files: list[str], output_mode: str, msg_queue: queue.Queue
) -> None:
    success = 0
    fail = 0
    for filepath in files:
        try:
            text = open(filepath, encoding="utf-8", errors="replace").read()
            converted = convert_to_traditional(text)
            if output_mode == "overwrite":
                out_path = filepath
            else:
                base, ext = os.path.splitext(filepath)
                out_path = base + "_TC" + ext
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(converted)
            success += 1
            msg_queue.put(("conv_log", True, os.path.basename(filepath), ""))
        except Exception as e:
            fail += 1
            msg_queue.put(("conv_log", False, os.path.basename(filepath), str(e)))
    msg_queue.put(("conv_done", success, fail))
```

- [ ] **Step 6: 執行測試確認全部通過**

```powershell
venv\Scripts\python.exe -m pytest tests/test_converter.py -v
```

Expected: 11 PASS

- [ ] **Step 7: Commit**

```powershell
git add requirements.txt src/converter.py tests/test_converter.py
git commit -m "feat: add converter module with s2twp conversion"
```

---

## Task 2: 整合轉換到 downloader.py

**Files:**
- Modify: `src/downloader.py`
- Modify: `tests/test_downloader.py`

- [ ] **Step 1: 在 tests/test_downloader.py 加轉換驗證測試**

在 `tests/test_downloader.py` 末尾加入：

```python
def test_download_converts_to_traditional(tmp_path):
    """下載後內容自動轉為繁體中文"""
    # 60 bytes 以上才能通過 HTML 偵測（< 50 bytes 會被擋）
    simplified_content = ("软件" * 30).encode("utf-8")
    session = _mock_session([_ok_resp(content=simplified_content)])
    fp = str(tmp_path / "vol.txt")
    with patch("src.downloader._get_session", return_value=session):
        assert download_volume("1861", 65280, fp) is True
    text = open(fp, encoding="utf-8").read()
    assert "軟體" in text
    assert "软件" not in text
```

- [ ] **Step 2: 執行新測試確認失敗**

```powershell
venv\Scripts\python.exe -m pytest tests/test_downloader.py::test_download_converts_to_traditional -v
```

Expected: FAIL（下載後還是簡體，`assert "軟體" in text` 失敗）

- [ ] **Step 3: 修改 src/downloader.py**

在 `downloader.py` 頂部 imports 加入：
```python
from src.converter import convert_to_traditional
```

在 `download_volume` 內，找到：
```python
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(resp.content)
            return True
```
替換為：
```python
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            text = resp.content.decode("utf-8", errors="replace")
            converted = convert_to_traditional(text)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(converted)
            return True
```

- [ ] **Step 4: 執行所有 downloader 測試確認全部通過**

```powershell
venv\Scripts\python.exe -m pytest tests/test_downloader.py -v
```

Expected: 全部 PASS（注意：舊測試 `test_download_success` 驗證 `open(fp, "rb").read() == CONTENT`，這會失敗，因為現在是文字模式寫入。需要更新該測試。）

如果 `test_download_success` 失敗，將其改為：
```python
def test_download_success(tmp_path):
    session = _mock_session([_ok_resp()])
    fp = str(tmp_path / "vol.txt")
    with patch("src.downloader._get_session", return_value=session):
        assert download_volume("1861", 65280, fp) is True
    assert os.path.exists(fp)
    assert os.path.getsize(fp) > 0
```

- [ ] **Step 5: 執行全部測試確認無回歸**

```powershell
venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 6: Commit**

```powershell
git add src/downloader.py tests/test_downloader.py
git commit -m "feat: auto-convert downloaded content to traditional Chinese"
```

---

## Task 3: 重構 _build_ui() 加入 Notebook

**Files:**
- Modify: `src/main.py`

這是結構性重組。`_build_ui()` 中，所有現有 frame 改 parent 為 `tab_download`，並新增 `tab_convert`。

- [ ] **Step 1: 在 `__init__` 加 `_conv_files` 初始化**

在 `__init__` 的 `self._fail_volumes: list = []` 那行之後加入：
```python
self._conv_files: list[str] = []
```

- [ ] **Step 2: 修改 `_build_ui()` 開頭，加 Notebook 與 tab_download**

找到 `_build_ui` 開頭：
```python
    def _build_ui(self):
        pad = {"padx": 14, "pady": 6}
        self.root.columnconfigure(0, weight=1)
```
替換為：
```python
    def _build_ui(self):
        pad = {"padx": 14, "pady": 6}
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self._notebook = ttk.Notebook(self.root)
        self._notebook.grid(row=0, column=0, sticky="nsew")

        tab_download = ttk.Frame(self._notebook)
        self._notebook.add(tab_download, text="  下載  ")
        tab_download.columnconfigure(0, weight=1)
        tab_download.rowconfigure(1, weight=1)
        tab_download.rowconfigure(3, weight=1)
```

- [ ] **Step 3: 將所有現有 frame 的 parent 從 `self.root` 改為 `tab_download`**

依序找以下四處，將 parent `self.root` 改為 `tab_download`，**並移除對應的 `self.root.rowconfigure` 呼叫**（已移到 Step 2）：

1. `frame_url = ttk.LabelFrame(self.root, ...)` → `ttk.LabelFrame(tab_download, ...)`
2. `frame_volumes = ttk.LabelFrame(self.root, ...)` → `ttk.LabelFrame(tab_download, ...)`
   - 移除：`self.root.rowconfigure(1, weight=1)`
3. `frame_progress = ttk.LabelFrame(self.root, ...)` → `ttk.LabelFrame(tab_download, ...)`
4. `frame_log = ttk.LabelFrame(self.root, ...)` → `ttk.LabelFrame(tab_download, ...)`
   - 移除：`self.root.rowconfigure(3, weight=1)`

- [ ] **Step 4: 在 frame_log 建立之後、separator 之前加 Convert tab**

找到 `# === Status Bar ===` 那段之前，加入：
```python
        tab_convert = ttk.Frame(self._notebook)
        self._notebook.add(tab_convert, text="  轉換  ")
        self._build_convert_tab(tab_convert)
```

- [ ] **Step 5: 確認 separator 和 status_bar 仍掛在 self.root**

檢查 `sep` 和 `self._status_bar` 的 parent 還是 `self.root`（不需改動，維持 row 98、99）。

- [ ] **Step 6: 加入空殼 _build_convert_tab 避免 AttributeError**

在 `_build_ui` 下方加入暫時空殼（Task 4 會填實）：
```python
    def _build_convert_tab(self, tab: ttk.Frame):
        pass
```

- [ ] **Step 7: 執行現有測試確認無回歸**

```powershell
venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 8: 啟動 app 確認主視窗顯示兩個 tab（下載 / 轉換）**

```powershell
start venv\Scripts\python.exe -m src.main
```

確認：
1. 視窗頂部有「下載」和「轉換」兩個 tab
2. 點「下載」tab，原有功能（URL 輸入、卷列表、進度、記錄）正常顯示
3. 點「轉換」tab，目前空白（Step 6 的空殼）
4. Status bar 在兩個 tab 下都可見

關閉視窗。

- [ ] **Step 9: Commit**

```powershell
git add src/main.py
git commit -m "refactor: wrap download UI in Notebook tab, add empty convert tab"
```

---

## Task 4: 實作「轉換」tab 完整 UI 與邏輯

**Files:**
- Modify: `src/main.py`（`_build_convert_tab`、`_on_conv_select`、`_conv_remove_file`、`_refresh_conv_file_list`、`_on_conv_start`、`_poll_queue`）

- [ ] **Step 1: 替換空殼 `_build_convert_tab` 為完整實作**

找到並替換：
```python
    def _build_convert_tab(self, tab: ttk.Frame):
        pass
```
為：
```python
    def _build_convert_tab(self, tab: ttk.Frame):
        pad = {"padx": 14, "pady": 6}
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        tab.rowconfigure(3, weight=1)

        # Header：計數 + 選擇檔案按鈕
        frame_header = ttk.Frame(tab)
        frame_header.grid(row=0, column=0, sticky="ew", **pad)
        frame_header.columnconfigure(0, weight=1)

        self._conv_count_label = ttk.Label(
            frame_header, text="未選擇任何檔案", font=FS
        )
        self._conv_count_label.grid(row=0, column=0, sticky="w")
        ttk.Button(
            frame_header, text="選擇檔案", command=self._on_conv_select, width=10
        ).grid(row=0, column=1)

        # 檔案列表（可捲動）
        frame_files = ttk.LabelFrame(tab, text=" 檔案列表 ", padding=8)
        frame_files.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 6))
        frame_files.columnconfigure(0, weight=1)
        frame_files.rowconfigure(0, weight=1)

        self._conv_canvas = tk.Canvas(frame_files, highlightthickness=0, height=120)
        conv_sb = ttk.Scrollbar(
            frame_files, orient="vertical", command=self._conv_canvas.yview
        )
        self._conv_canvas.configure(yscrollcommand=conv_sb.set)
        self._conv_canvas.grid(row=0, column=0, sticky="nsew")
        conv_sb.grid(row=0, column=1, sticky="ns")

        self._conv_file_frame = ttk.Frame(self._conv_canvas)
        self._conv_file_window = self._conv_canvas.create_window(
            (0, 0), window=self._conv_file_frame, anchor="nw"
        )
        self._conv_file_frame.bind(
            "<Configure>",
            lambda e: self._conv_canvas.configure(
                scrollregion=self._conv_canvas.bbox("all")
            ),
        )
        self._conv_canvas.bind(
            "<Configure>",
            lambda e: self._conv_canvas.itemconfig(
                self._conv_file_window, width=e.width
            ),
        )

        # 輸出模式 + 開始按鈕
        frame_output = ttk.Frame(tab)
        frame_output.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 6))

        ttk.Label(frame_output, text="輸出：", font=FS).pack(side="left")
        self._conv_output_var = tk.StringVar(value="overwrite")
        ttk.Radiobutton(
            frame_output, text="覆蓋原檔",
            variable=self._conv_output_var, value="overwrite"
        ).pack(side="left", padx=(0, 16))
        ttk.Radiobutton(
            frame_output, text="另存新檔（加 _TC 後綴）",
            variable=self._conv_output_var, value="new_file"
        ).pack(side="left")

        self._conv_btn = ttk.Button(
            frame_output, text="開始轉換",
            command=self._on_conv_start, width=10, state="disabled"
        )
        self._conv_btn.pack(side="right")

        # 記錄區
        frame_conv_log = ttk.LabelFrame(tab, text=" 記錄 ", padding=8)
        frame_conv_log.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 6))
        frame_conv_log.columnconfigure(0, weight=1)
        frame_conv_log.rowconfigure(0, weight=1)

        self._conv_log = scrolledtext.ScrolledText(
            frame_conv_log, width=60, height=6,
            state="disabled", font=FM
        )
        self._conv_log.pack(fill="both", expand=True)
```

- [ ] **Step 2: 加入 _on_conv_select、_conv_remove_file、_refresh_conv_file_list**

在 `_build_convert_tab` 之後加入：

```python
    def _on_conv_select(self):
        from tkinter import filedialog
        chosen = filedialog.askopenfilenames(
            title="選擇 TXT 檔案",
            filetypes=[("文字檔案", "*.txt"), ("所有檔案", "*.*")],
        )
        for path in chosen:
            if path not in self._conv_files:
                self._conv_files.append(path)
        self._refresh_conv_file_list()

    def _conv_remove_file(self, path: str):
        self._conv_files.remove(path)
        self._refresh_conv_file_list()

    def _refresh_conv_file_list(self):
        for w in self._conv_file_frame.winfo_children():
            w.destroy()
        for path in self._conv_files:
            row = ttk.Frame(self._conv_file_frame)
            row.pack(fill="x", padx=4, pady=1)
            row.columnconfigure(0, weight=1)
            ttk.Label(row, text=path, font=FS, anchor="w").grid(
                row=0, column=0, sticky="ew"
            )
            ttk.Button(
                row, text="移除", width=5,
                command=lambda p=path: self._conv_remove_file(p),
            ).grid(row=0, column=1, padx=(4, 0))
        n = len(self._conv_files)
        self._conv_count_label.config(
            text=f"已選 {n} 個檔案" if n > 0 else "未選擇任何檔案"
        )
        self._conv_btn.config(state="normal" if n > 0 else "disabled")
        self._conv_canvas.yview_moveto(0)
```

- [ ] **Step 3: 加入 _on_conv_start**

在 `_refresh_conv_file_list` 之後加入：

```python
    def _on_conv_start(self):
        if not self._conv_files:
            return
        files = list(self._conv_files)
        output_mode = self._conv_output_var.get()
        self._conv_btn.config(state="disabled")
        self._conv_log.config(state="normal")
        self._conv_log.delete("1.0", "end")
        self._conv_log.config(state="disabled")
        self._set_status(f"轉換中... 共 {len(files)} 個檔案", "info")
        threading.Thread(
            target=_conv_worker,
            args=(files, output_mode, self.msg_queue),
            daemon=True,
        ).start()
```

- [ ] **Step 4: 加入模組層級 _conv_worker 函式**

在 `class App:` 之前（模組層級）加入：

```python
def _conv_worker(
    files: list[str], output_mode: str, msg_queue: queue.Queue
) -> None:
    from src.converter import run_convert_all
    run_convert_all(files, output_mode, msg_queue)
```

- [ ] **Step 5: 在 `_poll_queue` 加入 conv_log / conv_done 處理**

在 `_poll_queue` 的 `elif kind == "status":` 之前加入：

```python
                elif kind == "conv_log":
                    _, ok, filename, detail = msg
                    icon = "✅" if ok else "❌"
                    line = f"{icon} {filename}"
                    if detail:
                        line += f"（{detail}）"
                    self._conv_log.config(state="normal")
                    self._conv_log.insert("end", line + "\n")
                    self._conv_log.see("end")
                    self._conv_log.config(state="disabled")

                elif kind == "conv_done":
                    _, success, fail = msg
                    self._conv_btn.config(
                        state="normal" if self._conv_files else "disabled"
                    )
                    total = success + fail
                    level = "success" if fail == 0 else "error"
                    self._set_status(f"轉換完成 {success}/{total}", level)
```

- [ ] **Step 6: 執行所有測試確認無回歸**

```powershell
venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 7: 手動驗證轉換 tab**

```powershell
start venv\Scripts\python.exe -m src.main
```

驗證：
1. 點「轉換」tab，看到「未選擇任何檔案」+ [選擇檔案] 按鈕
2. 點「選擇檔案」，選一個 TXT 檔，清單顯示路徑 + [移除] 按鈕，計數更新為「已選 1 個檔案」
3. 再選一個，計數變 2；點「移除」，計數回 1
4. 選「另存新檔（加 _TC 後綴）」，點「開始轉換」
5. 記錄區出現 ✅ 檔名，status bar 顯示「轉換完成 1/1」
6. 確認產生了 `_TC.txt` 新檔，內容為繁體
7. 改選「覆蓋原檔」，再轉一個檔，確認原檔被覆寫為繁體

關閉視窗。

- [ ] **Step 8: Commit**

```powershell
git add src/main.py
git commit -m "feat: implement convert tab with batch s2t conversion UI"
```

---

## Task 5: 更新文件

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TODO.md`

- [ ] **Step 1: 更新 docs/TODO.md**

移除 `1. **簡轉繁**` 那行（已完成），其餘 items 重新編號為 1–4：

```markdown
# TODO

1. **亂碼檢查**：下載完成後驗證內容是否有亂碼或編碼錯誤（optional）
2. **檔案命名格式客製化**：自訂命名樣板（是否含書名、分隔符號等）（optional）
3. **正式卷 vs 外傳自動識別**：系統判斷卷名屬於正式卷或外傳，分別編號或分資料夾存放（optional）
4. **下載隊列 + 暫停/繼續/取消**：個別卷可控制（optional）
```

- [ ] **Step 2: 在 docs/CHANGELOG.md 加 v5 記錄**

在「已完成功能」清單加入：
```
- 下載自動轉繁體（s2twp，opencc-python-reimplemented）
- 「轉換」tab：多選 TXT 批次轉繁體，支援覆蓋原檔或另存 _TC 新檔
```

在更新記錄最上方加入：
```markdown
### 2026-06-10（v5）
- 新增：下載時自動將簡體轉為台灣繁體（全自動，使用 opencc s2twp）
- 新增：主視窗「轉換」tab，支援多選 TXT 批次轉繁，可覆蓋原檔或另存 _TC 新檔
- 重構：主視窗改為 Notebook 結構（下載 / 轉換 兩個 tab）
```

- [ ] **Step 3: Commit**

```powershell
git add docs/CHANGELOG.md docs/TODO.md
git commit -m "docs: update CHANGELOG and TODO for v5 features"
```
