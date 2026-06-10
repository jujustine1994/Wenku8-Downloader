# Wenku8 Downloader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows tkinter tool that downloads light novel volumes from wenku8.net by parsing a catalog URL, scraping all volume info, and downloading each volume as a TXT file with retry logic.

**Architecture:** User pastes `https://www.wenku8.net/modules/article/reader.php?aid=XXXX` → scraper extracts `aid`, fetches catalog HTML, parses volume headers + first chapter `cid` per volume → downloader calculates `vid = cid - 1` and calls `dl.wenku8.com/packtxt.php` per volume → background thread sends queue messages to tkinter UI for live progress.

**Tech Stack:** Python 3.10+, tkinter (built-in), requests, beautifulsoup4, lxml, pytest, requests-mock, uv (venv + package manager)

---

## File Map

| File | Role |
|------|------|
| `Wenku8下載器啟動器.bat` | Double-click entry, calls launcher.ps1 |
| `launcher.ps1` | Env check, venv setup, launches src/main.py |
| `requirements.txt` | Runtime deps |
| `requirements_test.txt` | Test deps |
| `.gitignore` | Excludes venv, cache, downloads |
| `src/config.py` | URLs, retry settings, User-Agent, output dir |
| `src/scraper.py` | `parse_aid_from_url`, `fetch_catalog`, `parse_book_title`, `parse_volumes` |
| `src/downloader.py` | `download_volume`, `build_filepath`, `run_download_all` (thread fn) |
| `src/main.py` | tkinter App class, queue polling, CTH banner |
| `tests/__init__.py` | Empty |
| `tests/conftest.py` | sys.path fix for src imports |
| `tests/test_scraper.py` | Unit tests for scraper (no HTTP) |
| `tests/test_downloader.py` | Unit tests for downloader (requests-mock) |
| `README.md` | Project README |
| `docs/ARCHITECTURE.md` | Tool overview |
| `docs/CHANGELOG.md` | Status + history |
| `docs/PITFALLS.md` | Known issues |
| `docs/TODO.md` | Deferred features |

---

## Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `requirements_test.txt`
- Create: `.gitignore`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `src/__init__.py`

- [ ] **Step 1: Create `requirements.txt`**

```
requests>=2.31.0
beautifulsoup4>=4.12.0
lxml>=4.9.0
sv-ttk>=2.6.0
```

- [ ] **Step 2: Create `requirements_test.txt`**

```
pytest>=7.4.0
requests-mock>=1.11.0
```

- [ ] **Step 3: Create `.gitignore`**

```
venv/
__pycache__/
*.pyc
.env
*.log
cache/
downloads/
```

- [ ] **Step 4: Create `tests/__init__.py`**

Empty file.

- [ ] **Step 5: Create `tests/conftest.py`**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
```

- [ ] **Step 6: Create `src/__init__.py`**

Empty file.

- [ ] **Step 7: Create venv and install deps**

```powershell
uv venv venv
uv pip install -r requirements.txt --python venv\Scripts\python.exe
uv pip install -r requirements_test.txt --python venv\Scripts\python.exe
```

Expected: no errors, `venv/` created.

- [ ] **Step 8: Commit**

```
git init
git add requirements.txt requirements_test.txt .gitignore tests/ src/
git commit -m "feat: project scaffold"
```

---

## Task 2: src/config.py

**Files:**
- Create: `src/config.py`

- [ ] **Step 1: Create `src/config.py`**

```python
CATALOG_BASE_URL = "https://www.wenku8.net/modules/article/reader.php"
DOWNLOAD_BASE_URL = "http://dl.wenku8.com/packtxt.php"
OUTPUT_DIR = "downloads"
RETRY_COUNT = 3
RETRY_DELAY = 2  # seconds between retries

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.wenku8.net/",
}
```

- [ ] **Step 2: Commit**

```
git add src/config.py
git commit -m "feat: add config"
```

---

## Task 3: src/scraper.py (TDD)

**Files:**
- Create: `tests/test_scraper.py`
- Create: `src/scraper.py`

- [ ] **Step 1: Write failing tests in `tests/test_scraper.py`**

```python
import pytest
from bs4 import BeautifulSoup
from src.scraper import parse_aid_from_url, parse_volumes, parse_book_title

