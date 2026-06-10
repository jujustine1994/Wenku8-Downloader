# ARCHITECTURE — Wenku8 Downloader

## 工具概覽

從 wenku8.net 的書籍目錄頁自動解析所有卷次，並批次下載為 TXT 檔。
使用者只需貼上網址，工具自動完成目錄爬取、卷次解析、下載與命名。

## 目錄結構

```
root/
  Wenku8下載器啟動器.bat   ← 雙擊入口
  launcher.ps1             ← 環境檢查、venv 建立、啟動 src/main.py
  requirements.txt         ← runtime 套件
  requirements_test.txt    ← 測試套件
  README.md
  .gitignore

  src/
    main.py                ← tkinter UI 主程式、CTH banner 入口
    scraper.py             ← 目錄頁爬取與卷列表解析
    downloader.py          ← 下載邏輯、retry、filepath 建構
    config.py              ← URL 常數、retry 設定、User-Agent

  tests/
    conftest.py            ← sys.path 修正
    test_scraper.py        ← scraper 單元測試（無 HTTP）
    test_downloader.py     ← downloader 單元測試（requests-mock）

  docs/
    ARCHITECTURE.md        ← 本檔
    CHANGELOG.md
    PITFALLS.md
    TODO.md
    superpowers/specs/     ← 設計規格文件
    superpowers/plans/     ← 實作計畫文件

  downloads/               ← 輸出（gitignored）
```

## 檔案職責

| 檔案 | 職責 |
|------|------|
| `src/config.py` | 所有 URL、retry、headers 常數集中管理 |
| `src/scraper.py` | parse_aid_from_url / fetch_catalog / parse_book_title / parse_volumes |
| `src/downloader.py` | download_volume（retry）/ build_filepath / run_download_all（thread fn）|
| `src/main.py` | tkinter App、queue 輪詢、UI 事件處理 |
| `launcher.ps1` | Python/uv 檢查、首次安裝說明、venv 建立、啟動 |

## 執行流程

```
使用者雙擊 BAT
  → launcher.ps1 檢查 Python / uv / venv
  → venv\Scripts\python.exe src\main.py
  → 終端顯示 CTH banner
  → tkinter 視窗開啟

使用者貼上 URL → 點「載入」
  → parse_aid_from_url 提取 aid
  → 背景 thread: fetch_catalog(aid) → parse_volumes(soup)
  → queue: ("catalog_done", book_name, volumes)
  → UI 顯示卷列表

使用者點「下載全部」
  → 背景 thread: run_download_all(aid, book_name, volumes, output_dir, queue)
  → 每卷: download_volume(aid, vid) → retry 最多 3 次
  → queue: ("progress", ...) / ("log", ...) / ("done", ...)
  → UI 即時更新進度條與記錄

輸出:
  downloads/
    書名/
      01 書名 第一卷.txt
      02 書名 第二卷.txt
      ...
```

## 關鍵設定變數（src/config.py）

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `CATALOG_BASE_URL` | `https://www.wenku8.net/modules/article/reader.php` | 書籍目錄頁 URL |
| `DOWNLOAD_BASE_URL` | `http://dl.wenku8.com/packtxt.php` | 下載 URL |
| `OUTPUT_DIR` | `downloads` | 輸出資料夾（相對於專案根目錄）|
| `RETRY_COUNT` | `3` | 每卷最大重試次數 |
| `RETRY_DELAY` | `2` | 重試間隔秒數 |

## Queue 訊息協定（src/main.py ↔ thread）

| 類型 | 格式 | 說明 |
|------|------|------|
| `catalog_done` | `("catalog_done", book_name, volumes)` | 目錄載入成功 |
| `catalog_error` | `("catalog_error", error_msg)` | 目錄載入失敗 |
| `progress` | `("progress", current, total, vol_name)` | 下載進度更新 |
| `log` | `("log", status, index_str, vol_name, detail)` | 單卷完成或失敗 |
| `done` | `("done", success_count, fail_list)` | 全部下載完成 |
| `status` | `("status", (msg, level))` | 狀態列更新（level: info/success/error）|
