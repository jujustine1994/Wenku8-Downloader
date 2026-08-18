# i18n 遷移 — 接手說明（未完成）

分支 `feat/i18n`，從 `9049ef2` 開出。**未合併、未 push。**
工作區乾淨，所有已提交的狀態都是測試全綠的。

作業因額度中斷而停在**批次 3 進行中**。下面的內容讓你不必重新盤點。

---

## 1. 現在停在哪

| 批次 | 內容 | 狀態 |
|---|---|---|
| 0 | 區域變數 `t` 改名 | ✅ 完成 |
| 1 | i18n.py + 語言檔 + config + 首次選語言 + 語言選單 + 重啟提示 | ✅ 完成 |
| 2 | log 字串抽 `logtext.py`、資料字串抽 `sitedata.py` | ✅ 完成 |
| 3 | GUI 介面文字 | ⚠ **做一半**：`downloader.py`／`converter.py` 完成，**`main.py` 完全沒動** |
| 4 | 錯誤訊息 | ❌ 未做（key 已備妥，見下） |
| 5 | 简中／英／日譯文 | ❌ 未做（三個語言檔目前是空的 `STRINGS = {}`） |
| 6 | 防退化測試 | ❌ 未做 |

### commit 清單

```
e59f41f  refactor: 區域變數 t 改名為 theme，讓出 t 這個名稱給 i18n
1cb9fc6  feat(i18n): 批次1 查表核心 + 空語言檔 + 語言設定 + 首次啟動選語言
c7af7a3  feat(i18n): 批次2 log 字串抽 logtext.py + 資料字串抽 sitedata.py
92cb0e2  feat(i18n): 批次3(部分) downloader/converter 的畫面訊息走 t()
```

---

## 2. 下一步具體要做什麼

**`src/main.py` 還有 142 條寫死的中文字面要搬。** 母表 `src/locales/zh_tw.py`
**已經整份寫好了**（含 main.py 用得到的全部 key），所以這一步是純粹的
「把字面換成 `t("key")`」，不需要再想 key 名稱、不需要再想譯文。

### 已經替你做好的準備

- `src/locales/zh_tw.py` — 完整母表，key 與譯文都定好了
- `main.py` 開頭已經 `from src.i18n import t` 與 `from src import i18n`，可直接用

### 逐項對照表（行號以 commit `92cb0e2` 的 `src/main.py` 為準）

盤點用的腳本在
`C:\Users\CTH\AppData\Local\Temp\claude\...\scratchpad\inventory.py`，
但那是暫存區可能已清掉。要重跑就用 AST 掃 `ast.Constant` 且 `re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", value)`，排除 docstring。

主要區塊與對應 key 前綴：

| main.py 位置 | 內容 | key |
|---|---|---|
| `THEMES` 的 `"name"` 欄 | 清爽白／深色模式／金融藍 | `theme.light` / `theme.dark` / `theme.financial` |
| `_build_ui()` | 分頁標籤、LabelFrame 標題、按鈕 | `gui.tab.*` `gui.frame.*` `gui.btn.*` |
| `_build_convert_tab()` | 轉換分頁 | `gui.conv.*` `gui.filetype.*` |
| `_build_settings_tab()` | 設定分頁 | `gui.settings.*` `gui.lbl.*` `gui.naming.*` |
| `_open_appearance_dialog()` | 外觀視窗 + `draw_preview()` 畫布文字 | `gui.dlg.appearance` `gui.lbl.color_theme` `gui.preview.download_all` |
| `_open_identify_dialog()` | 識別視窗 | `gui.dlg.identify` `gui.lbl.side_keywords` |
| `_open_preview_dialog()` | 確認分類視窗 | `gui.dlg.preview_title` `gui.cat.*` `gui.btn.mark_*` |
| `_manage_recovery_dialog()` | 管理待處理卷 | `gui.dlg.manage` `gui.lbl.manage_hint` |
| `_poll_queue()` | 進度／完成／失敗清單 | `gui.progress.*` `gui.status.*` |
| 各處 `_set_status(...)` | 錯誤訊息 | `err.*` |