SAMPLE_HTML = """
<html>
<head><title>Re:從零開始的異世界生活 - 輕小說文庫</title></head>
<body>
<h2>Re:從零開始的異世界生活</h2>
<table>
  <tr><td colspan="4">第一卷</td></tr>
  <tr>
    <td><a href="reader.php?aid=1861&cid=65281">序章</a></td>
    <td><a href="reader.php?aid=1861&cid=65282">第一章</a></td>
  </tr>
  <tr><td colspan="4">第二卷</td></tr>
  <tr>
    <td><a href="reader.php?aid=1861&cid=67829">序章</a></td>
  </tr>
  <tr><td colspan="4">第三卷</td></tr>
  <tr>
    <td><a href="reader.php?aid=1861&cid=70001">第一章</a></td>
  </tr>
</table>
</body></html>
"""


def test_parse_aid_basic():
    url = "https://www.wenku8.net/modules/article/reader.php?aid=1861"
    assert parse_aid_from_url(url) == "1861"


def test_parse_aid_with_cid():
    url = "https://www.wenku8.net/modules/article/reader.php?aid=1861&cid=65281"
    assert parse_aid_from_url(url) == "1861"


def test_parse_aid_missing_raises():
    with pytest.raises(ValueError):
        parse_aid_from_url("https://www.wenku8.net/modules/article/reader.php")


def test_parse_volumes_count():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    volumes = parse_volumes(soup)
    assert len(volumes) == 3


def test_parse_volumes_first():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    v = parse_volumes(soup)[0]
    assert v["index"] == 1
    assert v["name"] == "第一卷"
    assert v["first_cid"] == 65281
    assert v["vid"] == 65280


def test_parse_volumes_no_prelude():
    # Third volume has 第一章 instead of 序章 — must still work
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    v = parse_volumes(soup)[2]
    assert v["first_cid"] == 70001
    assert v["vid"] == 70000


def test_parse_book_title_h2():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    assert parse_book_title(soup) == "Re:從零開始的異世界生活"


def test_parse_book_title_fallback():
    html = "<html><head><title>灼眼的夏娜 - 輕小說文庫</title></head><body></body></html>"
    soup = BeautifulSoup(html, "lxml")
    assert parse_book_title(soup) == "灼眼的夏娜"
```

- [ ] **Step 2: Run tests to confirm they fail**

```powershell
venv\Scripts\python.exe -m pytest tests/test_scraper.py -v
```

Expected: all FAIL with `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Implement `src/scraper.py`**

```python
import urllib.parse
import requests
from bs4 import BeautifulSoup
from src.config import CATALOG_BASE_URL, HEADERS


def parse_aid_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    if "aid" not in params:
        raise ValueError(f"No 'aid' parameter in URL: {url}")
    return params["aid"][0]


def fetch_catalog(aid: str) -> BeautifulSoup:
    url = f"{CATALOG_BASE_URL}?aid={aid}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "lxml")


def parse_book_title(soup: BeautifulSoup) -> str:
    h2 = soup.find("h2")
    if h2:
        return h2.get_text(strip=True)
    title_tag = soup.find("title")
    if title_tag:
        return title_tag.get_text(strip=True).split(" - ")[0].strip()
    return "未知書名"


def parse_volumes(soup: BeautifulSoup) -> list[dict]:
    volumes = []
    current_volume = None
    volume_index = 0
    found_first_chapter = False

    for row in soup.find_all("tr"):
        cells = row.find_all("td")

        # Volume header: single full-width cell, no links inside
        if (len(cells) == 1
                and cells[0].get("colspan")
                and not cells[0].find("a")):
            current_volume = {
                "index": volume_index + 1,
                "name": cells[0].get_text(strip=True),
            }
            volume_index += 1
            found_first_chapter = False
            continue

        # First chapter link under current volume
        if current_volume and not found_first_chapter:
            first_link = row.find("a")
            if first_link and first_link.get("href"):
                parsed = urllib.parse.urlparse(first_link["href"])
                params = urllib.parse.parse_qs(parsed.query)
                if "cid" in params:
                    cid = int(params["cid"][0])
                    volumes.append({
                        **current_volume,
                        "first_cid": cid,
                        "vid": cid - 1,
                    })
                    found_first_chapter = True

    return volumes
```

