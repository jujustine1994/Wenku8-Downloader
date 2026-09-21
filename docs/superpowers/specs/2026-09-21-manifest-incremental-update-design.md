# 設計規格：manifest 與增量更新

日期：2026-09-21
狀態：已實作（2026-09-21）

---

## 需求摘要

目前工具每次下載都是整批重抓，沒有任何「這一卷已經抓過而且抓得完整」的紀錄。
既有的 `scan_existing_volumes()` 只做兩件事：檔案在不在、能不能用 UTF-8 讀且不含 `�`。
這留下三個洞：

1. **斷檔看不出來。** 伺服器回 HTTP 200 但內容不完整時，檔案是合法 UTF-8、沒有 `�`，
   現行驗收一律判定成功。（真正的傳輸中斷 curl 多半直接拋例外，已被現有 retry 接住，
   不是這裡要解的問題。）
2. **簡繁狀態看不出來。** `convert_traditional` 是可關的設定。使用者關著抓了 10 卷、
   之後打開，檔案都在、大小也對，於是判定完整不重抓，資料夾永遠簡繁混雜，
   而且從檔名完全看不出來。
3. **沒有「只抓新卷」的流程。** 追連載中的書，每次都要人工比對哪幾卷是新的。

本規格新增一個持久化的 manifest 檔，記錄每一卷的識別碼、下載時間、檔案指紋、
簡繁狀態與完整性判定結果，並在此之上做「更新」流程：只抓目錄上有而本機沒有的新卷，
以及本機驗不過的卷。

### 不在本規格範圍

- **功能「貼單卷網址直接載入」另案處理**（bounded，無 spec）：`scraper` 加
  `parse_vid_from_url()`，`_on_load` 拿到 vid 後仍整份抓目錄（`seq_index`/`seq_total`
  要靠全部卷才算得出來，省不得），但 Preview 與下載清單只帶那一卷。兩案共用
  `parse_volumes()` 的改動，實作順序上本規格先。
  **放在既有的「下載」分頁，不開新分頁**：整套網址與單卷網址貼的是同一個輸入框，
  貼進來後自動偵測有沒有 `vid` 就好；開新分頁等於要求使用者先自行分類手上的網址，
  還要複製一整套卷列表／下載／修復 UI 與狀態機。「更新」按鈕同理放在下載分頁。
- 跨資料夾、跨書源的書庫管理。
- 自動排程更新。使用者按按鈕才跑。

---

## Spike 實測結論（2026-09-21，aid=1861，第 1／21／57 卷）

完整性判定的依據來自這次實測，門檻不是拍腦袋定的：

| 觀察 | 數據 | 對設計的影響 |
|---|---|---|
| 目錄頁章節標題原樣出現在 txt | 第 1 卷 9/9、第 57 卷 7/7 命中 | 章節標題可以當完整性錨點 |
| 標題行格式固定 | 前面縮排兩個全形空格，行長 > 標題長 | 用 `in` 子字串比對，不做整行全等 |
| 標點會對不上 | 第 21 卷一章目錄與 txt 用了不同的間隔符號，全等比對誤判缺章；該卷實際完整（153,309 字／8,193 行） | 比對前必須正規化標點與空白 |
| 短標題誤命中 | 2 字標題（插圖、後記之類）命中到正文同字，第 21 卷該章命中在第 862 行而非檔尾 | 只有長度 ≥ 4 的標題可當錨點 |
| cid 不出現在 txt 內容 | `any cid literal in txt: False` | cid 只能當 manifest 的穩定識別碼，驗不了內容 |
| 完整檔的最後錨點位置 | 第 1 卷 99.2%、第 57 卷 99.6%、第 21 卷 70.0% | 「最後錨點落在檔案後 50%」對完整檔有充足餘裕 |

---

## 架構設計

### 1. `src/scraper.py`：`parse_volumes()` 補出章節清單

現況兩個限制擋住章節擷取，都要改：

- `row.find("a")` 只取每列第一個連結。但 index.htm 版型是**一個 `<tr>` 裝 4 個 `<td>`、
  每個 td 一章**，這樣會漏掉 3/4 的章節。
- 章節 href 是相對路徑（`65281.htm` 這種），沒有 `?cid=`。現有解析只認 query 裡的 `cid`。

