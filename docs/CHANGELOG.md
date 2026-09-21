# CHANGELOG

## feat/i18n（進行中，未合併）

多語言（繁中／简中／English／日本語）遷移，做到批次 3 的一半因故中斷。
接手說明見專案根目錄 `I18N_RESUME.md`。

**新增檔案**
- `src/i18n.py` — `t()` 查表核心（目標語言→母語言→key 本身，永不 raise／回空字串）
- `src/locales/{zh_tw,zh_cn,en,ja}.py` — 語言檔；`zh_tw` 母表已完整（約 130 條 key），其餘三個仍為空
- `src/logtext.py` — 落檔字串，**固定繁中**，不跟使用者語言走
- `src/sitedata.py` — 永遠不翻的資料字串（檔名前綴、爬蟲比對關鍵字、HTML 解析樣式）

**變更**
- 區域變數 `t = THEMES.get(...)` 改名為 `theme`（2 處），讓出 `t` 給 i18n
- `.tool_config.json` 新增 `language` 欄位（預設空字串，才分得出「沒選過」）
- 首次啟動跳語言選擇視窗（刻意不翻譯）；「設定」分頁最上方加 Language 下拉，
  套用後提示重啟（重開生效，不做即時切換）
- `downloader.py` / `converter.py` 推到畫面的訊息改走 `t()`（約 11 條）
- `scraper.py` 的 HTML 解析樣式與書名 fallback 移入 `sitedata.py`；
  `parse_aid_from_url` 的 `ValueError` 訊息改英文（開發者導向，永不顯示）

**驗收**
- 測試 89 → 89（**既有測試一條都沒改，全綠**）
- 檔名／目錄／檔案內容與改前**逐字相同**（12 條路徑 + 12 個檔案，4 種命名組合，
  走真正的組裝與寫檔函式，網路以 mock 取代）
- 9 條 log 行與改前 f-string 逐字相同
- 繁中 GUI 建置 248 條 widget 文字、殘留 key 0
- ⚠ 四語驗收、防退化測試、負向驗證**尚未執行**


## 現狀

**已完成功能：**
- URL 解析（aid 提取，支援 reader.php?aid=、/book/XXXX.htm、純數字書號）
- 目錄頁爬取與卷列表解析（curl_cffi 模擬 Chrome TLS 繞過 Cloudflare；
  reader.php 被 challenge 擋下時 fallback 到 /novel/.../index.htm）