- [ ] **Step 4: Run tests to confirm they pass**

```powershell
venv\Scripts\python.exe -m pytest tests/test_scraper.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```
git add src/scraper.py tests/test_scraper.py
git commit -m "feat: scraper — parse aid, catalog, volumes (TDD)"
```

---

## Task 4: src/downloader.py (TDD)

**Files:**
- Create: `tests/test_downloader.py`
- Create: `src/downloader.py`

- [ ] **Step 1: Write failing tests in `tests/test_downloader.py`**

```python
import os
import queue
from unittest.mock import patch
import pytest
from src.downloader import download_volume, build_filepath, run_download_all

DOWNLOAD_URL = "http://dl.wenku8.com/packtxt.php?aid=1861&vid=65280&charset=utf-8"
CONTENT = "A" * 500


def test_download_success(tmp_path, requests_mock):
    requests_mock.get(DOWNLOAD_URL, text=CONTENT)
    fp = str(tmp_path / "vol.txt")
    assert download_volume("1861", 65280, fp) is True
    assert open(fp, encoding="utf-8").read() == CONTENT


def test_download_retry_then_success(tmp_path, requests_mock):
    requests_mock.get(DOWNLOAD_URL, [
        {"exc": Exception("timeout")},
        {"exc": Exception("timeout")},
        {"text": CONTENT},
    ])
    fp = str(tmp_path / "retry.txt")
    with patch("src.downloader.time.sleep"):
        assert download_volume("1861", 65280, fp) is True


def test_download_all_fail(tmp_path, requests_mock):
    requests_mock.get(DOWNLOAD_URL, exc=Exception("unreachable"))
    fp = str(tmp_path / "fail.txt")
    with patch("src.downloader.time.sleep"):
        assert download_volume("1861", 65280, fp) is False


def test_build_filepath_basic():
    path = build_filepath("downloads", "灼眼的夏娜", 1, "第一卷", 18)
    expected = os.path.join("downloads", "灼眼的夏娜", "01 灼眼的夏娜 第一卷.txt")
    assert path == expected


def test_build_filepath_triple_digit():
    path = build_filepath("downloads", "某書", 1, "第一卷", 100)
    assert "001 某書 第一卷.txt" in path


def test_run_download_all_messages(tmp_path, requests_mock):
    url1 = "http://dl.wenku8.com/packtxt.php?aid=1&vid=99&charset=utf-8"
    url2 = "http://dl.wenku8.com/packtxt.php?aid=1&vid=199&charset=utf-8"
    requests_mock.get(url1, text="X" * 500)
    requests_mock.get(url2, text="Y" * 500)

    volumes = [
        {"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99},
        {"index": 2, "name": "第二卷", "first_cid": 200, "vid": 199},
    ]
    q = queue.Queue()
    run_download_all("1", "TestBook", volumes, str(tmp_path), q)

    messages = []
    while not q.empty():
        messages.append(q.get())

    types = [m[0] for m in messages]
    assert "progress" in types
    assert "log" in types
    assert messages[-1][0] == "done"
    assert messages[-1][1] == 2  # success count
```

- [ ] **Step 2: Run tests to confirm they fail**

```powershell
venv\Scripts\python.exe -m pytest tests/test_downloader.py -v
```

Expected: all FAIL.

- [ ] **Step 3: Implement `src/downloader.py`**

```python
import os
import time
import queue
import requests
from src.config import DOWNLOAD_BASE_URL, HEADERS, RETRY_COUNT, RETRY_DELAY, OUTPUT_DIR


def download_volume(aid: str, vid: int, filepath: str) -> bool:
    url = f"{DOWNLOAD_BASE_URL}?aid={aid}&vid={vid}&charset=utf-8"
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            if len(resp.content) < 50:
                raise ValueError("Response too short — likely an error page")
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(resp.content)
            return True
        except Exception:
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_DELAY)
    return False