改動：逐 `<td>` 走每一列的所有 `<a>`，cid 取得順序為
`?cid=` query → `(?:^|/)(\d+)\.htm` 相對或絕對路徑。
每卷新增欄位：

```python
"chapters": [{"cid": 65281, "title": "<目錄頁原始標題>"}, ...]
```

**`vid` 的推導維持現狀不動**：index.htm 版型讀卷標題 td 的 `vid` 屬性；
reader.php 版型用 `first_cid - 1`。章節清單是新增的附加資訊，不改既有推導路徑。

**標題保持原始簡體**，照 `src/sitedata.py` 的準則：它是拿去跟下載內容比對的**資料**，
不進 i18n，不做任何轉換後才存。

回傳 dict 多一個 key，既有呼叫端（`classify_volumes` / `resequence_by_category` /
Preview 視窗）都是 `{**v, ...}` 展開複製，不受影響。

### 2. `src/verify.py`（新模組）：完整性判定

獨立成模組而不是塞進 `downloader.py`：判定邏輯是純函式、沒有網路與 UI 依賴，
獨立才測得動，`downloader` 與 `main` 兩邊都要用。

```python
NORMALIZE_MAP: dict[str, str]        # 資料，不翻譯
ANCHOR_MIN_LEN = 4                   # 短於此的章節標題不當錨點
ANCHOR_HIT_RATIO = 0.8               # 錨點命中率門檻
ANCHOR_TAIL_POSITION = 0.5           # 最後錨點必須落在檔案後半
FALLBACK_CHARS_RATIO = 0.2           # 無錨點時：同書卷字數中位數的比例
FALLBACK_CHARS_FLOOR = 3000          # 無錨點時的絕對下限

def normalize(text: str) -> str
def verify_volume(text: str, chapters: list[dict], median_chars: int | None) -> dict
```

`normalize()` 做三件事：去除所有空白（半形空格、全形空格 `　`、tab）、
把常見間隔符號統一成單一字元、把全形括號類統一。
標題與內文都過同一個函式再比對。

`verify_volume()` 回傳：

```python
{"status": "complete" | "suspect" | "garbled",
 "chars": 135579,
 "anchor_total": 7, "anchor_hits": 7,
 "tail_position": 0.992,
 "reason": ""}          # suspect 時填機器可讀代號，不是給人看的句子
```

判定順序：

1. 內文含 `�` → `garbled`（沿用現有語意，優先於其他判定）
2. 取 `len(normalize(title)) >= ANCHOR_MIN_LEN` 的章節當錨點
3. **有錨點**：命中率 ≥ 0.8 且最後一個命中的錨點位置 ≥ 全文長度 0.5 → `complete`，
   否則 `suspect`（`reason` 為 `"anchor_ratio"` 或 `"anchor_tail"`）
4. **無錨點**（單章卷、全短標題卷）：字數 ≥ `max(median_chars * 0.2, 3000)` →
   `complete`，否則 `suspect`（`reason` 為 `"too_short"`）。
   `median_chars` 由呼叫端從 manifest 裡同一本書已完成卷的 `chars` 算中位數；
   一卷都還沒有時 `median_chars=None`，只比 3000 的絕對下限

**位置比例以字元偏移計算**，不是行號 —— 行數受換行風格影響，字元偏移不受。

### 3. `src/manifest.py`（新模組）：讀寫與遷移

檔案位置：輸出資料夾根目錄 `.wenku8.json`，一個資料夾一個檔，內部按 aid 分書。
（輸出不會自動建書名子資料夾，同一個資料夾本來就可能混多本書。）

```json
{
  "version": 1,
  "books": {
    "1861": {
      "book_name": "<書名>",
      "updated_at": "2026-09-21T14:03:22",
      "volumes": {
        "65280": {
          "vid": 65280,
          "name": "第一卷",
          "category": "main",
          "seq_index": 1,
          "cids": [65281, 65282, 65283],
          "chapter_count": 9,
          "filename": "01 書名 第一卷.txt",
          "downloaded_at": "2026-09-21T14:03:22",
          "size": 312456,
          "chars": 135579,
          "script": "zh-hant",
          "status": "complete",
          "anchor_hits": 7,
          "anchor_total": 7
        }
      }
    }
  }
}
```

**欄位語意，三個容易出錯的地方：**