- 逐卷下載（retry 3x）
- tkinter UI（進度條、記錄區、主題切換）
- 卷選單（可勾選指定卷下載，全選/全不選）
- 啟動器（BAT + PS1）
- 輸出資料夾選擇（主 UI 直接顯示 + 可編輯 + 瀏覽按鈕）
- 「設定」tab 內的下載區塊：retry 次數與間隔可調整（持久化至 config.json）
- 下載自動轉繁體（s2twp，opencc-python-reimplemented）
- 「轉換」tab：多選 TXT 批次轉繁體，支援覆蓋原檔或另存 _TC 新檔
- 「設定」tab 內的命名區塊：序號格式（零補位/純數字/不顯示）、書名開關、分隔符號客製化，含即時預覽
- 亂碼檢查：下載/修復時一律先偵測 BOM 判斷實際編碼（wenku8 的 charset 參數名稱不可信），大幅減少誤判亂碼；仍有亂碼才需手動按「修復亂碼 N 卷」，修復會持續重試直到修好或連續數輪無改善才放棄
- 跳過與管理：下載或修復中都可點「跳過目前卷」；待處理卷可透過「管理」對話框選擇性移出清單
- 「重試失敗」「修復亂碼」合併成單一「重試/修復」按鈕與待處理清單，一律用既有的 repair 邏輯（網路重試+編碼修復）處理，使用者不用分辨失敗類型
- 「設定」tab 內的識別區塊：外傳關鍵字管理（新增/刪除），持久化至 config；`classify_volume` 以正式卷 pattern 白名單優先，再比對關鍵字
- 「下載至」路徑即為該書存放位置，不再自動多加一層書名資料夾
- 「設定」tab 內的下載區塊 可勾選「無限重試」，網路重試與修復迴圈會持續到成功或手動跳過為止
- 下載/修復路徑不可用時會先擋下並顯示錯誤，單一卷寫檔失敗也不會讓整批背景執行緒卡死
- 設定改為主視窗第三個常駐 tab（外觀/下載/命名/識別打平成單一可捲動頁面），取消原本的彈出視窗；⚙ 按鈕保留作為捷徑，點擊直接切到「設定」tab；沿用「套用/取消」機制，取消會還原成目前生效值
- 主視窗分頁（下載/轉換/設定）文字放大加粗、加大點擊區域；「轉換」tab 加上一行功能說明
- 載入目錄後跳出 Preview 視窗，確認/調整每卷「正式卷」「外傳」分類（含批次選取多列一次改），確認後才帶入下載 tab；正式卷與外傳卷各自獨立編號，外傳卷檔名加「外傳」前綴
- 「掃描既有檔案」按鈕：比對目前已載入書籍的卷列表跟輸出資料夾實際檔案，把缺檔或含亂碼的卷補進「重試/修復」待處理清單（不含網路請求，純本地檔案比對；檔名比對依照目前的命名設定計算，命名設定變更後的舊檔案可能被誤判為缺檔）
- 下載完成若有失敗/亂碼卷，自動接續觸發修復（不用手動按「重試/修復」）；有限重試模式最多自動跑 3 輪，無限重試模式單一編碼嘗試上限 50 次後自動視同跳過；跑到上限後仍有問題的卷會清楚留在待處理清單，狀態列會告知需要手動處理的卷數，使用者隨時可再手動點「重試/修復」
- **貼單卷網址只載入那一卷**：`?vid=` 或章節頁 `/novel/{分類}/{aid}/{cid}.htm` 都認得（後者靠章節清單反查屬於哪一卷）。編號仍照整份目錄算，檔名跟其他卷對得上。跟整套網址共用同一個輸入框與同一個「下載」分頁，不另開分頁
- **manifest（`.wenku8.json`）與「更新」按鈕**：輸出資料夾記錄每卷的 vid／cid 清單／下載時間／檔案大小／字數／簡繁／完整性判定；「更新」重抓目錄後比對，把每一卷分成新卷／不完整／被改過／章節有變動／簡繁不符／已完整六組讓使用者勾選，只抓要抓的。舊資料夾按檔名回推建 manifest，不重抓
- **完整性判定改用章節標題當錨點**（`src/verify.py`）：斷檔（HTTP 200 但內容不完整）過去驗不出來，現在靠「目錄說有的章節標題在不在檔案裡、最後一個錨點離檔尾多遠」判斷。比對前正規化標點與空白（實測有章節目錄與 txt 用不同間隔號），只取長度 ≥ 4 的標題當錨點（短標題會誤命中正文），且**錨點少於 3 個就整個不採信**（實測 aid=1832 只剩卷首「主要人物」一個錨點，位置在檔頭，會把完整檔誤判成斷檔）。章節標題光禿的書因此會退回字數判定，精度較低
- 載入書籍後若資料夾裡已有檔案，直接提示「已有 1–10 卷」並讓使用者選「只抓缺的與新的」或「全部重抓覆蓋」
- **檔名跟著簡轉繁開關一起轉**：勾了簡轉繁，書名與卷名（都是簡體站抓回來的原文）也會轉繁再組檔名。下載／修復／掃描／manifest 比對四條路徑共用同一個 `build_filepath()`，不會出現「寫檔用繁體、找檔用簡體」。預設關閉，漏傳參數時維持既有行為
- 完整性判定改用**兩組並列錨點**（純標題／卷名＋標題），取命中高的那組。複合錨點把
  「序章」這種 2 字標題救回來（aid=1832 從每卷 0 個錨點變成 6–11 個），但刻意不寫死
  哪種命名格式，格式對不上會自動落到另一組或字數判定，不會把完好的檔案判成斷檔