def build_filepath(output_dir: str, book_name: str, volume_index: int,
                   volume_name: str, total: int) -> str:
    pad = max(len(str(total)), 2)
    index_str = str(volume_index).zfill(pad)
    safe = lambda s: "".join(c for c in s if c not in r'\/:*?"<>|')
    filename = f"{index_str} {safe(book_name)} {safe(volume_name)}.txt"
    return os.path.join(output_dir, safe(book_name), filename)


def run_download_all(aid: str, book_name: str, volumes: list[dict],
                     output_dir: str, msg_queue: queue.Queue) -> None:
    total = len(volumes)
    success = 0
    fail_list = []
    pad = max(len(str(total)), 2)

    for i, vol in enumerate(volumes, 1):
        msg_queue.put(("progress", i, total, vol["name"]))
        filepath = build_filepath(output_dir, book_name, vol["index"], vol["name"], total)
        ok = download_volume(aid, vol["vid"], filepath)
        index_str = str(vol["index"]).zfill(pad)
        if ok:
            success += 1
            msg_queue.put(("log", "ok", index_str, vol["name"], ""))
        else:
            fail_list.append(vol["name"])
            msg_queue.put(("log", "fail", index_str, vol["name"], "retry 3x 失敗"))

    msg_queue.put(("done", success, fail_list))
```

- [ ] **Step 4: Run tests to confirm they pass**

```powershell
venv\Scripts\python.exe -m pytest tests/test_downloader.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```
git add src/downloader.py tests/test_downloader.py
git commit -m "feat: downloader — download, retry, filepath builder (TDD)"
```

---

## Task 5: src/main.py (tkinter UI)

**Files:**
- Create: `src/main.py`

> **Before writing any code:** Read the following files in order:
> 1. `C:\Users\CTH\.claude\project-rules\windows-tool\tkinter-ui\skeleton.py`
> 2. `C:\Users\CTH\.claude\project-rules\windows-tool\tkinter-ui\pattern_cth_banner.py`
> 3. `C:\Users\CTH\.claude\project-rules\windows-tool\tkinter-ui\pattern_topmost.py`
> 4. `C:\Users\CTH\.claude\project-rules\windows-tool\tkinter-ui\pattern_indeterminate.py`
> 5. `C:\Users\CTH\.claude\project-rules\windows-tool\tkinter-ui\pattern_status_bar.py`
>
> Use skeleton.py as the structural base. Integrate patterns exactly as defined.

- [ ] **Step 1: Read all 5 pattern files listed above before writing any code**

- [ ] **Step 2: Implement `src/main.py`**

Structure (fill in from skeleton + patterns):