- **`vid` 是 key，`cids` 是內容識別。** vid 不受改名、換編號格式影響，所以拿它當 key；
  `cids` 記下來是為了目錄改版時能判斷「這一卷的章節組成有沒有變」——
  章節數或 cid 集合變了（作者補章、站方重新分卷），即使檔案驗得過也該列入可重抓。
- **`size` 必須是寫檔完成後的 `os.path.getsize()` 實測值。**
  `downloader.py:110` 是 `open(filepath, "w", encoding="utf-8")`，**沒有指定 `newline=""`**，
  Windows text mode 會把 `\n` 翻成 `\r\n`，所以磁碟 bytes ≠ `len(text.encode("utf-8"))`。
  用記憶體算的值會讓每一卷快篩都判定「檔案被動過」而全部重抓。
  本規格**不改**既有的換行行為（改了會讓所有既有檔案的 size 對不上），只要求 size 取實測值。
- **`script`**：`"zh-hant"`（下載時開了簡轉繁）／`"zh-hans"`（關著）／`"unknown"`（回推來的舊檔）。

API：

```python
MANIFEST_FILENAME = ".wenku8.json"

def load(output_dir: str) -> dict                    # 壞檔／不存在回空骨架，不 raise
def save(output_dir: str, data: dict) -> None
def get_book(data: dict, aid: str) -> dict
def record_volume(output_dir, aid, book_name, vol, filepath, verdict, script) -> None
def rebuild_from_files(output_dir, aid, book_name, volumes, naming_opts) -> dict
def plan_update(volumes, book_entry, output_dir, naming_opts, want_script) -> dict
```

**編碼規範（三條都是實際會咬人的）：**

- 寫：`open(path, "w", encoding="utf-8", newline="\n")` + `json.dump(..., ensure_ascii=False, indent=2)`。
  **不加 BOM** —— BOM 是 `launcher.ps1` 那種 PS1 檔的規矩，JSON 加了會讓別的工具解析失敗。
  `ensure_ascii=False` 讓書名卷名維持可讀。
- 讀：`encoding="utf-8-sig"` 容錯，萬一被記事本編輯過塞了 BOM 也吃得下。
- 壞掉時不 raise：`JSONDecodeError` / `OSError` / schema 版本不認得 → 回空骨架，
  讓流程退回 `rebuild_from_files()`。log 記一行 `type(e).__name__`，
  照專案規矩不記檔案內容。

### 4. 舊資料夾遷移：`rebuild_from_files()`

沒有 manifest（或 manifest 壞掉）時，按檔名回推，**不重抓**：

- 對每一卷用現有 `build_filepath()`（帶目前命名設定）算出應有檔名
- 檔案存在 → 寫一筆：`size` 取 `os.path.getsize()`、`downloaded_at` 取檔案 mtime、
  `chars` 讀檔後取長度、跑 `verify_volume()` 填 `status`
- **`script` 一律填 `"unknown"`，不做簡繁偵測。** 用 OpenCC 反推原文是簡是繁很容易誤判
  （本來就是繁體的文字轉完也一樣），誤判代價是幾十卷白抓一遍。`unknown` 不觸發重抓。
- 檔案不存在 → 不寫入 manifest（等同「沒下載過」）

**已知限制（沿用 `scan_existing_volumes` 的同一個限制）：** 檔名比對照**目前**命名設定算。
下載後改過命名設定的話，舊檔對不上會被當成沒下載過。刻意不處理。

### 5. 更新流程：`plan_update()` 與 UI

`plan_update()` 是純函式，回傳分好組的清單，不做任何下載：

```python
{"new":        [vol, ...],   # 目錄有、manifest 沒有
 "incomplete": [vol, ...],   # status != complete，或檔案已不存在
 "changed":    [vol, ...],   # 檔案 size 與 manifest 不符（被外部改過）
 "chapters_changed": [vol, ...],  # cids 集合與 manifest 不同（站方補章/重新分卷）
 "script_mismatch": [vol, ...],   # script 與目前設定不一致（unknown 不列入）
 "ok":         [vol, ...]}
```

兩層驗證，兩層都做 —— spike 顯示重驗成本很低（單卷 300KB 讀+掃約 5–10ms，
100 卷全讀也才 0.5–1 秒），所以快篩是省心不是省時：