- `launcher.ps1`：`uv pip install` 失敗時自動清除 site-packages 的唯讀屬性與
  `xxx (1).*` 同步殘留檔再重試一次（檔案同步工具會造成 uv 的 `os error 5`）
- 修正對話框滾輪 handler 洩漏：`_open_identify_dialog()` 每開一次就在 `root.bind_all`
  多留一個永不解綁的 handler。三個對話框統一改走新的 `_bind_wheel_to_dialog()`

**尚未完成：**
- 見 docs/TODO.md

---

## 更新記錄

### 2026-09-21 — 這一天的來龍去脈（本專案當天的異動一次看完）

CTH 抽查 2026-09-14 那輪「10 個 Windows 工具專案 venv 改用 uv」有沒有做確實，
一路查下去翻出三層問題，本專案當天的異動都是這條線上的：

- **第一層**：9/14 的遷移有些沒做確實。urusai upload 重建後根本沒裝到 pytest
  （`requirements.txt` 只列執行期依賴），測試直接跑不動，而它的 CHANGELOG 還寫著
  「測試 90 條全過」——那是舊 venv 的結果。另外查出 3 個專案（AV Code Rename、
  Excel repair、FanCheck）當初根本沒被納入那輪遷移，還掛在 python.org 版系統 Python 上。
- **第二層**：9/14 有 3 個專案不是乾淨重建，是在舊 `site-packages` 上直接疊裝，
  留下一堆孤兒 `dist-info`（同一套件掛新舊兩份 metadata，`uv pip list` 會列兩次）。
  同時發現 4 個專案有測試卻沒把 pytest 寫進 requirements，只是 venv 還沒重建過所以沒爆。
