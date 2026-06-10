# Wenku8 Downloader — Design Spec
Date: 2026-06-10

## Overview

A Windows desktop tool (Python + tkinter) that downloads light novels from wenku8.net by volume, given a book's catalog URL. Downloads are organised into per-book folders with zero-padded volume filenames.

---

## Input & URL Parsing

User pastes the book catalog URL into the tool:
```
https://www.wenku8.net/modules/article/reader.php?aid=1861
```

Tool extracts `aid` from the query string. No manual input of `vid` or `cid` required.

---

## Scraping Logic

### Catalog page
URL: `https://www.wenku8.net/modules/article/reader.php?aid={aid}`

The page renders an HTML table where:
- Volume headers are full-width rows (`<td colspan="4">第X卷</td>` or similar)
- Chapter links follow each header row, in the format `reader.php?aid=...&cid=XXXXX`

### Volume discovery algorithm
1. Fetch catalog page with a browser User-Agent header
2. Parse HTML with BeautifulSoup
3. Walk the table row by row:
   - If row is a volume header → record volume name, reset "first link found" flag
   - If row contains `<a>` links and first link not yet found for this volume → record the first `cid`
4. Result: list of `(volume_index, volume_name, first_cid)`

**Key invariant:** first chapter detection is position-based, not name-based. Works regardless of whether the first chapter is called 序章, 第一章, or anything else.

### Download URL construction
```
vid = first_cid - 1
download_url = http://dl.wenku8.com/packtxt.php?aid={aid}&vid={vid}&charset=utf-8
```

---

## Architecture

```
root/
  Wenku8下載器啟動器.bat   ← double-click entry point
  launcher.ps1             ← env check, venv setup, launches main.py
  requirements.txt
  README.md
  .gitignore

  src/
    main.py                ← tkinter UI, entry point, CTH banner
    scraper.py             ← fetch catalog, parse volumes
    downloader.py          ← download volumes, retry logic, background thread
    config.py              ← output dir, retry settings

  docs/
    ARCHITECTURE.md
    CHANGELOG.md
    PITFALLS.md
    TODO.md
    superpowers/specs/     ← this file

  downloads/               ← output (gitignored)
  cache/                   ← gitignored
```

---

## UI Layout

```
┌─────────────────────────────────────────┐
│  Wenku8 Downloader          [CTH Banner] │
├─────────────────────────────────────────┤
│  貼上書籍目錄網址                         │
│  [________________________________] [載入]│
├─────────────────────────────────────────┤
│  書名：<解析後顯示>                       │
│  卷列表                                   │
│  ┌─────────────────────────────────┐    │
│  │ 第一卷  (cid: 65281)            │    │
│  │ 第二卷  (cid: 67829)            │    │
│  └─────────────────────────────────┘    │
│                         [下載全部]       │
├─────────────────────────────────────────┤
│  進度                                    │
│  正在下載 02/18：第二卷...               │
│  [████████░░░░░░░░░░]  11%             │
├─────────────────────────────────────────┤
│  記錄                                    │
│  ✅ 01 第一卷                            │
│  ⏳ 02 第二卷（retry 1/3）               │
│  ❌ 03 第三卷（3次失敗，已跳過）          │
└─────────────────────────────────────────┘
```

---

## Download & Retry Logic

- Downloads run in a **background thread** (keeps UI responsive)
- Per-volume retry: up to **3 attempts** with a short delay between retries
- On final failure: mark volume as ❌, log error, continue to next volume
- Progress updates sent back to UI via a thread-safe queue
- End of run: show summary (成功 X/N，失敗清單)

### Error states
| Condition | Behaviour |
|-----------|-----------|
| HTTP error on catalog fetch | Show error in UI, abort load |
| HTTP error on volume download | Retry up to 3x, then mark failed |
| Partial/empty download | Treat as failure, retry |
| All volumes failed | Show full failure summary |

---

## Output

```
downloads/
  Re:從零開始的異世界生活/
    01 Re:從零開始的異世界生活 第一卷.txt
    02 Re:從零開始的異世界生活 第二卷.txt
    ...
    18 Re:從零開始的異世界生活 第十八卷.txt
```

Filename format: `{zero_padded_index} {book_name} {volume_name}.txt`
- Index zero-padded to 2 digits (or 3 if >99 volumes)
- Book name parsed from catalog page title

---

## Known Risks

- **Anti-scraping (403):** WebFetch returns 403; Python `requests` with browser User-Agent should work. Validate at implementation time.
- **HTML structure variation:** Volume header detection assumes `colspan` full-width rows. Some books may use different markup — handle gracefully with a fallback or clear error.
- **Download domain:** Uses `dl.wenku8.com`; if the site moves to `dl.wenku8.net`, URL needs updating.

---

## TODO (deferred features)

- **簡轉繁**：下載後自動將簡體中文轉換為繁體中文
- **亂碼檢查**：下載完成後驗證內容是否有亂碼或編碼錯誤
- **輸出資料夾選擇**：讓使用者自訂下載目的地資料夾（目前固定為 `downloads/`）
- **檔案命名格式客製化**：自訂命名樣板（例如是否含書名、分隔符號等）
- **正式卷 vs 外傳自動識別**：系統判斷卷名屬於正式卷或外傳，分別編號或分資料夾存放
- Download queue with pause / resume / cancel per volume
- Re-download individual failed volumes
