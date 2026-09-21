# ARCHITECTURE — Wenku8 Downloader

## 工具概覽

從 wenku8.net 的書籍目錄頁自動解析所有卷次，並批次下載為 TXT 檔。
使用者只需貼上網址，工具自動完成目錄爬取、卷次解析、下載、簡轉繁、命名，
下載完成後若有失敗/亂碼卷會自動接續修復；另可隨時掃描既有輸出資料夾找出缺檔/亂碼卷補進修復清單。

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
    main.py                ← tkinter UI 主程式、queue 輪詢、按鈕狀態機
    scraper.py              ← 目錄頁爬取、卷列表解析、正式卷/外傳分類與編號
    downloader.py            ← 下載/修復邏輯、retry、亂碼偵測、filepath 建構
    converter.py             ← 簡轉繁核心（OpenCC）、本機檔案編碼偵測（轉換 tab 用）
    verify.py                 ← 單卷完整性判定（章節標題錨點、字數 fallback）
    manifest.py               ← 輸出資料夾的下載紀錄 .wenku8.json 讀寫、更新比對
    logutil.py                ← 執行紀錄（logs/app.log）共用模組
    config.py                  ← URL 常數、預設 retry 設定
    .tool_config.json          ← 使用者本機設定持久化（輸出路徑、retry、命名、外傳關鍵字...；gitignored）

  tests/
    conftest.py             ← sys.path 修正
    test_scraper.py         ← scraper 單元測試（無 HTTP）
    test_downloader.py      ← downloader 單元測試（unittest.mock 模擬 curl_cffi session）
    test_converter.py       ← converter 單元測試（本機檔案編碼偵測、簡轉繁）
    test_main_helpers.py    ← main.py 內可獨立測試的純函式（例如 resolve_output_dir）

  docs/
    ARCHITECTURE.md        ← 本檔
    CHANGELOG.md
    PITFALLS.md
    TODO.md
    superpowers/specs/     ← 設計規格文件
    superpowers/plans/     ← 實作計畫文件

  downloads/               ← 輸出（gitignored，實際路徑可在 UI 自訂）
    .wenku8.json           ← 下載紀錄 manifest，一個資料夾一個檔、內部按 aid 分書
  logs/app.log             ← 執行紀錄（main.py / downloader.py 共用，不分割、不輪替）
