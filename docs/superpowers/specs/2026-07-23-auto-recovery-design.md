# 設計規格：下載完自動接續修復

日期：2026-07-23
狀態：已核准

---

## 需求摘要

目前下載完成後，若有失敗卷（網路完全抓不到）或亂碼卷（抓到但編碼爛掉），使用者必須手動按「重試/修復」才會繼續處理。使用者的理想狀態是「輸入網址、全部自動跑到好」：下載完成後不用手動介入，程式自動接續修復，直到全部成功或遇到真的解決不了的問題才停下來，並清楚報告哪些卷需要人工處理。

**重要澄清（已跟使用者確認）**：不是所有錯誤都能自動修好——暫時性問題（網路瞬斷、編碼誤判）可以自動修好；永久性問題（來源端內容真的消失、書號打錯）沒有任何自動化機制能真的解決，只能重試到一個合理次數上限後清楚回報，不能讓程式安靜卡住或無限空轉。

**範圍不含**：
- 「掃描既有檔案」按鈕維持原設計不變——掃描只補待修復清單，不自動觸發修復（這是先前 `2026-07-23-scan-existing-files-design.md` 就定案的行為，這次不更動）
- 「無聲亂碼偵測」（解碼沒拋錯但內容其實是錯的）：評估後這類情況本來就發生機率很低，需要額外內建常用字表才能可靠偵測，投入產出比不划算，本次不做
- 下載端加 Big5 編碼候選：**已確認技術上無效**（見下方「不在本次範圍內」），改成補一條 PITFALLS.md 記錄，不寫程式碼

---

## 架構設計

### 1. 下載完自動接續修復（固定行為，不加開關）

`main.py` 的 `"done"` 訊息 handler 目前收到 `run_download_all` 的結果後，只是更新按鈕/清單狀態，等使用者手動按「重試/修復」。改為：**如果這次收到的 `"done"` 是來自「初次下載」（`not self._repair_mode`）且合併後的待處理清單非空，直接自動觸發修復流程**，不用等按鈕。

### 2. 自動修復停損機制

自動修復流程需要一個「多少嘗試後放棄」的上限，避免真的下載不到的卷讓程式無限空轉。依照使用者目前的重試設定（`self._retry_count`）分兩種情況：

**有限重試模式**（`self._retry_count > 0`）：
- 自動修復最多跑 **3 輪**（`AUTO_REPAIR_ROUND_LIMIT = 3`）在整批待處理卷上
- 每一輪都是完整跑一次 `run_repair_all`（沿用現有邏輯，`repair_volume` 內部本來就有的「連續 5 輪沒改善就放棄」機制不變）
- 3 輪後如果清單還非空，停下來，清楚報告「成功 X 卷，Y 卷需要你手動處理」

**無限重試模式**（`self._retry_count <= 0`）：
- 因為單一卷的 HTTP 請求設計成「重試到成功或 `skip_event` 被觸發」，不會自然結束，用「輪數」當停損點對它沒有意義（連第 1 輪都跑不完）
- 改為在 `_fetch_bytes` 加一個新參數 `max_attempts: int | None = None`：當設定時，即使 `retry_count <= 0`（無限模式），單次 HTTP 請求循環也會在達到 `max_attempts` 次嘗試後放棄（回傳 `None`，跟有限重試次數耗盡時行為一致）
- `repair_volume` 的外層停滯偵測迴圈（`stale_rounds >= REPAIR_STALE_LIMIT`）目前只在 `not infinite` 時生效；改為 `max_attempts` 有設定時也視同「有界」，套用同一個 5 輪停滯偵測邏輯來決定放棄
- 自動修復流程呼叫 `run_repair_all` 時，若偵測到無限重試模式，額外傳入 `max_attempts=50`（`AUTO_REPAIR_MAX_ATTEMPTS = 50`），只跑 **1 輪**（因為每一卷在這 1 輪內，靠 `max_attempts` + 既有的 5 輪停滯偵測，已經得到足夠充分的嘗試機會，不需要再疊加多輪）
- **重要**：`max_attempts` 只在「自動修復流程」內部使用；使用者自己手動按「重試/修復」（`_on_recover()`）時完全不傳這個參數，維持現有的真無限重試行為不變