1. **快篩**：`os.stat` 比 size。相符且 manifest 記 `complete` → 進 `ok`，不讀內容。
2. **重驗**：快篩不過、manifest 無紀錄、或 status 不是 complete → 讀全文跑
   `verify_volume()` 重新判定。

UI 改動（`src/main.py`）：

- 下載 tab 的 `btn_row` 新增「更新」按鈕，放在「下載選取」左邊。啟用條件同 `btn_scan`
  （已載入書籍）。**不併進「掃描既有檔案」** —— 掃描是純本地、不碰網路的既有行為，
  更新要重抓目錄，兩者成本與語意不同，併在一起會讓使用者不知道按下去會不會連網。
- 按下後背景 thread 重抓目錄 → `plan_update()` → queue 回 `("update_plan", plan)`
- **載入書籍時就先提醒一次。** Preview 確認後（卷列表帶進下載分頁那一刻），
  用剛抓回來的目錄就地跑一次 `plan_update()`（純本地，不重抓目錄），
  資料夾裡已經有檔案時在狀態列直接講清楚：
  「這本書共 57 卷，資料夾裡已有 1–10 卷（完整）。」並跳一個兩選一的提示：
  **只抓缺的與新的**（勾選 `new` + `incomplete`）／**全部重抓覆蓋**（全選）。
  已有檔案的連續卷序用區間表示（`1–10`），不連續時列出前幾個加「等 N 卷」，
  避免 50 卷時狀態列爆掉。資料夾裡一卷都沒有時不跳提示，維持現行行為。
- 主執行緒跳確認視窗，**按上述六組分開列出**，每組一個「全選/全不選」，
  `new` 與 `incomplete` 預設勾選，`changed`／`chapters_changed`／`script_mismatch`
  **預設不勾**（這三組是「你可能有意為之」的情況，不該自動覆蓋使用者的檔案）
- 確認 → 走既有 `run_download_all()`，不另寫下載邏輯

新增 queue 訊息類型一種：`("update_plan", plan_dict)`。其餘沿用。

### 6. 寫入時機

`run_download_all()` 與 `run_repair_all()` 每卷寫完檔後，就地跑
`verify_volume()` 並呼叫 `manifest.record_volume()`。

- **驗證用轉換前的原文**（`_fetch_best_text` 的回傳值），章節標題是簡體，直接對得上，
  不用轉換，最準。
- 更新流程重驗磁碟上的檔案時，檔案可能已是繁體：依 manifest 的 `script` 決定要不要先
  把**章節標題**跑一次 `convert_to_traditional()` 再比對（轉標題比轉全文便宜得多）。
  `script` 為 `unknown` 時兩種都試，任一過就算過。
- 每卷寫一次 manifest（開檔→寫→關檔，不持有 handle），跟 log 同一條規矩。
  一卷幾十 KB 的 JSON 寫入相對於一次 HTTP 下載可以忽略；累積到最後才寫的話，
  中途關視窗就整批丟失，而那正是最需要紀錄的時候。
- 寫入失敗包 `except OSError: pass` —— manifest 掛掉不能拖垮下載。

### 7. i18n

新增介面字串的 key 進母表 `src/locales/zh_tw.py`：更新按鈕、確認視窗六組標題與說明、
載入後提醒、狀態列訊息。`en`／`ja`／`zh_cn` 目前整份是空的 `STRINGS = {}`，本規格不補。

**`src/main.py` 的字面維持現況。** 照 `I18N_RESUME.md`，i18n 遷移停在批次 3，
`main.py` 的 142 條中文字面還沒搬成 `t()`。新增的 UI 字串在 `main.py` 裡**跟周圍一樣寫字面**，
key 同步補進母表，等批次 3 一次搬完 —— 現在單獨只讓新程式碼走 `t()`，會讓同一個
按鈕列一半 `t()` 一半字面，遷移時更難盤點。

新增落檔字串進 `src/logtext.py`（照專案 log 規矩）。

**不進 i18n 的**：manifest 的所有 key 與 `status`／`script`／`reason` 的值、
`NORMALIZE_MAP` 的內容、`MANIFEST_FILENAME`。全部是會落檔或拿去比對的資料。
`NORMALIZE_MAP` 含簡體標點，性質同 `src/sitedata.py`，模組 docstring 要寫明不可翻譯。
（`I18N_RESUME.md` 批次 6 規劃的防退化測試 `tests/test_i18n.py` 目前還不存在，
本規格不建立；該測試建立時需把 `src/verify.py` 一併放進 ALLOWLIST。）