```
Font constants (F, FS, FB, FM) — copy exactly from INDEX.md
THEMES dict — copy from skeleton.py
CTH banner function — copy from pattern_cth_banner.py (Python version)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        # DPI awareness (from skeleton)
        # Window title, size, min size
        # Theme setup (sv-ttk with fallback)
        # Build UI sections in order:
        #   1. URL input row (Entry + 載入 button)
        #   2. Book title label (populated after load)
        #   3. Volume listbox with scrollbar
        #   4. 下載全部 button (disabled until volumes loaded)
        #   5. Progress section: label + indeterminate bar → determinate bar
        #      Phase 1 (loading catalog): indeterminate
        #      Phase 2 (downloading): determinate with "02/18 第二卷..."
        #   6. Log area (ScrolledText, FM font, read-only)
        #   7. Status bar (from pattern_status_bar.py)
        self._queue = queue.Queue()
        self._volumes = []
        self._aid = None
        self._book_name = None
        self._poll_queue()

    def _on_load(self):
        # Validate URL, extract aid via parse_aid_from_url
        # Disable load button, start indeterminate progress
        # Run fetch_catalog + parse_volumes in background thread
        # Thread puts ("catalog_done", book_name, volumes) or ("catalog_error", msg) on queue
        pass

    def _on_download(self):
        # Disable download button
        # Switch to determinate progress bar
        # Start thread: run_download_all(aid, book_name, volumes, OUTPUT_DIR, queue)
        pass

    def _poll_queue(self):
        try:
            while True:
                msg = self._queue.get_nowait()
                self._handle_msg(msg)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _handle_msg(self, msg):
        kind = msg[0]
        if kind == "catalog_done":
            # _, book_name, volumes = msg
            # Update title label, populate listbox, enable download button
            # Stop indeterminate bar
            pass
        elif kind == "catalog_error":
            # _, error_msg = msg
            # Show error in status bar, re-enable load button
            pass
        elif kind == "progress":
            # _, current, total, vol_name = msg
            # Update progress bar value and label
            pass
        elif kind == "log":
            # _, status, index_str, vol_name, detail = msg
            # Append to log: "✅ 01 第一卷" or "❌ 01 第一卷（retry 3x 失敗）"
            pass
        elif kind == "done":
            # _, success_count, fail_list = msg
            # Update status bar: "完成 X/N，失敗 Y 卷"
            # Re-enable buttons
            pass

def main():
    show_cth_banner()  # Python version from signature.md
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the app to verify UI renders correctly**

```powershell
venv\Scripts\python.exe src/main.py
```

Expected: CTH banner in terminal, tkinter window opens. URL input visible, buttons present.

- [ ] **Step 4: Manual smoke test**
  - Paste `https://www.wenku8.net/modules/article/reader.php?aid=1861` → click 載入
  - Verify: book title appears, volume list populates
  - Click 下載全部
  - Verify: progress bar advances, log shows ✅ per volume, `downloads/` folder created

- [ ] **Step 5: Commit**

```
git add src/main.py
git commit -m "feat: tkinter UI — catalog load, download progress, log"
```

---

## Task 6: Launcher Files

**Files:**
- Create: `Wenku8下載器啟動器.bat`
- Create: `launcher.ps1`

> **Before writing:** Read `C:\Users\CTH\.claude\project-rules\windows-tool\windows-tool-pitfalls.md` then `C:\Users\CTH\.claude\project-rules\windows-tool\windows-tool-templates.md`.

- [ ] **Step 1: Read pitfalls.md and templates.md**

- [ ] **Step 2: Create `Wenku8下載器啟動器.bat`**

```bat
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher.ps1"
```

- [ ] **Step 3: Create `launcher.ps1`** (follow template exactly, include CTH PS banner)

Key sections:
```powershell
# UTF-8 output
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Show-CTHBanner function — copy from signature.md PowerShell version verbatim
# Show-CTHBanner call

# Check Python
# Check uv
# If venv doesn't exist → explain what will be installed, create venv, install deps
# Activate and launch: venv\Scripts\python.exe src\main.py
# Handle exit code, pause on error
```

- [ ] **Step 4: Add UTF-8 BOM to launcher.ps1** (per pitfalls地雷五)

```powershell
# In PowerShell terminal:
$content = Get-Content launcher.ps1 -Raw -Encoding UTF8
[System.IO.File]::WriteAllText(
    (Resolve-Path launcher.ps1),
    $content,
    [System.Text.UTF8Encoding]::new($true)
)
```

- [ ] **Step 5: Double-click `Wenku8下載器啟動器.bat` to verify it launches correctly**

- [ ] **Step 6: Commit**

```
git add "Wenku8下載器啟動器.bat" launcher.ps1
git commit -m "feat: launcher bat + ps1 with env check and venv setup"
```

---