### ⚠ 三個特別要小心的點

1. **`THEMES` 的 `"name"` 欄改放 key，不是中文字面。**
   `t()` 不可以在 import 時求值（模組層級常數會凍結在預設語言）。
   改完 `_theme_summary_text()` 與 `_open_appearance_dialog()` 的
   radiobutton 都要改成 `t(info["name"])`。

2. **`{current:02d}` 的格式碼不可以進譯文。**
   `_poll_queue()` 的 `f"正在下載 {current:02d}/{total}：{vol_name}"`
   要在呼叫端先算好：
   `t("gui.progress.downloading", current=f"{current:02d}", total=total, name=vol_name)`
   格式碼留在譯文裡，翻譯者改成 `:02f` 會靜默把數字弄錯且不報錯。

3. **`_open_preview_dialog()` 的 `正式卷` / `外傳` 下拉選單**
   這兩個字串在同一個對話框內被拿去比對（`cv.get() == "正式卷"`）。
   做法：在對話框開頭取一次區域常數
   ```python
   CAT_MAIN, CAT_SIDE = t("gui.cat.main"), t("gui.cat.side")
   ```
   之後 `values=[CAT_MAIN, CAT_SIDE]`、`_mark_selected(CAT_MAIN)`、
   `"main" if cv.get() == CAT_MAIN else "side"` 全部用這兩個常數。
   **絕對不要**每次呼叫 `t()` 重新求值後拿去比對。
   這跟檔名前綴「外傳」是兩回事，見下面第 4 節。

---

## 3. 已知還沒過的驗收項目

已經過的：

- ✅ 繁中 GUI 建置成功，248 條 widget 文字，殘留 key 0（含 Treeview.heading、
  Combobox.values、`tk.Text.get("1.0","end")`、Canvas `create_text`）
- ✅ 檔名／目錄／檔案內容 golden 與改前**逐字相同**（12 條路徑 + 12 個檔案，
  4 種命名選項組合，走真正的 `build_filepath()` 與 `run_download_all()`，
  網路以 mock 取代，沒有打真的 wenku8）
- ✅ 9 條 log 行與改前 f-string **逐字相同**
- ✅ 既有 89 條測試全綠，**一條都沒改**

**還沒做的：**

1. ❌ 四語各建置一次 GUI、殘留 key 0 —— 目前只驗過繁中（其餘三語言檔是空的，
   現在跑一定整片顯示 key）
2. ❌ 四語 key 集合一致 + placeholder 一致
3. ❌ 四語產出檔案比對（繁中已對過改前基準，另三語未跑）
4. ❌ 首次啟動語言視窗的自動化驗證（`after()` 排模擬點擊，**不要用
   `wait_window` 卡住**）
5. ❌ 負向驗證（故意塞中文常數／刪某語言檔一個 key／塞一個叫 `t` 的區域變數，
   確認測試都會紅）
6. ❌ 批次 6 的防退化測試整組

### 測試檔要注意的事

- `tests/` 目前 89 條。批次 6 要新增 `tests/test_i18n.py`。
- ⚠ **掃描路徑用 `src/` 是對的**（本專案 `.py` 確實都在 `src/`），
  但仍要 `assert len(files) > 0`，否則 parametrize 收集到 0 個 case 時
  測試會「通過」但什麼都沒檢查。
- ⚠ 不可以每個 test 建一個 `tk.Tk()`（Microsoft Store 版 Python 會間歇性丟
  `TclError: Can't find a usable init.tcl`）。用 session 級 fixture 共用一個
  隱藏的 `tk.Tk()`，各測試開 `Toplevel`。
- ALLOWLIST 只該有三個檔：`i18n.py`（語言自稱）、`logtext.py`（log 固定繁中）、
  `sitedata.py`（資料字串）。**再加就是把測試關掉。**
  另外要有一條反向測試釘住 `main.py` 確實在掃描範圍內。
