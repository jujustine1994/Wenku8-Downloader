"""locales/zh_tw.py — 繁體中文（母表）

改這裡的譯文不影響任何邏輯：程式一律用 key 比對。改錯最壞的情況只是
畫面顯示怪怪的。

⚠ 這裡只放**顯示在畫面上**的字。會落進檔名／檔案內容、或拿去跟網站抓下來
的文字比對的字串，一律在 src/sitedata.py，不進這張表。
⚠ 落進 logs/app.log 的字串在 src/logtext.py，固定繁中，不進這張表。

帶變數一律用**具名** placeholder（{book} 而不是 {0}）：翻譯時語序一變，
位置參數就錯位。數字格式（{current:02d} 這種）由呼叫端先算好再餵進來，
不放進譯文——翻譯者改到格式碼會靜默把數字弄錯。
"""

from __future__ import annotations

STRINGS: dict[str, str] = {
    # ── 主題名稱（THEMES 表的第二欄放的是這裡的 key，不是中文字面）──
    "theme.light":     "清爽白",
    "theme.dark":      "深色模式",
    "theme.financial": "金融藍",

    # ── 分頁標籤（前後空白是版面留白，翻譯時請保留）──
    "gui.tab.download": "  下載  ",
    "gui.tab.convert":  "  轉換  ",
    "gui.tab.settings": "  設定  ",

    # ── 下載分頁 ──
    "gui.frame.url":         " 書籍目錄網址 ",
    "gui.btn.load":          "載入",
    "gui.lbl.download_to":   "下載至：",
    "gui.btn.browse":        "瀏覽",
    "gui.frame.volumes":     " 卷列表 ",
    "gui.lbl.no_book":       "（輸入網址後點「載入」）",
    "gui.btn.select_all":    "全選",
    "gui.btn.deselect_all":  "全不選",
    "gui.btn.download":      "下載選取",
    "gui.btn.recover":       "重試/修復",
    "gui.btn.recover_n":     "重試/修復 {n} 卷",
    "gui.btn.scan":          "掃描既有檔案",
    "gui.btn.manage":        "管理",
    "gui.btn.skip":          "跳過目前卷",
    "gui.frame.progress":    " 進度 ",
    "gui.frame.log":         " 記錄 ",
    "gui.status.waiting":    "等待中...",
    "gui.status.ready":      "就緒",

    # ── 轉換分頁 ──
    "gui.conv.hint":         "把已下載的 TXT 檔案批次轉換成台灣繁體中文（簡轉繁），不需要重新下載。",
    "gui.conv.no_files":     "未選擇任何檔案",
    "gui.conv.n_files":      "已選 {n} 個檔案",
    "gui.btn.choose_files":  "選擇檔案",
    "gui.frame.files":       " 檔案列表 ",
    "gui.lbl.output":        "輸出：",
    "gui.conv.overwrite":    "覆蓋原檔",
    "gui.conv.new_file":     "另存新檔（加 _TC 後綴）",
    "gui.btn.convert":       "開始轉換",
    "gui.btn.remove":        "移除",
    "gui.dlg.choose_txt":    "選擇 TXT 檔案",
    "gui.filetype.txt":      "文字檔案",
    "gui.filetype.all":      "所有檔案",
    "gui.status.converting":   "轉換中... 共 {n} 個檔案",
    "gui.status.convert_done": "轉換完成 {success}/{total}",

    # ── 下載路徑 ──
    "gui.dlg.choose_folder":   "選擇下載資料夾",
    "gui.status.output_dir":   "下載位置：{path}",
    "gui.status.path_missing": "路徑不存在：{path}（下載時會自動建立）",

    # ── 設定分頁 ──
    "gui.settings.appearance":    "外觀",
    "gui.btn.appearance_dlg":     "外觀設定...",
    "gui.settings.theme_summary": "目前主題：{name}",
    "gui.settings.download":      "下載",
    "gui.lbl.retry_count":        "重試次數：",
    "gui.unit.times":             "次",
    "gui.chk.infinite_retry":     "無限重試（直到成功或手動跳過）",
    "gui.lbl.retry_delay":        "重試間隔：",
    "gui.unit.seconds":           "秒",
    "gui.settings.naming":        "命名",
    "gui.lbl.index_format":       "序號格式",
    "gui.naming.padded":          "零補位（01, 02…）",
    "gui.naming.plain":           "純數字（1, 2…）",
    "gui.naming.none":            "不顯示",
    "gui.chk.include_book":       "檔名含書名",
    "gui.lbl.separator":          "分隔符號：",
    "gui.lbl.sep_hint":           "（空白 = 空格）",
    "gui.naming.sample_book":     "書名",
    "gui.naming.sample_vol":      "第一卷",
    "gui.naming.preview":         "預覽：{name}",
    "gui.settings.identify":      "識別（外傳關鍵字）",
    "gui.btn.identify_dlg":       "識別設定...",
    "gui.settings.kw_summary":    "目前共 {n} 個關鍵字",
    "gui.btn.apply":              "套用",
    "gui.btn.cancel":             "取消",
    "gui.status.settings_applied": "設定已套用",

    # ── 外觀設定視窗 ──
    "gui.dlg.appearance":     "外觀設定",
    "gui.lbl.color_theme":    "配色主題",
    "gui.lbl.preview":        "預覽",
    "gui.preview.download_all": "下載全部",

    # ── 識別設定視窗 ──
    "gui.dlg.identify":       "識別設定（外傳關鍵字）",
    "gui.lbl.side_keywords":  "外傳關鍵字",
    "gui.btn.delete":         "刪除",
    "gui.btn.add":            "新增",

    # ── 確認分類視窗 ──
    # ⚠ gui.cat.main / gui.cat.side 是下拉選單的顯示文字，同一次對話框內拿來
    #   比對使用者選了哪一項。兩者在任一語言下都**不可以翻成相同的字**，
    #   否則所有卷都會被判成正式卷（tests/test_i18n.py 有一條測試釘住這點）。
    #   它們跟檔名前綴「外傳」是兩回事——檔名前綴在 sitedata.SIDE_INDEX_PREFIX。
    "gui.dlg.preview_title":  "確認分類 - {book}",
    "gui.lbl.book_summary":   "書名：{book}　共 {n} 卷",
    "gui.cat.main":           "正式卷",
    "gui.cat.side":           "外傳",
    "gui.btn.mark_main":      "已選標為正式卷",
    "gui.btn.mark_side":      "已選標為外傳",
    "gui.btn.confirm":        "確認",
    "gui.status.loaded_hint": "載入完成，勾選要下載的卷後按「下載選取」",
    "gui.status.loaded":      "已載入：{book}，共 {n} 卷",
    "gui.status.load_cancelled": "已取消載入",

    # ── 管理待處理卷視窗 ──
    "gui.dlg.manage":      "管理待處理卷",
    "gui.lbl.manage_hint": "取消勾選 = 移出重試列表",

    # ── 載入目錄 ──
    "gui.status.loading_title":     "載入中...",
    "gui.status.fetching_catalog":  "正在取得目錄...",
    "gui.status.loading_book":      "正在載入書籍目錄...",
    "gui.status.load_failed_title": "載入失敗",
    "gui.status.load_failed_hint":  "載入失敗，請確認網址",

    # ── 下載／修復進行中 ──
    "gui.status.downloading":  "下載中... 共 {n} 卷",
    "gui.status.processing":   "處理中... 共 {n} 卷",
    "gui.log.auto_repair":     "自動修復 第{round}輪 共 {n} 卷",
    "gui.status.scan_found":   "掃描完成，發現 {n} 卷缺檔/亂碼",
    "gui.status.scan_clean":   "掃描完成，沒有發現問題",
    "gui.progress.downloading": "正在下載 {current}/{total}：{name}",
    "gui.progress.done":       "完成 {success}/{total} 卷",
    "gui.status.download_done": "下載完成",
    "gui.status.repair_done":   "修復完成",
    "gui.status.batch_done":    "{prefix} {success}/{total}{suffix}",
    "gui.status.batch_suffix":  "，{parts}",
    "gui.status.fail_list":     "失敗：{names}",
    "gui.status.garbled_list":  "亂碼：{names}",
    "gui.sep.list":             "；",
    "gui.sep.names":            ", ",
    "gui.status.auto_done":     "自動處理完成，成功 {success}/{total} 卷，{n} 卷需要你手動處理（可點「重試/修復」再試）",

    # ── 錯誤訊息 ──
    "err.path_empty":     "下載路徑不能為空，請先設定「下載至」",
    "err.path_unusable":  "下載路徑無法使用：{path}（{err}）",
    "err.bad_url":        "網址格式錯誤，找不到 aid 參數",
    "err.no_selection":   "請至少勾選一卷",
    "err.http403_hint":   "（403 錯誤：網站拒絕存取，可稍後再試）",
    "err.load_failed":    "載入失敗：{err}{hint}",

    # ── 下載／修復的單卷結果（推到畫面的記錄區，不落檔）──
    "dl.detail.garbled":       "偵測到亂碼",
    "dl.detail.skipped":       "已跳過",
    "dl.detail.retry_failed":  "retry {retry} 失敗",
    "dl.detail.error":         "錯誤：{err}",
    "dl.detail.repair_failed": "修復失敗",
    "dl.detail.still_garbled": "修復後仍有亂碼",
    "dl.detail.repaired":      "已修復",
    "dl.retry.infinite":       "無限次",

    # ── 簡轉繁 ──
    "conv.detail.encoding_fixed": "偵測為 {enc} 編碼，已修正",
}