- **第三層（真正的病根）**：清乾淨重建後幾小時內又被污染。查出 `Documents\Code`
  整個被 Google Drive 桌面版備份（從 `root_preference_sqlite.db` 的 `roots` 表確認，
  `root_id=4`、`state=2`），venv 放專案裡就會被同步，`site-packages` 目錄被設成唯讀、
  產生 `xxx (1).py` 影子檔、套件被切成兩半。清查當下 **13 個專案的 venv 全部**中招。
  所以最後把 venv 全部搬到 `%USERPROFILE%\venvs\` 並改了規則檔 `windows-tool.md`，
  以後新專案一律建在專案外。

**本專案當天的異動**：

1. venv 搬到專案外（commit `447e705`）

同一輪處理的還有其他 12 個專案，以及全域規則檔 `windows-tool.md`
（新增「venv 位置」章節）、`windows-tool-templates.md`、`windows-tool-pitfalls.md`。

**本專案當時的污染程度**：`site-packages` 底下 309 個目錄**全部**被設成唯讀，
另外還有 5 個影子檔（`venv/pyvenv (1).cfg`、`venv/Scripts/python (1).exe`、
`pythonw (1).exe`、`pytest (1).exe`、`py (1).test.exe`）。這裡要特別記一筆：
2026-09-21 稍早曾經手動清過一次並重裝，當時的結論是「venv 目前是好的」，
但實際抽查時影子檔還在——**手動清乾淨這件事本身沒有成功，而且就算成功也擋不住
下一次同步**，這正是最後決定把 venv 整個搬出去的原因。

**commit 歸屬要注意**：本專案的 `launcher.ps1` 改動被拆在兩筆 commit 裡。
改動做到一半時，另一個 session 的 `fd19961`（訊息寫的是
「docs: 記錄偶發下載失敗的真因是 HTTP 429 限流」）把當時還在工作目錄的
`launcher.ps1` 一起掃進去了，剩下的兩行才在 `447e705`。所以**光看 commit 訊息
會找不到 launcher 的 venv 路徑改動**，要往 `fd19961` 裡找。檔案本身已確認完整
正確（`$VenvPath` / `$VenvPython` 定義、9 處引用、BOM、PowerShell 語法都驗過），
沒有被覆蓋或漏改。


### 2026-09-21 — 維護：venv 搬到專案資料夾外（`%USERPROFILE%\venvs\Wenku8 Downloader\`）

`Documents\Code` 整個被 Google Drive 桌面版備份（從
`%LOCALAPPDATA%\Google\DriveFS\root_preference_sqlite.db` 的 `roots` 表確認，
`root_id=4`、`state=2`）。venv 放在專案裡就會跟著被同步，實測災情：

- `site-packages` 底下的目錄被設成唯讀 → uv 換套件版本時 `RemoveDirectory`
  一律回 `ERROR_ACCESS_DENIED`，uv 報 `os error 5 存取被拒`，套件更新整個失敗
- 產生大量 `xxx (1).py` 影子檔（同步工具的衝突命名）
- 套件被切成兩半（實測 `idna` 被刪到只剩影子檔，變成 namespace package）

清查當下 13 個專案的 venv **全部**有唯讀目錄，其中 10 個是 100%；本專案是
309/309 全數唯讀，另有 5 個影子檔。當天稍早才乾淨重建過的 3 個也已經在被感染中，**幾小時就中**，
所以「清乾淨再重建」這種治標做法沒有用。

Drive 桌面版不支援排除子資料夾，只能整個資料夾勾或不勾；而 `Documents\Code`
底下有一半專案沒有 git remote、Drive 是它們唯一的備份，不能關掉備份。
結論是把 venv 搬到同步範圍外。

改動：

- `launcher.ps1`：新增 `$VenvPath` / `$VenvPython` 兩個變數，venv 存在性檢查、
  `uv venv`、`uv pip install --python`、site-packages 路徑、`Activate.ps1`
  全部改用新路徑；建立前會先 `New-Item` 補出 `%USERPROFILE%\venvs\` 父目錄
- `ARCHITECTURE.md`：新增「venv 位置」章節（為什麼搬、手動重建指令）
- 專案內舊 venv 已刪除（先清唯讀屬性才刪得掉）

`venv` **不能用 `mv` 搬**，`Scripts\*.exe` 內嵌絕對路徑，一定要重建。

規則檔 `windows-tool.md` 同步新增「venv 位置」章節，以後新專案一律建在外面。

驗證：測試 166 條全過，與搬移前一致


### 2026-09-14 — 維護：venv 改用 uv 管理的獨立 Python（不依賴系統 Python）

原本 `venv` 是用 Microsoft Store 版 Python 3.13 建的（沙盒安裝，容易有套件裝了
但其他環境讀不到、資料夾存取受限等問題）。照 `windows-tool.md` 既定規範改用
`uv venv venv --python 3.13`：uv 會自己管理一份獨立的 Python 3.13.12，所有專案
共用同一份，不依賴系統上裝的任何 Python。套件安裝改用
`uv pip install -r requirements.txt --python venv\Scripts\python.exe`。舊 venv
備份搬到專案外 `Documents/Code/_venv_backups/Wenku8 Downloader/venv_old_store_20260914/`。
驗證：測試套件 89 條全過，跟改之前一致。

### 2026-09-11 — 簡轉繁修正常見誤轉字（隻/臺/檯/範）
`opencc` `s2twp` 詞庫的幾類已知誤轉會影響小說閱讀體驗，`converter.py`
的 `_OVERRIDES` 由原本僅有的「賓士→奔馳」擴充為 5 條：
- 「只」轉換後常被誤判成量詞「隻」（一隻、兩隻），小說裡「只是/只有」用法
  遠多於量詞用法，全部改回「只」
- 「台」被轉成公文正式異體字「臺／檯」（舞台→舞臺、櫃台→櫃檯），小說慣用
  「台」，全部改回來
- 姓氏「范」常被誤轉成「範」（范先生→範先生），不在詞庫特例名單內的自創
  角色姓名都會中招，全部改回「范」
- 取捨：以上皆為全域字串替換，非上下文判斷，會連帶把真正該用「隻」
  （一隻貓）、「臺」、「範」（範圍、模範）的地方也改掉；已與使用者確認
  接受此取捨（寧可不翻，不要錯翻）

### 2026-09-07 — 新增「下載後自動簡轉繁」開關
「設定」分頁「下載」區塊新增勾選項，關閉後下載/修復都保留原始簡體，不經過
`converter.convert_to_traditional()`。預設維持開啟（跟改之前行為一致）。
- `downloader.download_volume()`／`repair_volume()`／`run_download_all()`／
  `run_repair_all()` 新增 `convert_traditional` 參數（預設 `True`），一路傳到
  寫檔前那行轉換
- `main.py` 存到 `.tool_config.json` 的 `convert_traditional` 欄位
- 既有測試同步調整一條呼叫參數位置斷言（`repair_volume` 多了一個參數，
  `max_attempts` 不再是最後一個位置參數），89 測試全綠

### 2026-09-07 — reader.php 遭 Cloudflare 升級為 JS challenge，目錄抓取改走 fallback
`reader.php`（目錄 API）被 Cloudflare 升級成 Managed Challenge（回應帶
`cf-mitigated: challenge`），`curl_cffi` 的 TLS 指紋模擬對這種互動式挑戰無效，
一律 403。一般網頁 `/novel/{分類}/{aid}/index.htm` 目前未受同等防護，且卷/
章節表格結構與 reader.php 相容（卷標題 `<td>` 直接帶 `vid` 屬性）。
- `scraper.fetch_catalog()`：reader.php 失敗時才觸發 `_fetch_catalog_fallback()`
  —— 先抓 `/book/{aid}.htm` 找出分類代碼，再組 `/novel/{分類}/{aid}/index.htm`；
  reader.php 正常時完全不受影響，走原本路徑
- `scraper.parse_volumes()`：新增讀取卷標題 `vid` 屬性的分支（index.htm 版型），
  讀不到才照舊邏輯從第一章連結的 `cid` 反推，兩種頁面格式都能解析
- `config.py` 新增 `BOOK_BASE_URL`／`NOVEL_BASE_URL`
- 已用實際書號（1832）驗證 fallback 全流程：書名、卷數、vid 皆正確

### 2026-08-23 — 設定分頁新增「版本更新」按鈕
「設定」分頁識別區塊下方新增「檢查更新」／「一鍵安裝」，比對本機與 GitHub
上游程式碼差異，供手動確認並一鍵套用。全程沒有任何一步自動觸發：檢查只讀
不寫，有新版本才出現「一鍵安裝」，按下去先跳確認框列出實際變更摘要，使用
者按確定才動檔案；更新完不自動重啟，跳訊息框請使用者自行關閉重開。
- 新增：`scripts/check_update.ps1`（純資料層，git fetch/diff/checkout，只印一行 JSON）
- 新增：`src/update_checker.py`（呼叫子行程、解析 JSON，不碰 tkinter）
- 技術：`main.py` 新增 `_build_update_section()` 及對應事件處理，網路呼叫走背景執行緒 + `after(0, ...)` 送回主執行緒
- i18n：`src/locales/zh_tw.py` 新增 `gui.settings.update`／`gui.btn.check_update`／`gui.btn.install_update`／`gui.update.*` 共 19 個 key（僅補在母表，其餘三語言檔沿用既有「先留空、之後再統一翻」慣例，未動）

### 2026-08-17 — launcher.ps1 拿掉失效的 winget Python 安裝步驟
`winget install --id Python.Python.3`（不帶次版號）已被上游下架，靜默失效。改成
只檢查 uv，`uv venv venv --python 3.13` 讓 uv 自己下載 Python。步驟從 [1/3]~[3/3]
改成 [1/2]~[2/2]。

### 2026-07-23（v18）
- 新增：下載完成後若有失敗/亂碼卷，自動接續觸發修復流程，不用手動按「重試/修復」
- 新增：自動修復停損機制——有限重試模式最多自動跑 3 輪；無限重試模式因單卷請求設計上不會自然結束，改為單一編碼嘗試次數上限 50 次後視同放棄，只跑 1 輪；跑到上限仍有問題的卷保留在待處理清單，可隨時手動再處理
- 技術：`downloader.py` 的 `_fetch_bytes`/`_fetch_best_text`/`repair_volume`/`run_repair_all` 新增 `max_attempts` 參數（僅自動流程使用，手動操作不受影響）；`main.py` 新增 `_dispatch_repair()`/`_start_auto_repair()`
- 文件：`docs/PITFALLS.md` 新增 P5，記錄 wenku8 下載 API 的 `charset` 參數不可信，Big5 候選已驗證無效因此不採用

### 2026-07-23（v17）
- 新增：「掃描既有檔案」按鈕，比對目前已載入書籍的卷列表跟輸出資料夾實際檔案狀態（缺檔或含亂碼），結果併入既有「重試/修復」待處理清單，沿用現有修復流程，不新增下載邏輯
- 技術：`downloader.py` 新增 `scan_existing_volumes()`；`check_garbled()` 改為對非 UTF-8 檔案回傳 `True` 而非拋例外（掃描既有檔案時可能遇到舊格式殘留檔）

### 2026-07-17 — 文件修正
- `docs/ARCHITECTURE.md`：目錄結構與檔案職責表補上 `src/logutil.py`（執行紀錄共用模組）與 `src/converter.py`（簡轉繁核心，`downloader.py` 的 `download_volume`/`repair_volume` 皆呼叫 `convert_to_traditional`）
- `docs/ARCHITECTURE.md`：修正 queue `done` 訊息格式，從 3 元素 `("done", success_count, fail_list)` 更正為實際的 4 元素 `("done", success, fail_volumes, garbled_volumes)`
- `.gitignore` 加入 `src/.tool_config.json`（存使用者本機輸出路徑，先前未被涵蓋，僥倖未進版控）

### 2026-07-09（v16）
- 改版：「重試失敗」「修復亂碼」合併成單一「重試/修復」按鈕與 `_recovery_volumes` 待處理清單。`repair_volume`/`run_repair_all` 本來就是完整超集（網路重試+編碼修復都有），直接重用，`downloader.py`/`scraper.py` 不用改
- 改善：移除「修復亂碼」原本的二次確認對話框，點「重試/修復」直接處理，不用先判斷是網路失敗還是編碼問題

### 2026-07-08（v15）
- 修正：連續載入兩本書時，第一本書的失敗/亂碼清單與「重試失敗」「管理」「修復亂碼」按鈕沒有跟著重置，殘留舊書的卷資料；若在載入第二本書後誤按重試，會用新書的 aid 去抓舊書卷的 vid，抓到錯誤內容
- 修正：Preview 視窗按「取消」時，畫面上的卷列表與下載相關按鈕沒有跟著清空/停用，會殘留上一本書的勾選清單
- 兩者統一改用新增的 `_reset_book_state()` 共用重置邏輯

### 2026-07-08（v14）
- 新增：載入目錄後跳出 Preview 視窗，使用者可確認/調整每卷「正式卷」「外傳」分類，支援批次選取多列一次改分類；確認後才帶入下載 tab 卷列表
- 新增：正式卷與外傳卷各自獨立編號（外傳卷檔名加「外傳」前綴），穿插存在同一資料夾；下載 tab 卷列表顯示的編號與實際檔名一致
- 技術：`build_filepath()` 新增 `index_prefix` 參數（向下相容）；`scraper.py` 新增 `classify_volumes`/`resequence_by_category`/`assign_categories_and_sequence`/`format_index_token` 四個可獨立測試的純函式

### 2026-07-08（v13）
- 效能：停用 sv-ttk（`App.USE_SV_TTK = False`）。sv-ttk 用 sprite-sheet 圖片裁切繪製元件而非原生繪製，本專案卷列表/轉換檔案清單/識別關鍵字清單都會動態大量建立、銷毀 widget，符合已知會觸發明顯 Tcl 端卡頓的情境（詳見 `windows-tool/tkinter-ui/INDEX.md`）。停用後改用系統原生 ttk 主題，配色仍照 `THEMES` dict 套用

### 2026-07-08（v12）
- 改版：設定 tab 內「外觀」「識別（外傳關鍵字）」改為正常區塊（顯示目前主題／關鍵字數量摘要），往下捲動就看得到；點擊各自的按鈕才彈出獨立視窗編輯、即時套用。「下載」「命名」維持打平顯示，套用/取消按鈕固定在底部
- 改善：外觀設定、識別設定彈出視窗改為可自由拖拉調整大小（不再鎖死），預設也放大；外觀預覽圖從 210×168 固定比例放大到 336×269（1.6 倍），座標與字體統一等比縮放，避免文字跟版面比例跑掉
- 改善：主視窗分頁標籤字體放大加粗、增加內距，明顯好點擊好辨識
- 新增：「轉換」tab 加上一行說明文字，簡述功能用途
- 新增：「轉換」功能現在會先智慧偵測檔案實際編碼（BOM 偵測 + UTF-8/GBK/Big5 比對），修正非 UTF-8 或編碼跑掉的舊檔案，記錄區會標註「偵測為 XX 編碼，已修正」
- 修正（真正修好）：可捲動區域的滾輪事件原本綁在 canvas 本身，滑鼠移到 canvas 內的子元件（Label、Checkbutton...）上方就收不到滾輪事件；改用 `bind_all` 綁在整個視窗層級 + `winfo_ismapped()` 判斷目前可見分頁，滑鼠停在任何子元件上都能正確捲動，且不同分頁的可捲動區域不會互相干擾
- **修正（重大，影響先前已下載/修復的檔案）**：BOM 偵測邏輯把 BOM bytes 一起丟給對應編碼解碼，UTF-16 的 BOM（`\xff\xfe`／`\xfe\xff`）沒有像 UTF-8 的 `utf-8-sig` 一樣自動被去除，導致解碼後文字開頭多一個看不見的 U+FEFF 字元。已修正為解碼前先跳過 2 個 BOM bytes。**v11 之後下載或修復過的檔案，內容開頭可能都藏了這個看不見的字元**，建議重新用「轉換」功能跑一次（本次順便加的智慧編碼偵測會一併清掉開頭的 BOM 殘留）

### 2026-07-08（v11）
- **根因修正（重大）**：wenku8 下載 API 的 `charset` 參數名稱不可信——`charset=utf-8` 實際回傳 UTF-16 LE bytes、`charset=big5` 實際回傳 UTF-8 bytes。改為一律偵測 BOM 決定實際解碼方式，而非相信參數名稱；修好後絕大多數卷一次下載就無亂碼，不再需要多輪重試硬湊
- 新增：「設定」tab 內的下載區塊 可勾選「無限重試（直到成功或手動跳過）」，取代固定 1–10 次的重試上限
- 改善：「修復亂碼」不再只試一次，會持續重新下載並比對 UTF-8/GBK 何者亂碼較少，直到完全無亂碼、連續 5 輪無改善、或使用者按「跳過目前卷」才停止；勾選無限重試時，不套用 5 輪停滯上限，只靠手動跳過結束
- 修正：下載/修復路徑為空或無法建立時，原本會讓背景執行緒直接卡死、UI 永遠停在「下載中」；現在會先驗證路徑，不可用就擋下並顯示錯誤
- 修正：`run_download_all`／`run_repair_all` 迴圈中若單一卷發生非預期例外（如寫檔失敗），原本會讓整批背景執行緒中斷、UI 卡死；現在會將該卷記為失敗並繼續處理下一卷

### 2026-07-08（v10）
- 修正：`parse_aid_from_url` 無法正確解析 `novel/{分類}/{書號}/index.htm` 格式，誤把分類碼當書號導致抓不到目錄
- 改善：下載時偵測到亂碼會自動改用 GBK 編碼重下一次，不必等下載完才手動點「修復亂碼」
- 修正：分批下載（例如先下載 1~5 卷、再下載 6~9 卷）時，「重試失敗」「修復亂碼」清單會互相覆蓋，導致前一批未解決的卷從清單消失；改為合併，只更新本批次涵蓋到的卷
- 修正：`build_filepath` 不再自動加一層書名子資料夾，「下載至」路徑即為該書最終存放位置

### 2026-06-12（v9）
- 新增：「設定」tab 內的識別區塊，管理外傳關鍵字（新增/刪除），套用後持久化至 config
- 新增：`classify_volume(name, side_keywords)` — 正式卷 pattern 白名單優先，再比對關鍵字，fallback 為正式卷
- 更新：TODO 合併「正式卷 vs 外傳自動識別」與「下載前 Preview」為單一功能條目

### 2026-06-11（v8）
- 新增：下載中「跳過目前卷」按鈕，跳過的卷歸入失敗列表（可重試或管理移除）
- 新增：「管理」按鈕開啟對話框，可選擇性將失敗卷移出重試列表

### 2026-06-11（v7）
- 新增：下載後亂碼偵測（?），記錄區顯示 ⚠️
- 新增：「修復亂碼 N 卷」按鈕，自動嘗試 GBK 編碼重下修復，可重複點擊

### 2026-06-11（v6）
- 新增：「設定」tab 內的命名區塊，支援自訂序號格式（零補位/純數字/不顯示）、書名開關、分隔符號

### 2026-06-10（v5）
- 新增：下載時自動將簡體轉為台灣繁體（全自動，使用 opencc s2twp）
- 新增：主視窗「轉換」tab，支援多選 TXT 批次轉繁，可覆蓋原檔或另存 _TC 新檔
- 重構：主視窗改為 Notebook 結構（下載 / 轉換 兩個 tab）

### 2026-06-10（v4）
- 新增：主 UI「書籍目錄網址」框加「下載至」列，可直接輸入或瀏覽選擇輸出資料夾
- 新增：設定視窗加「下載」tab，支援調整重試次數（1–10）與重試間隔（1–30 秒）
- 改善：downloader 的 retry 設定改為參數傳入，不再依賴 module-level hardcode

### 2026-06-10（v3）
- 新增：下載失敗後出現「重試 N 卷失敗」按鈕，一鍵重跑失敗卷
- 修正：下載也改用 `curl_cffi` Chrome TLS 指紋，解決 dl.wenku8.com 的 429 問題
- 修正：目錄頁為 GBK 編碼，改傳 bytes 給 BeautifulSoup 自動偵測，解決書名亂碼
- 修正：`parse_book_title` 加 regex 去除 title tag 的網站垃圾（「小说在线阅读與TXT下载…」）
- 修正：`ttk.Checkbutton` 不接受 `font=` 參數導致載入後 crash
- 修正：視窗最小寬度 600 → 800
- 修正：title_label 和 status_bar 綁定 wraplength，防止長文字撐寬視窗
- 技術：scraper 和 downloader 各自維護 module-level curl_cffi Session，重用 TLS 連線

### 2026-06-10（v2）
- 修正：改用 `curl_cffi` 模擬 Chrome 120 TLS 指紋，解決 Cloudflare 403 問題（目錄頁）
- 新增：卷選單（勾選清單 + 全選/全不選），可選擇要下載的卷
- 新增：`parse_aid_from_url` 支援 `/book/XXXX.htm`、純數字書號
- 修正：錯誤訊息過長造成視窗自動變寬

### 2026-06-10（v1）
- 新增：初始版本，完成主要下載功能