- **有 4 條既有測試會因為批次 3 而需要跟著改**（目前還沒改，因為預設語言是
  繁中所以還是綠的）：`tests/test_downloader.py` 的 324／358／376／465 行，
  斷言 `log_msg[4] == "偵測到亂碼" / "已修復" / "修復後仍有亂碼" / "已跳過"`。
  它們現在比對的是 `t()` 的繁中輸出，**建議改成跟 `t("dl.detail.*")` 比對**，
  否則之後有人改譯文就會紅，而且在非繁中語言下跑會紅。

---

## 4. 判定為「資料」不翻的清單與理由 ★重要★

全部集中在 `src/sitedata.py`，該檔在測試 ALLOWLIST 裡。**接手的人不要動這些。**

| 常數 | 內容 | 翻了會怎樣 |
|---|---|---|
| `SIDE_INDEX_PREFIX` | `"外傳"` | **進檔名**（`外傳01 書名 番外篇.txt`）。翻了之後使用者切一次語言，同一本書的外傳存到另一組檔名，舊檔案對不起來，「掃描既有檔案」全部判成缺檔然後整批重抓 |
| `DEFAULT_SIDE_KEYWORDS` | 外傳／番外／特典／幕間… | 拿去跟 **wenku8 抓下來的卷名**做小寫 `in` 比對，**而且會存進 `.tool_config.json`**。翻了＝分類靜默失效，全部卷變正式卷 |
| `MAIN_VOLUME_RE` | `第[一二三…]+[卷册冊部篇章]` 等 | 解析網站 HTML 的樣式。**簡繁字形都要留**（`册`／`冊` 兩個都在）。動了就抓不到 |
| `TITLE_TRIM_RE` | `小说\|TXT\|全文\|在线\|电子书` | ⚠ **這些簡體字是 wenku8 的網站原文**，不是「該翻成繁中的介面文字」。改成繁體＝書名解析靜默失效 |
| `UNKNOWN_BOOK_TITLE` | `"未知書名"` | 解析不到書名時會變成 `book_name`，**直接進檔名** |

### 其他判成資料、留在原處沒動的

- `THEMES` 的 key（`light`／`dark`／`financial`）、`filename_index` 的
  `padded`／`plain`／`none`、`_conv_output_var` 的 `overwrite`／`new_file`
  —— 都會存進 `.tool_config.json`，本來就是英文代號，正確
- `_TC` 後綴、`.txt` 副檔名、`s2twp`（OpenCC 設定名）
- msg_queue 的訊息類型（`"log"`／`"done"`／`"progress"`…）與狀態等級
  （`ok`／`warn`／`skip`／`fail`／`info`／`success`／`error`）
- `converter._FALLBACK_ENCODINGS` 的編碼標籤（`UTF-8 (BOM)` 等）——
  是編碼名稱，且拿去跟 `"utf-8"` 比對。外層那句「偵測為 {enc} 編碼，已修正」
  才是介面文字（已搬）
- ✅／⚠️／⏭️／❌ 圖示，`──` 分隔線
- **從網站 parse 出來的書名、卷名一律原樣使用**，沒有任何一處被翻譯或轉換

> 本專案**不產出 EPUB**，只產出純文字 `.txt`（內容是小說正文，全部來自網站，
> 沒有任何程式產生的顯示文字）。所以「EPUB metadata 欄位鍵／`content.opf`
> 欄位名」這類規格欄位在本專案不存在，無需處理。
> 這也是為什麼批次 2 沒有「輸出檔顯示文字」可搬，改做了 log 字串分離。

### 灰色地帶（判成資料，但下次可以再想想）

- `_build_checkbox_list()` 裡卷列表的編號標籤，用的是跟檔名同一組
  `format_index_token(..., SIDE_INDEX_PREFIX)`。**目前判成資料不翻**，理由是
  讓使用者在清單上看到的就是待會存出來的檔名開頭。若之後覺得英文介面下
  看到「外傳01」很怪，可以改成顯示與檔名分離的一對函式，但那會讓兩者對不上。

---

## 5. 譯文待校對的 key

三個語言檔（`zh_cn` / `en` / `ja`）目前是**空的**，批次 5 才會填。
填的時候以下幾條我沒把握，請找懂的人確認：

