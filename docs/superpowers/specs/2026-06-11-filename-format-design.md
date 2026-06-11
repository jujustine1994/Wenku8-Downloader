# 設計規格：檔案命名格式客製化

日期：2026-06-11  
狀態：已核准

---

## 需求摘要

讓使用者可以在設定視窗自訂下載檔案的命名格式，包含三個維度：
- 序號格式（零補位 / 純數字 / 不顯示）
- 是否在檔名中包含書名
- 各段之間的分隔符號（自由輸入）

---

## 架構設計

### 1. config.json 新增欄位

| 欄位 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `filename_index` | string | `"padded"` | `"padded"` = 零補位（01）、`"plain"` = 純數字（1）、`"none"` = 不顯示 |
| `filename_book_name` | bool | `true` | 檔名是否包含書名 |
| `filename_separator` | string | `" "` | 各段之間的分隔符號（預設空格） |

沿用現有 `_load_config` / `_save_config`，無需改動讀寫邏輯。

---

### 2. `downloader.py` — `build_filepath` 與 `run_download_all`

**`build_filepath` 新增三個關鍵字參數（預設值維持現行行為）：**

```python
def build_filepath(
    output_dir: str, book_name: str, volume_index: int,
    volume_name: str, total: int,
    index_fmt: str = "padded",
    include_book_name: bool = True,
    separator: str = " ",
) -> str:
```

**命名邏輯：**
1. 依 `index_fmt` 產生序號段：`padded` → 零補位字串、`plain` → 無補位字串、`none` → 空字串
2. 依 `include_book_name` 決定是否加入書名段
3. 用 `separator` 串接非空的段落
4. 子資料夾維持 `output_dir/書名/`（不受命名設定影響）

**範例輸出：**
- `padded / True / " "` → `01 書名 第一卷.txt`（現行預設）
- `plain / False / "_"` → `1_第一卷.txt`
- `none / True / "-"` → `書名-第一卷.txt`
- `none / False / " "` → `第一卷.txt`

**`run_download_all` 同步新增三個對應參數，透傳給 `build_filepath`：**

```python
def run_download_all(
    aid, book_name, volumes, output_dir, msg_queue,
    retry_count=RETRY_COUNT, retry_delay=RETRY_DELAY,
    index_fmt="padded", include_book_name=True, separator=" ",
) -> None:
```

---

### 3. `main.py` — Settings 視窗「命名」tab

在現有設定視窗（外觀 / 下載）加入第三個 tab「命名」：

```
┌─ 命名 ────────────────────────────────┐
│ 序號格式                               │
│   ● 零補位（01, 02…）                  │
│   ○ 純數字（1, 2…）                    │
│   ○ 不顯示                             │
│                                        │
│ ☑ 檔名含書名                           │
│                                        │
│ 分隔符號：[   ] （空白 = 空格）          │
│                                        │
│ 預覽：01 書名 第一卷.txt                │
└────────────────────────────────────────┘
```

- 預覽用固定範例值（書名=「書名」、卷名=「第一卷」、卷數=10），三個控件 `trace_add` 即時更新
- 「空白 = 空格」提示讓使用者知道留空等同空格
- 套用時呼叫 `_save_config` 存入 config.json，並更新 App 的三個屬性

---

### 4. `App` 類別屬性

初始化時從 config 讀入，加入三個屬性：

```python
self._fname_index = cfg.get("filename_index", "padded")
self._fname_book_name = bool(cfg.get("filename_book_name", True))
self._fname_separator = cfg.get("filename_separator", " ")
```

`_on_download` 與 `_on_retry` 呼叫 `run_download_all` 時帶入這三個值。

---

## 不在本次範圍內

- 子資料夾結構客製化（仍固定為 `書名/` 子資料夾）
- 正式卷 vs 外傳識別（TODO #3）
- 命名衝突自動處理（重複檔名覆蓋，維持現行行為）