**不管哪種模式，被自動流程放棄的卷都不會消失**——它們留在 `self._recovery_volumes` 待處理清單裡，使用者隨時可以手動再按「重試/修復」重跑（不受這次自動流程的次數限制），或是之後再次觸發「掃描既有檔案」也會重新抓到它們。

### `src/downloader.py` 變更

**`_fetch_bytes` 新增 `max_attempts` 參數**：
```python
def _fetch_bytes(aid: str, vid: int, charset: str,
                 retry_count: int, retry_delay: float,
                 skip_event=None, max_attempts: int | None = None) -> bytes | None:
```
在例外處理的放棄判斷加一行：
```python
if not infinite and attempt >= retry_count:
    return None
if max_attempts is not None and attempt >= max_attempts:
    return None
```

**`_fetch_best_text` 透傳 `max_attempts`**（簽名新增同名參數，往下傳給兩次 `_fetch_bytes` 呼叫）。

**`repair_volume` 新增 `max_attempts` 參數**，透傳給 `_fetch_best_text`；外層停滯偵測條件從：
```python
if not infinite and stale_rounds >= REPAIR_STALE_LIMIT:
    break
```
改為：
```python
if (not infinite or max_attempts is not None) and stale_rounds >= REPAIR_STALE_LIMIT:
    break
```

**`run_repair_all` 新增 `max_attempts` 參數**，透傳給每一卷的 `repair_volume` 呼叫。

**`download_volume`/`run_download_all` 不需要改動**——`max_attempts` 只在修復流程使用，初次下載维持現狀（`_fetch_best_text` 新增的參數有預設值 `None`，向下相容）。

### `src/main.py` 變更

**新增共用方法 `_dispatch_repair()`**：把 `_on_recover()` 裡「設定按鈕狀態、寫 log 分隔線、開執行緒跑 `run_repair_all`」這段共用邏輯抽出來，`_on_recover()`（手動觸發）和自動修復流程都呼叫這個方法，避免重複程式碼：
```python
def _dispatch_repair(self, vols, output_dir, log_label, max_attempts=None):
    """共用的修復執行緒派工，_on_recover()（手動）與自動修復流程都呼叫這個。"""
```
參數：
- `vols`: 這一輪要處理的卷清單
- `output_dir`: 輸出資料夾
- `log_label`: 寫進 `log_text` 分隔線的文字（例如 `"重試/修復 3 卷"` 或 `"自動修復 第2輪 共 3 卷"`）
- `max_attempts`: 透傳給 `run_repair_all`，`None` 表示不限制（手動觸發一律傳 `None`）

**新增狀態欄位**（跟 `self._recovery_volumes` 一樣的生命週期，在 `_on_download()` 開始時重置為初始值，`_reset_book_state()` 也要重置）：
- `self._auto_repair_active: bool` — 目前是否處於自動修復鏈中
- `self._auto_round: int` — 目前跑到第幾輪（只在有限重試模式下有意義）

**新增方法 `_start_auto_repair()`**：從 `self._recovery_volumes` 取出全部待處理卷，設定 `self._auto_repair_active = True`、`self._auto_round = 1`，依照 `self._retry_count` 決定要不要傳 `max_attempts`，呼叫 `self._dispatch_repair(...)`。

**`"done"` 訊息 handler 新增自動鏈邏輯**（接在現有的合併/按鈕狀態更新邏輯之後）：
- 若 `self._auto_repair_active` 為真（代表這個 `"done"` 是自動修復某一輪跑完）：
  - 若 `recovery_count == 0`：全部成功，`self._auto_repair_active = False`（既有的成功狀態列文字已經涵蓋，不用另外處理）
  - 若已達到輪數上限（有限模式 `self._auto_round >= AUTO_REPAIR_ROUND_LIMIT`；無限模式一律只跑 1 輪，跑完不管清單是否還非空都視為到上限）：`self._auto_repair_active = False`，狀態列顯示「自動處理完成，成功 X/Y 卷，Z 卷需要你手動處理（可點「重試/修復」再試）」
  - 否則：`self._auto_round += 1`，取出目前 `self._recovery_volumes` 清空並呼叫 `self._dispatch_repair(...)` 開始下一輪