## Task 7: Documentation Files

**Files:**
- Create: `README.md`
- Create: `docs/ARCHITECTURE.md`
- Create: `docs/CHANGELOG.md`
- Create: `docs/PITFALLS.md`
- Create: `docs/TODO.md`

> **Before writing README.md:** Read `C:\Users\CTH\.claude\project-rules\templates\readme-template-code.md` and use it as template. Add CTH banner block at the very top per signature.md.

- [ ] **Step 1: Create `README.md`** using readme-template-code.md, `類型` = `Windows 工具`

- [ ] **Step 2: Create `docs/ARCHITECTURE.md`**

Include:
- Tool overview (1 paragraph)
- Directory structure (copy from file map above)
- File responsibilities (one line each)
- Execution flow (URL paste → scrape → download → output)
- Key config variables (CATALOG_BASE_URL, DOWNLOAD_BASE_URL, OUTPUT_DIR, RETRY_COUNT)
- Queue message protocol (progress / log / done / catalog_done / catalog_error)

- [ ] **Step 3: Create `docs/CHANGELOG.md`**

```markdown
## 現狀

**已完成功能：**
- URL 解析（aid 提取）
- 目錄頁爬取與卷列表解析
- 逐卷下載（retry 3x）
- tkinter UI（進度條、記錄區）
- 啟動器（BAT + PS1）

**尚未完成：**
- 見 docs/TODO.md

---

## 更新記錄

### 2026-06-10
- 新增：初始版本，完成主要下載功能
```

- [ ] **Step 4: Create `docs/PITFALLS.md`**

```markdown
# PITFALLS

## P1: 網站返回 403
- **問題**：requests 未設 User-Agent 時 wenku8.net 返回 403
- **解法**：在 config.py 的 HEADERS 設定完整 Chrome User-Agent + Referer
- **禁止**：不帶 headers 直接 requests.get

## P2: launcher.ps1 必須有 UTF-8 BOM
- **問題**：PS1 無 BOM 時中文訊息亂碼
- **解法**：用 [System.IO.File]::WriteAllText 寫入時指定 UTF8Encoding($true)
- **禁止**：用 Set-Content / Out-File 寫 PS1（預設 UTF-16）

## P3: BAT 路徑不可含中文
- **問題**：BAT 用 CMD CP950 讀取，路徑含中文會亂碼導致無法呼叫 PS1
- **解法**：launcher.ps1 統一用英文命名，BAT 只含兩行
```

- [ ] **Step 5: Create `docs/TODO.md`**

```markdown
# TODO

1. **簡轉繁**：下載後自動將簡體中文轉換為繁體中文
2. **亂碼檢查**：下載完成後驗證內容是否有亂碼或編碼錯誤
3. **輸出資料夾選擇**：讓使用者自訂下載目的地資料夾（目前固定為 downloads/）
4. **檔案命名格式客製化**：自訂命名樣板（是否含書名、分隔符號等）
5. **正式卷 vs 外傳自動識別**：系統判斷卷名屬於正式卷或外傳，分別編號或分資料夾存放
6. **下載隊列 + 暫停/繼續/取消**：方案三，個別卷可控制
7. **失敗卷單獨重試**：完成後可針對失敗的卷重新下載
```

- [ ] **Step 6: Commit**

```
git add README.md docs/
git commit -m "docs: architecture, changelog, pitfalls, todo, readme"
```

---

## Known Risks

| Risk | Mitigation |
|------|-----------|
| wenku8 HTML structure differs from screenshot | Smoke test Task 5 Step 4 will catch this; parser may need adjustment to colspan detection logic |
| 403 on catalog fetch | HEADERS in config.py include User-Agent + Referer; if still blocked, add cookie handling |
| Download URL domain mismatch (wenku8.net vs .com) | DOWNLOAD_BASE_URL uses `dl.wenku8.com`; validate during smoke test |
| Volume name contains filesystem-illegal chars | `build_filepath` strips `\ / : * ? " < > |` |
