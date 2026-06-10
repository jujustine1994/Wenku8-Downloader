# Design Spec: 輸出資料夾選擇 + 下載設定 tab

**Date:** 2026-06-10  
**Status:** Approved

---

## 目標

1. 讓使用者在主 UI 直接看到並修改下載目的地資料夾
2. 將 retry 次數與間隔從 hardcode 改為可在設定視窗調整
3. 所有設定持久化至 `.tool_config.json`

---

## 主 UI 變更

在「書籍目錄網址」LabelFrame（`frame_url`）內加第二行：

```
┌─ 書籍目錄網址 ────────────────────────────────────────┐
│ [url input..................................] [載入] [⚙] │
│ 下載至：[C:\Users\CTH\Downloads\novels       ] [瀏覽]  │
└──────────────────────────────────────────────────────────┘
```

**行為：**
- Entry（`path_var: tk.StringVar`）可直接鍵入路徑
- 失焦（`<FocusOut>`）或按 Enter（`<Return>`）時驗證路徑：
  - 路徑存在 → 儲存至 config，status bar 顯示 info
  - 路徑不存在 → status bar 顯示 error，Entry 保留輸入值（不回退）
- 「瀏覽」按鈕呼叫 `filedialog.askdirectory(initialdir=current_path)`，選完自動填入 Entry 並儲存
- 預設值：專案根目錄下的 `downloads/`（絕對路徑，啟動時計算）

---

## 設定視窗變更

在現有 Notebook 加「下載」tab：

```
⚙ 設定
├── 外觀   ← 現有（主題選擇）
└── 下載   ← 新增
    重試次數：  [3 ↕]   次   (Spinbox, 範圍 1–10)
    重試間隔：  [2 ↕]   秒   (Spinbox, 範圍 1–30)
```

**行為：**
- 開啟時從 config 讀取當前值填入 Spinbox
- 「套用」：儲存至 config，同步更新 `src/config.py` 的 module-level 變數 `RETRY_COUNT` / `RETRY_DELAY`
- 「取消」：不儲存，關閉視窗

---

## Config 結構（`.tool_config.json`）

```json
{
  "theme": "light",
  "output_dir": "C:\\Users\\CTH\\Downloads\\novels",
  "retry_count": 3,
  "retry_delay": 2
}
```

新增 key：`output_dir`、`retry_count`、`retry_delay`  
舊有 config（只有 `theme`）向後相容，缺少的 key 使用預設值。

---

## 改動範圍

| 檔案 | 改動 |
|------|------|
| `src/main.py` | `_build_ui()`：frame_url 加下載至那行；`_open_settings()`：加下載 tab；`_on_download()` / `_on_retry()`：output_dir 改從 config 讀取；新增 `_get_output_dir()` 輔助方法 |
| `src/config.py` | `RETRY_COUNT` / `RETRY_DELAY` 保留作 fallback 預設值；main.py 啟動時若 config 有值則覆寫 module-level 變數 |
| `src/downloader.py` | 不動（output_dir 已是參數傳入） |
| `src/scraper.py` | 不動 |

---

## 不在本次範圍

- 下載資料夾不在設定視窗內顯示（只在主 UI）
- 自動轉繁體開關（TODO #1，留待下次）
- 路徑不存在時不自動建立（使用者自己決定，下載時再 `os.makedirs`）
