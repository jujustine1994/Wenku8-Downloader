# TODO

1. 校正專案 MD（依新模板：ARCHITECTURE 補現狀，CHANGELOG 拿掉現狀段）
2. **UI 介面美觀修正**：分頁標籤字體/大小、設定改為常駐 tab 已於 v12 完成；其餘排版、間距、視覺細節仍可再檢視
3. **下載也比照修復邏輯「重試到成功」**：目前初次下載（`下載選取`）網路層已支援無限重試（設定「無限重試」），但一卷內只做一輪 utf-8/GBK 比對，不像 `repair_volume` 會多輪持續重試到完全無亂碼；v11 修好 BOM 誤判根因後亂碼機率已大幅降低，此項優先度下修，先觀察後續是否還需要
4. **程式碼加上註解增加可維護性**：目前多數函式僅靠命名與型別提示表意，缺乏解釋「為什麼這樣做」的註解（特別是 wenku8 API 的怪異行為、BOM 偵測邏輯等非顯而易見的部分）
5. **技術細節寫入對應 MD 文件**：把目前散落在程式碼註解或對話紀錄裡的技術決策（例如 wenku8 charset 參數實際行為、亂碼修復策略）整理進 docs/ARCHITECTURE.md 或 docs/PITFALLS.md
6. **初次下載時的無限重試阻塞問題（若有需要再做）**：目前初次下載若開啟「無限重試」，單一卷卡住會擋住整批後續卷下載，只能靠手動「跳過目前卷」化解，沒有自動 fallback（例如逾時或次數門檻自動跳過）。v16 把「重試/修復」合併成懶人流程後，緩解了下載完再處理的體驗，但初次下載當下卡住的問題本身還在；若後續實際使用中常遇到，再評估要不要加自動化保險機制
7. **`feat/i18n` 分支已 merge 進 `main`（2026-08-18），遠端分支還留著沒刪**：要不要刪除 `origin/feat/i18n`，等進到這個專案時再評估決定

## i18n 多語言遷移（分支 `feat/i18n`，做到一半）

**完整接手說明在專案根目錄 `I18N_RESUME.md`**，以下只列待辦重點。

8. **`src/main.py` 還有 142 條寫死中文要搬 `t()`**（批次 3 未完成）。母表
   `src/locales/zh_tw.py` 已整份寫好，key 與譯文都定好了，這步是純字面替換。
   三個要小心的點：① `THEMES` 的 `"name"` 欄要改放 key，不可在 import 時求值
   ② `_poll_queue()` 的 `{current:02d}` 格式碼不可進譯文，呼叫端先算好
   ③ `_open_preview_dialog()` 的「正式卷／外傳」下拉要用區域常數
   `CAT_MAIN, CAT_SIDE = t(...), t(...)` 後再比對，不可每次重新求值
9. **`src/locales/{zh_cn,en,ja}.py` 目前是空的 `STRINGS = {}`**（批次 5 未做）。
   譯文拿不準的 7 個 key 列在 `I18N_RESUME.md` 第 5 節，含四語建議值
10. **`tests/test_i18n.py` 尚未建立**（批次 6 未做）。ALLOWLIST 只該有
    `i18n.py` / `logtext.py` / `sitedata.py` 三個檔，再加就是把測試關掉；
    另需一條反向測試釘住 `main.py` 在掃描範圍內，以及一條
    `test_nothing_shadows_the_translation_function`
11. **`tests/test_downloader.py` 324／358／376／465 行要跟著改**：目前斷言
    `log_msg[4] == "偵測到亂碼"` 等字面，建議改成跟 `t("dl.detail.*")` 比對。
    現在是綠的（預設語言繁中），但改譯文或在非繁中語言下跑就會紅
12. **`_enable_wheel_scroll()` 的 `bind_all` handler 洩漏**（非 i18n 範圍，
    順手發現）：`main.py` 每個 canvas 都 `root.bind_all(..., add="+")`，
    `_open_identify_dialog()` 每開一次就多一個殘留 handler，關閉對話框不會移除。
    `_open_preview_dialog()` 已改綁自己的 Toplevel 迴避，`_open_identify_dialog()`
    沒比照辦理
13. **`show_cth_banner()` 直接 print ANSI escape**（順手發現）：非 tty
    （輸出重導到檔案）時會噴裸的 escape 序列
