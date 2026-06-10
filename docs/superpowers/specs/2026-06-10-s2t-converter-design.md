# Design Spec: 簡轉繁功能

**Date:** 2026-06-10
**Status:** Approved

---

## 目標

1. 下載時自動將簡體中文轉換為台灣繁體（全自動，無開關）
2. 在主視窗新增「轉換」tab，支援多選現有 TXT 檔案批次轉換

---

## 主視窗結構變動

現有所有 frame 改包進 `ttk.Notebook` 第一個 tab：

```
root
├── ttk.Notebook (row 0, sticky="nsew", expands)
│   ├── tab: "  下載  "  ← 現有 frame_url / frame_volumes / frame_progress / frame_log 搬進來
│   └── tab: "  轉換  "  ← 新 tab
├── ttk.Separator (row 98)
└── status_bar Label (row 99)   ← 兩個 tab 共用
```

`_build_ui()` 重構：
- 建立 `self._notebook = ttk.Notebook(self.root)`，grid 到 row 0
- 所有現有 frame 的 parent 從 `self.root` 改為 `tab_download`（一個 `ttk.Frame`）
- row / column configure 對應改到 `tab_download`
- 新增 `_build_convert_tab(tab_convert)` 方法建立轉換 tab 內容

---

## Feature 1：下載自動轉繁

### 轉換模組

新建 `src/converter.py`：

```python
from opencc import OpenCC
_cc = OpenCC("s2twp")          # 簡體 → 台灣繁體（含詞彙對應）

def convert_to_traditional(text: str) -> str:
    return _cc.convert(text)
```

套件：`opencc-python-reimplemented`，加入 `requirements.txt`。

### downloader.py 整合

`download_volume` 成功寫檔後，立即轉換：

```python
# 原本
with open(filepath, "wb") as f:
    f.write(resp.content)

# downloader.py 頂部加 import：
# from src.converter import convert_to_traditional

# download_volume 內，原本 wb 寫檔改為：
text = resp.content.decode("utf-8", errors="replace")
converted = convert_to_traditional(text)
with open(filepath, "w", encoding="utf-8") as f:
    f.write(converted)
```

無任何 toggle，全自動。

---

## Feature 2：轉換 tab UI

```
┌─ 轉換工具 ───────────────────────────────────────┐
│ 已選 N 個檔案                       [選擇檔案]   │
├──────────────────────────────────────────────────┤
│ (可捲動清單)                                      │
│ C:\...\01 灼眼的夏娜 第一卷.txt           [移除] │
│ C:\...\02 灼眼的夏娜 第二卷.txt           [移除] │
├──────────────────────────────────────────────────┤
│ 輸出：○ 覆蓋原檔   ○ 另存新檔（加 _TC 後綴）    │
│                                    [開始轉換]     │
└──────────────────────────────────────────────────┘
┌─ 記錄 ───────────────────────────────────────────┐
│ (ScrolledText，即時顯示每檔 ✅/❌)                │
└──────────────────────────────────────────────────┘
```

### 行為細節

| 元件 | 行為 |
|------|------|
| [選擇檔案] | `filedialog.askopenfilenames(filetypes=[("TXT", "*.txt")])`，無數量上限，重複路徑自動去重 |
| 清單 | 每行顯示完整路徑 + [移除] 按鈕；可捲動 |
| 已選 N 個檔案 | 即時更新計數 |
| 覆蓋原檔 | 轉換完直接寫回同路徑 |
| 另存新檔 | 同目錄，檔名加 `_TC`：`第一卷.txt` → `第一卷_TC.txt` |
| [開始轉換] | 背景 thread 跑；轉換期間 disable；全部完成後 re-enable |
| 記錄區 | 每檔一行：`✅ 第一卷.txt` 或 `❌ 第一卷.txt（錯誤訊息）` |
| status bar | 轉換完成時更新：`轉換完成 N/M` |

### 轉換 thread 流程

```
_on_convert_start()
  → disable [開始轉換]
  → 清空記錄區
  → 背景 thread: _run_convert_all(files, output_mode, queue)
      for each file:
          convert_to_traditional(text)
          queue.put(("conv_log", ok, filename, detail))
      queue.put(("conv_done", success, fail))
  → _poll_queue 處理 conv_log / conv_done 訊息
```

### Queue 訊息擴充

| 類型 | 格式 | 說明 |
|------|------|------|
| `conv_log` | `("conv_log", ok: bool, filename: str, detail: str)` | 單檔結果 |
| `conv_done` | `("conv_done", success: int, fail: int)` | 全部完成 |

---

## 改動範圍

| 檔案 | 動作 |
|------|------|
| `src/converter.py` | 新建：`convert_to_traditional(text)` |
| `src/downloader.py` | 修改：寫檔後呼叫 `convert_to_traditional` |
| `src/main.py` | 修改：`_build_ui()` 加 Notebook 結構，新增 `_build_convert_tab()`，`_poll_queue` 加 conv_log/conv_done 處理，新增 `_on_convert_start()`、`_run_convert_all()` |
| `requirements.txt` | 修改：加 `opencc-python-reimplemented` |
| `tests/test_converter.py` | 新建：`convert_to_traditional` 單元測試 |
| `tests/test_downloader.py` | 修改：驗證下載後檔案為繁體 |

---

## 不在本次範圍

- 轉換方向切換（目前固定 s2twp）
- 資料夾模式批次轉換
- 進度百分比顯示（僅逐檔 log）