---

## 錯誤處理

| 情況 | 處理 |
|---|---|
| manifest 不存在 | `rebuild_from_files()` 建一份 |
| manifest JSON 壞掉／版本不認得 | 視同不存在，重建；log 一行 `type(e).__name__` |
| manifest 寫入失敗（唯讀、磁碟滿） | `except OSError: pass`，下載照跑，狀態列提示一次 |
| 更新時重抓目錄失敗 | 沿用 `catalog_error` 既有處理（含 403 提示），不進更新流程 |
| 單卷重驗時讀檔失敗 | 該卷列入 `incomplete`，不中斷整批 |
| 輸出資料夾在更新中途被移除 | 沿用 `run_download_all` 既有的單卷 `except Exception` 保護 |

---

## 測試計畫

全部是純函式，不需要 HTTP。沿用既有 `unittest.mock` 風格。

**`tests/test_verify.py`（新）**
- `normalize()`：空白三種、間隔符號、全形括號
- 錨點過濾：長度 3 的標題不當錨點
- `complete`：命中率 1.0、tail 0.99（比照 spike 第 1 卷實測）
- `complete`：命中率 8/9、tail 0.70（比照 spike 第 21 卷，標點誤判仍須通過）
- `suspect/anchor_tail`：只有前半段錨點命中（模擬斷檔）
- `suspect/anchor_ratio`：多數錨點找不到
- `garbled`：含 `�` 優先於錨點判定
- 無錨點卷：走字數 fallback，`median_chars=None` 時只比 3000 下限

**`tests/test_manifest.py`（新）**
- 讀寫往返，中文不被 escape（`ensure_ascii=False` 生效）
- 讀帶 BOM 的檔不炸（`utf-8-sig`）
- 壞 JSON → 回空骨架不 raise
- 同一資料夾兩本書互不干擾
- `rebuild_from_files()`：檔案存在寫入且 `script="unknown"`、不存在不寫入
- `plan_update()` 六組分類各一個案例，含 size 不符、cids 變動、script 不一致

**`tests/test_scraper.py`（擴充）**
- index.htm 版型：一個 `<tr>` 四個 `<td>` 四章，四章全抓到
- 相對路徑 href 解析出 cid
- reader.php 版型 `?cid=` 仍正常
- `vid` 推導行為與改動前一致（回歸）

**UI 部分**：更新按鈕、確認視窗六組顯示、狀態機，改完請使用者雙擊 BAT 實測，
不以程式碼審視代替驗收（照 `windows-tool.md` 驗收規定）。

---

## 已知限制

1. **檔名比對照目前命名設定算**。下載後改過命名設定，舊檔會被當成沒下載過。
   與 `scan_existing_volumes` 同一個限制，一併不處理。
2. **`script="unknown"` 的舊檔不會被自動重抓**。想統一簡繁要手動勾選重抓。
3. **錨點判定對「全短標題」的卷退化成字數判定**，精度較低。實測資料顯示這類卷很少
   （57 卷裡沒有一卷完全沒有長標題）。
4. **manifest 不跟檔案一起搬**。使用者手動搬 txt 到別的資料夾，manifest 留在原地，
   新資料夾會走回推重建。可接受。
5. **`too_short` 不自動重抓，但仍會每次出現在「不完整」那組。**
   實作時發現的問題：沒有章節錨點的卷（插圖卷、後記）本來就可能真的短於 3000 字，
   自動修復鏈會把它抓一遍又判一次可疑，變成永遠清不掉的待處理項目。
   所以判定拆成兩級——`anchor_ratio` / `anchor_tail`（**有章節證據**的斷檔）才併進
   `garbled_volumes` 自動重抓，`too_short`（只有字數）僅記進 manifest。
   代價是這類卷每次按「更新」都會落在「不完整」那組且預設勾選，使用者要自己取消勾選。
   真正的解法是站方目錄補上這類卷的章節，不在本工具能處理的範圍。
6. **站方大幅改版目錄結構**（章節不再用相對路徑 `.htm`）時章節清單會抓不到，
   此時所有卷退化成字數判定。`parse_volumes` 的 vid 推導不受影響，不會整個壞掉。