- 否則，若 `not self._repair_mode`（代表這是初次下載跑完，不是修復）且 `recovery_count > 0`：呼叫 `self._start_auto_repair()` 觸發自動修復鏈

**`_on_recover()` 開頭加一行 `self._auto_repair_active = False`**——確保使用者手動觸發時，不會被誤判成自動鏈的一部分而被自動邏輯接管。

---

## PITFALLS.md 新增條目（取代原本的 Big5 候選程式碼異動）

### 不在本次範圍內：下載端加 Big5 編碼候選

原本評估要在下載端（`downloader.py` 的 `_fetch_best_text`）比照「轉換」tab 加一個 Big5 編碼候選，但重新檢視 `downloader.py:51-54` 既有註解後確認：**wenku8 下載 API 的 `charset` query 參數不可信，實測 `charset=big5` 實際回傳的是 UTF-8 bytes，不是真的 Big5 編碼內容**。對下載 API 帶 `charset=big5` 打第三次網路請求，實際上不會拿到有意義的新資訊，純粹浪費一次網路請求。這個限制只存在於「打 wenku8 API」的情境；「轉換」tab 的 Big5 候選是處理本機既有檔案（來源不明），技術前提不同，不受此限制。

**改為在 `docs/PITFALLS.md` 新增 P5 條目**，明確記錄這個結論，避免以後（包含未來的自己）重複假設「加更多 charset 候選打 API 就能解決編碼問題」：

```markdown
## P5: wenku8 下載 API 的 charset 參數不可信
- **問題**：`dl.wenku8.com/packtxt.php` 的 `charset` query 參數名稱不能反映實際回傳的編碼——實測 `charset=utf-8` 實際回傳 UTF-16 LE bytes（帶 BOM），`charset=big5` 實際回傳 UTF-8 bytes（帶 BOM）。這代表無法靠切換 `charset` 參數的值來讓 API 老實回傳「你要求的」編碼內容
- **解法**：一律先偵測 BOM 決定實際解碼方式（`_decode_response`），不要相信 `charset` 參數名稱；`_fetch_best_text` 只在 utf-8 結果含亂碼時額外嘗試 `charset=gbk` 做比對（這是目前唯一驗證過有意義的候選組合）
- **禁止**：不要為了「增加編碼候選」而對這個 API 加更多不同的 `charset` 值去打（例如 `charset=big5`）——已驗證這類請求不會取得跟其他候選不同的實際內容，只會浪費一次網路請求，對修復亂碼沒有幫助
```

---

## 測試計畫

- `_fetch_bytes`：新增測試驗證 `max_attempts` 參數在 `retry_count<=0`（無限模式）下，達到次數上限會回傳 `None`（跟有限模式耗盡重試次數行為一致）
- `repair_volume`：新增測試驗證 `max_attempts` 有設定時，無限重試模式下的外層停滯偵測迴圈會在 `REPAIR_STALE_LIMIT` 輪後正確放棄（而不是無限迴圈）
- `run_repair_all`：新增測試驗證 `max_attempts` 參數會正確透傳到每一卷的 `repair_volume` 呼叫
- `main.py` 部分延續現有慣例（GUI 改動無自動化測試），改完跑 `pytest tests/`（回歸測試）+ `py_compile` + 手動驗證：
  - 下載一批包含刻意失敗的卷，確認完成後自動接續修復，不用手動按按鈕
  - 確認自動修復跑滿輪數上限後，清單裡還有問題的卷會清楚顯示在狀態列，且「重試/修復」按鈕仍可手動再點一次
  - 確認手動按「重試/修復」時，行為（含無限重試）完全不受這次改動影響