| key | 繁中現值 | 疑慮 |
|---|---|---|
| `gui.cat.main` / `gui.cat.side` | 正式卷／外傳 | 輕小說的「正式卷 vs 外傳」在英文沒有標準譯法。建議 `Main Volume` / `Side Story`，日文 `本編` / `外伝`。⚠ **兩者在任一語言下都不可翻成相同的字**，否則所有卷會被判成正式卷 |
| `gui.conv.hint` | 「…轉換成台灣繁體中文（簡轉繁）」 | 轉換目標**固定是台灣正體**（OpenCC `s2twp`），跟使用者介面語言無關。英日譯文要講清楚是「轉成 Traditional Chinese (Taiwan)」，不要寫成「轉成你的語言」 |
| `gui.conv.new_file` | 另存新檔（加 _TC 後綴） | `_TC` 是實際檔名後綴（資料），四語都必須原樣保留 `_TC` |
| `gui.btn.recover` | 重試/修復 | 一個按鈕兩個動作，英文 `Retry / Repair` 會偏長，注意 `width=10` 可能要放寬 |
| `dl.detail.retry_failed` | `retry {retry} 失敗` | 裡面的 `retry` 是原文就有的英文字，不是 placeholder；`{retry}` 才是 |
| `gui.status.auto_done` | 自動處理完成…（可點「重試/修復」再試） | 句中引用了按鈕名稱，翻譯時要跟 `gui.btn.recover` 保持一致，否則使用者找不到那個按鈕 |
| `theme.financial` | 金融藍 | 主題名，意譯即可（`Finance Blue` / `金融ブルー`） |

另外：`gui.tab.*` 的值前後有**刻意的空白**（`"  下載  "`），那是分頁的版面留白，
四語都要保留。

---

## 6. 順手發現、但這次沒動的既有問題

1. **`_enable_wheel_scroll()` 用 `bind_all` 會累積 handler。**
   `main.py` 的 `_enable_wheel_scroll()` 對每個 canvas 都 `root.bind_all(...,
   add="+")`。`_open_identify_dialog()` 每開一次就多綁一個，**對話框關掉後
   handler 不會移除**。開 10 次識別設定就有 10 個殘留 handler 在跑
   `winfo_ismapped()`。`_open_preview_dialog()` 已經有註解說明並改綁在自己的
   Toplevel 上迴避這件事，但 `_open_identify_dialog()` 沒有比照辦理。
   （非 i18n 範圍，這次沒動。）

2. **`show_cth_banner()` 直接 `print()` ANSI escape。**
   非 tty（例如被重導到檔案）時會噴出裸的 escape 序列。

3. **`src/.tool_config.json` 已在 `.gitignore`**，這點是對的，不用改。

4. `logs/app.log` 目前是 git 追蹤外（`.gitignore` 有 `logs/`），正確。

---

## 7. 驗證用的暫存腳本（已在暫存區，可能已被清掉）

三支腳本，重建成本不高，內容摘要：

- `scan_t.py` — AST 掃出所有叫 `t` 的名稱（def／參數／指派／迴圈變數／import／
  `except as`／global）。**動任何 i18n 之前先跑這支**。目前結果應為 0。
- `golden_output.py` — 固定假資料 + mock 掉 `downloader._fetch_bytes`，
  走真正的 `build_filepath()` 與 `run_download_all()`，把檔名、相對路徑、
  檔案內容 sha256 全部存成 JSON。改前基準必須逐字相同。
  **不會打真的 wenku8。**
- `gui_probe.py` — 指定語言建整個 GUI（`withdraw()`，不進 mainloop），
  走訪 widget 樹收集文字，額外涵蓋 `Treeview.heading()`、`Combobox.values`、
  `tk.Text.get("1.0","end")`、`Canvas.itemcget(text)`，
  以 regex `^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$` 判定殘留 key。
  會順便開 4 個對話框讓它們的字串也被掃到。

建議批次 6 時把 `golden_output.py` 與 `gui_probe.py` 的邏輯正式收進
`tests/`，不要繼續放暫存區。