```

## 檔案職責

| 檔案 | 職責 |
|------|------|
| `src/config.py` | URL、預設 retry 常數集中管理（使用者實際生效的 retry/命名/外傳關鍵字設定存在 `.tool_config.json`，由 `main.py` 讀寫） |
| `src/verify.py` | `normalize`（比對前統一標點與空白）／`verify_volume`（章節標題錨點命中率 + 最後錨點位置判定 complete/suspect/garbled，無錨點時退回字數）／`verify_file`。純函式，無網路與 UI 依賴 |
| `src/manifest.py` | `.wenku8.json` 的 `load`／`save`／`record_volume`／`median_chars`／`rebuild_from_files`（舊資料夾按檔名回推，不重抓）／`plan_update`（把每卷分到 new／incomplete／changed／chapters_changed／script_mismatch／ok 剛好一組）。**不可 import `downloader`**，算檔名由呼叫端傳 `build_path` callable 進來 |
| `src/scraper.py` | `parse_aid_from_url` / `parse_vid_from_url` / `parse_cid_from_url` / `find_volume_by_cid`（單卷網址）／ `fetch_catalog` / `parse_book_title` / `parse_volumes`（目錄爬取解析，每卷帶 `chapters`：cid + 原始簡體標題）；`classify_volume` / `classify_volumes` / `resequence_by_category` / `assign_categories_and_sequence` / `format_index_token`（正式卷/外傳分類與各自獨立編號，供 Preview 視窗與檔名共用） |
| `src/downloader.py` | `build_filepath`（**檔名的唯一真相來源**，四條路徑共用；`convert_traditional=True` 時書名與卷名也轉繁，轉換在濾非法字元之前）；`download_volume`（初次下載，utf-8/gbk 比對亂碼）/ `repair_volume`（修復，持續重試直到無亂碼或停滯放棄，接受 `max_attempts` 讓無限重試模式也能有界放棄）/ `check_garbled`（含容錯，非 UTF-8 檔案視為亂碼而非拋例外）/ `scan_existing_volumes`（純本地比對卷列表與磁碟檔案，不發網路請求）/ `build_filepath` / `run_download_all`、`run_repair_all`（thread 入口，透過 `msg_queue` 回報進度） |
| `src/converter.py` | `convert_to_traditional`（簡轉繁核心，OpenCC s2twp）；`_detect_and_decode`（本機既有檔案的 BOM 偵測 + utf-8/gbk/big5 比對，供「轉換」tab 用）；`run_download_all`/`repair_volume` 下載完成後都會呼叫 `convert_to_traditional` |
| `src/logutil.py` | 執行紀錄共用模組（`logs/app.log`，main.py/downloader.py 共用同一檔案，不分割、不輪替；`_extract_status` 從例外取 HTTP status code） |
| `src/main.py` | tkinter `App` 類別：三個分頁（下載/轉換/設定）、Preview 分類視窗、queue 輪詢與按鈕狀態機、下載完自動接續修復鏈 |
| `launcher.ps1` | Python/uv 檢查、首次安裝說明、venv 建立、啟動 |

## 簡轉繁兩層邏輯（src/converter.py）

轉換分兩層，順序：原文 → OpenCC → `_OVERRIDES` → 輸出。

1. **OpenCC `s2twp`**：詞庫式轉換，會依上下文判斷同一簡體字對應的繁體字（如「頭發→頭髮」「出發→出發」），但仍有已知誤轉（如把小說常用的「只是」誤判成量詞「一隻貓」的「隻」、把「范先生」的姓氏誤判成「範」、「台」被轉成公文正式異體字「臺／檯」）。
2. **`_OVERRIDES`**：OpenCC 轉完後再跑一輪**無上下文的全域字串 `.replace()`**，把已知誤轉結果強制改回來。目前 5 條：`賓士→奔馳`、`隻→只`、`臺→台`、`檯→台`、`範→范`。這是刻意選擇「寧可不翻、不要錯翻」——例如「隻→只」這條也會連帶把真的該用「隻」的「一隻貓」改成「一只貓」，是已知且接受的副作用。

**為什麼不直接改 OpenCC 本身、而要疊加這層：** `opencc-python-reimplemented` 套件的 `OpenCC(conversion)` 建構子寫死只接受設定檔「名稱」字串（如 `"s2twp"`），程式內部直接組路徑讀套件自己資料夾裡的 json/詞典（`venv/Lib/site-packages/opencc/opencc.py` 的 `os.path.join(os.path.dirname(__file__), CONFIG_DIR, config)`），**不像原版 C++ OpenCC 那樣開放傳入自訂設定檔或自訂詞典**。就算直接改 `venv/Lib/site-packages/opencc/dictionary/*.txt`，`venv/` 也不進版控，換機器或重新 `uv pip install` 就會被覆蓋消失。`_OVERRIDES` 寫在 `src/converter.py`（會進版控、跟著發布）是目前唯一能持久生效的修正方式。

新增 override 前，可用專案的 venv 直接跑 `OpenCC('s2twp').convert(...)` 測試候選字詞的轉換結果，確認是否誤轉、副作用範圍多大，再決定要不要加。

## 完整性判定與 manifest（src/verify.py、src/manifest.py）

**為什麼需要。** 原本的驗收只有 `check_garbled()`：能不能用 UTF-8 讀、含不含 `�`。
伺服器回 HTTP 200 但內容不完整時，檔案是合法 UTF-8、也沒有 `�`，一律判定成功。
（真正的傳輸中斷 curl 多半直接拋例外，已被 retry 接住，不是這裡要解的問題。）

**判定方式。** 用目錄頁的章節標題當錨點：完整的卷，每個章節標題都會出現在 txt 裡；
斷檔的卷後半段標題會整批消失。門檻是 2026-09-21 實測 aid=1861 第 1／21／57 卷定的，
三個都有實際踩到的坑，改門檻前先讀 `src/verify.py` 的 docstring：

1. **標點會對不上**——第 21 卷有一章目錄與 txt 用了不同的間隔號，全等比對誤判缺章，
   但該卷實際完整。所以比對前兩邊都要過 `normalize()`。
2. **短標題會誤命中**——2 字標題（插圖、後記之類）會命中正文裡的同字，位置還會亂跳。
   所以只有正規化後長度 ≥ 4 的標題能當錨點。
3. **cid 不出現在 txt 內容裡**（實測確認）。cid 只能當 manifest 的穩定識別碼，驗不了內容。
4. **錨點少於 3 個就不採信**（實測 aid=1832）。那本書的章節標題全是「序章／第一章／
   後記／插圖」這種 2–3 字光禿標題，整本 85 章只有 2 個 ≥ 4 字。第一卷只剩 1 個錨點
   「主要人物」——卷首的人物介紹頁，必然在檔頭——tail 測試就把完整的 155,614 字判成
   斷檔。1–2 個錨點的位置資訊沒有意義，錨點不足就退回字數判定。

**適用範圍要有自覺：** 錨點法只對「章節標題有描述性文字」的書有效。像 aid=1832 這種
光禿標題的書，10 卷全部 `anchors=0/0`，實際走的是比較弱的字數判定。這是資料端的限制，
不是可以靠調門檻解決的。

判定結果 `complete` / `suspect` / `garbled`，`suspect` 另外帶機器可讀的 `reason`。
**只有 `anchor_ratio` / `anchor_tail`（有章節證據）會自動重抓**；`too_short`（沒有任何
錨點、只靠字數）不自動重抓——插圖卷、後記這種卷本來就可能真的很短。

**manifest 的三個地雷：**

- `size` **一定要取寫檔完成後的 `os.path.getsize()` 實測值**。`downloader` 寫檔是
  `open(..., "w", encoding="utf-8")`，沒指定 `newline=""`，Windows text mode 會把
  `\n` 翻成 `\r\n`，磁碟 bytes ≠ `len(text.encode("utf-8"))`。用記憶體算的值會讓每卷
  快篩都判定「檔案被動過」而全部重抓。
- **`script` 一定要記**（`zh-hant` / `zh-hans` / `unknown`）。不記的話，使用者關著
  簡轉繁抓了 10 卷、之後打開，檔案都在、大小也對 → 判定完整不重抓 → 資料夾永遠簡繁
  混雜，而且從檔名完全看不出來。回推舊檔一律填 `unknown` 且不觸發重抓：用 OpenCC
  反推原文是簡是繁很容易誤判，代價是幾十卷白抓一遍。
- **`manifest.py` 不可 import `downloader`**——`downloader` 會 import 它寫紀錄，
  反過來就是循環。算檔名一律由呼叫端傳 `build_path(vol)` callable 進來。

## 執行流程

```
使用者雙擊 BAT
  → launcher.ps1 檢查 Python / uv / venv
  → venv\Scripts\python.exe -m src.main
  → 終端顯示 CTH banner
  → tkinter 視窗開啟（下載 / 轉換 / 設定 三個常駐分頁）

使用者貼上目錄網址 → 點「載入」
  → parse_aid_from_url 提取 aid；parse_vid_from_url / parse_cid_from_url 判斷是不是單卷網址
  → 背景 thread: fetch_catalog(aid) → parse_book_title / parse_volumes（每卷帶 chapters）
  → queue: ("catalog_done", book_name, volumes)
  → 主執行緒 assign_categories_and_sequence() 分類/編號（**一律整份目錄**）
  → 單卷網址時用 find_volume_by_cid 反查 vid，Preview 只顯示那一卷
  → 使用者確認/調整每卷「正式卷」「外傳」分類 → 「確認」
  → resequence_by_category() 先對**整份目錄**算編號，再篩出要帶進下載清單的卷
    （只拿一卷去 resequence 會把它編成 1，檔名跟其他卷對不上）
  → 帶入下載 tab 卷列表；整份目錄留在 self._catalog_volumes 供「更新」比對
  → _notify_existing_files()：純本地比對 manifest／磁碟，資料夾裡已有檔案就提示
    「已有 1–10 卷」，讓使用者選「只抓缺的與新的」或「全部重抓覆蓋」

使用者勾選卷次 → 點「下載選取」
  → 背景 thread: run_download_all(aid, book_name, volumes, output_dir, queue, retry_count, retry_delay, 命名參數, skip_event)
  → 每卷: download_volume() → 抓 utf-8，若含亂碼再抓 gbk 取較乾淨者 → convert_to_traditional() → 寫檔
         → check_garbled() 驗收 + _record_manifest()（讀回剛寫好的檔跑 verify，寫一筆 .wenku8.json）
         → 判定 reason 是 anchor_ratio / anchor_tail（有章節證據的斷檔）才併進 garbled_volumes 自動重抓；
           too_short（沒有錨點、只靠字數）只記 manifest，插圖卷這類本來就短的卷不該被自動重抓
  → queue: ("progress", ...) / ("log", ...) → 全部跑完 ("done", success, fail_volumes, garbled_volumes)
  → UI 即時更新進度條與記錄區

下載完成若有 fail_volumes/garbled_volumes（"done" handler）：
  → 自動觸發修復鏈（不用手動按「重試/修復」）：
    - 有限重試模式：最多自動跑 3 輪 run_repair_all，清單清空就提早停
    - 無限重試模式：只跑 1 輪，但傳入 max_attempts=50 讓 repair_volume 的迴圈能有界放棄
  → 跑到輪數上限仍有問題的卷留在 self._recovery_volumes，狀態列告知需手動處理的卷數
  → 使用者可隨時手動點「重試/修復」（不受自動流程次數限制、無限重試時完全依照設定跑到底或手動跳過）

使用者點「更新」（會連網，跟純本地的「掃描既有檔案」刻意分成兩顆按鈕）：
  → 背景 thread 重抓目錄 → 沿用使用者在 Preview 調過的分類，只有新卷才跑關鍵字分類
  → queue: ("update_catalog", book_name, volumes)
  → 主執行緒 _make_plan()：manifest 沒紀錄就先 rebuild_from_files 按檔名回推（不重抓）
    → plan_update() 兩層驗證：先 os.stat 比 size 快篩，快篩不過／沒紀錄／狀態不是
      complete 才讀全文重驗
  → 六組（new / incomplete / changed / chapters_changed / script_mismatch / ok）
    分開列在確認視窗，new 與 incomplete 預設勾選，另外三組預設不勾
    （那三組是「使用者可能有意為之」，不該自動覆蓋既有檔案）
  → 勾完按「下載選取」→ 走既有的 _start_download() / run_download_all()

使用者也可隨時點「掃描既有檔案」：
  → 純本地比對：對目前已載入書籍的卷列表逐一算出應有檔名（build_filepath），檔案不存在或 check_garbled 為 True 就列入
  → 結果用 vid 去重後併入 self._recovery_volumes（不覆蓋既有待處理項目），不自動觸發修復

輸出（依「下載至」路徑，不再自動加一層書名子資料夾）:
  <下載至路徑>/
    01 書名 第一卷.txt
    02 書名 第二卷.txt
    外傳01 書名 番外篇.txt   ← 外傳卷檔名固定加「外傳」前綴，跟正式卷各自獨立編號
    ...
```

## 關鍵設定變數（src/config.py，預設值；使用者實際生效值持久化在 `.tool_config.json`）

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `CATALOG_BASE_URL` | `https://www.wenku8.net/modules/article/reader.php` | 書籍目錄頁 URL |
| `DOWNLOAD_BASE_URL` | `http://dl.wenku8.com/packtxt.php` | 下載 URL（`charset` 參數不可信，見 `docs/PITFALLS.md` P5） |
| `OUTPUT_DIR` | `downloads` | 輸出資料夾預設值（相對於專案根目錄，使用者可在 UI 自訂絕對路徑） |
| `RETRY_COUNT` | `3` | 每次 HTTP 請求預設重試次數；`<=0` 代表無限重試（UI「無限重試」勾選項） |
| `RETRY_DELAY` | `2` | 重試間隔秒數 |

## Queue 訊息協定（src/main.py ↔ 背景 thread）

| 類型 | 格式 | 說明 |
|------|------|------|
| `catalog_done` | `("catalog_done", book_name, volumes)` | 目錄載入成功，觸發 Preview 視窗 |
| `catalog_error` | `("catalog_error", err_msg, err_type, status)` | 目錄載入失敗（含例外類型與 HTTP status，403 會額外提示） |
| `progress` | `("progress", current, total, vol_name)` | 下載/修復進度更新 |
| `log` | `("log", status, index_str, vol_name, detail)` | 單卷完成/失敗/跳過（status: ok/warn/skip/fail） |
| `done` | `("done", success_count, fail_volumes, garbled_volumes)` | 一批下載或修復完成（`main.py` 依此決定是否自動接續修復下一輪） |
| `conv_log` | `("conv_log", ok, filename, detail)` | 「轉換」tab 單一檔案轉換結果 |
| `update_catalog` | `("update_catalog", book_name, volumes)` | 「更新」重抓目錄成功（`main.py` 接著跑 `_make_plan()` 與確認視窗；失敗走既有的 `catalog_error`） |
| `conv_done` | `("conv_done", success, fail)` | 「轉換」tab 批次完成 |
| `status` | `("status", (msg, level))` | 狀態列更新（level: info/success/error） |
