# 設計規格：下載前 Preview + 正式卷/外傳分類編輯

日期：2026-07-08
狀態：已核准

---

## 需求摘要

使用者點「載入」抓完目錄後，先跳出 Preview 視窗，讓系統用既有的 `classify_volume()` 自動判斷每一卷是「正式卷」還是「外傳」，使用者可手動調整分類（含批次選取多列一次改），確認後才把結果帶入現有「下載」tab 的卷列表。正式卷與外傳卷分開編號（外傳卷加「外傳」前綴），穿插存在同一資料夾。

---

## 架構設計

### 1. 分類與編號：`scraper.py` 兩個純函式

拆成兩個獨立函式，因為 Preview 視窗「確認」時要在**使用者手動改過的分類**上重新編號，
不能整個重跑關鍵字分類（否則會蓋掉手動調整的結果）：

```python
def classify_volumes(volumes: list[dict], side_keywords: list[str]) -> list[dict]:
    """為每一卷加上 category（'main'/'side'），用 classify_volume() 判斷。
    回傳新 list（不修改原始輸入），保留原始目錄順序。"""


def resequence_by_category(volumes: list[dict]) -> list[dict]:
    """volumes 每個 dict 必須已有 'category' 欄位（可能是自動判斷、也可能是手動改過的）。
    依 category 分開計算 seq_index（1-based）、seq_total，寫回每個 dict。
    回傳新 list（不修改原始輸入），保留原始目錄順序。"""


def assign_categories_and_sequence(volumes: list[dict], side_keywords: list[str]) -> list[dict]:
    """便利包裝：classify_volumes() 接 resequence_by_category()，Preview 開啟時的預設值用這個。"""
    return resequence_by_category(classify_volumes(volumes, side_keywords))
```

- 每個 volume dict 沿用 `parse_volumes()` 產生的既有欄位（`index`、`name`、`first_cid`、`vid`），額外加上 `category`、`seq_index`、`seq_total`
- 純函式、不觸網，好單元測試
- **Preview 開啟時**呼叫 `assign_categories_and_sequence(volumes, side_keywords)` 取得預設分類
- **Preview 確認時**只呼叫 `resequence_by_category(edited_volumes)`（`edited_volumes` 是每列目前的 category，含手動調整），不再重跑關鍵字分類

### 2. 編號文字共用邏輯：`scraper.format_index_token()`

抽出「數字/前綴怎麼組字串」這段邏輯成獨立函式，讓 `build_filepath`（檔名用）和
`_build_checkbox_list`（畫面顯示用）共用同一份實作，避免兩處各自寫一次、之後改一邊漏改一邊：

```python
def format_index_token(seq_index: int, seq_total: int,
                       index_fmt: str = "padded", index_prefix: str = "") -> str:
    """
    回傳編號文字，例如 padded+prefix="外傳" → "外傳01"；none → ""。
    index_fmt == "none" 時忽略 index_prefix，回傳空字串（維持「不顯示」語意一致）。
    """
```

`downloader.build_filepath()` 新增可選參數 `index_prefix=""`（預設空字串，向下相容，既有呼叫端與測試不用改），內部改呼叫 `format_index_token()` 組出檔名開頭的編號段：

```python
def build_filepath(output_dir, book_name, volume_index, volume_name, total,
                   index_fmt="padded", include_book_name=True, separator=" ",
                   index_prefix="") -> str:
```

### 3. `run_download_all` / `run_repair_all` 改用分類後欄位

原本：
```python
total = len(volumes)
...
filepath = build_filepath(output_dir, book_name, vol["index"], vol["name"], total,
                          index_fmt, include_book_name, separator)
```

改為：
```python
...
for i, vol in enumerate(volumes, 1):
    seq_index = vol.get("seq_index", vol["index"])
    seq_total = vol.get("seq_total", len(volumes))
    prefix = "外傳" if vol.get("category") == "side" else ""
    filepath = build_filepath(output_dir, book_name, seq_index, vol["name"], seq_total,
                              index_fmt, include_book_name, separator,
                              index_prefix=prefix)
```

- 用 `.get()` 保底：沒有 `category`/`seq_index`/`seq_total`（例如既有單元測試直接建構 volumes dict，不經過 Preview 流程）時退回舊行為（`vol["index"]` / `len(volumes)` / 無 prefix），舊測試不用改。

### 4. UI：`main.py` 新增 `_open_preview_dialog()`

**觸發時機**：`catalog_done` 訊息處理時，不直接呼叫 `_build_checkbox_list(volumes)`，改成：
```python
classified = assign_categories_and_sequence(volumes, self._side_keywords)
self._open_preview_dialog(book_name, classified)
```

**視窗內容**（Modal Toplevel，可調整大小）：
```
書名：<書名>　共 N 卷

☐  03  第三卷        [正式卷 ▾]
☐  04  番外篇·SS     [外傳   ▾]
☑  05  第四卷        [正式卷 ▾]
☑  06  第五卷        [正式卷 ▾]
...（可捲動）

[全選] [全不選]      [已選標為正式卷] [已選標為外傳]

              [確認]  [取消]
```

- 每列**只有一個勾選框**，意義是「批次選取」，不是下載選取（避免跟下載 tab 的勾選混淆）
- 每列一個 `ttk.Combobox`（或 Radiobutton 組）顯示/編輯 `category`，預設值取自 `assign_categories_and_sequence()` 的判斷結果
- 「已選標為正式卷」／「已選標為外傳」：把目前勾選（批次選取）的列，其分類下拉選單一次改成對應值
- 「全選」／「全不選」：批次選取勾選框全選/全不選（跟下載 tab 現有的全選/全不選是同名但獨立的另一組狀態，只作用在這個 Preview 視窗）
- 「確認」：讀出每列目前的 `category`，呼叫 `resequence_by_category(edited_volumes)` 算出最終 `seq_index`/`seq_total`，把結果存入 `self._volumes`，接著呼叫既有的 `_build_checkbox_list(self._volumes)` 走原本流程；視窗關閉
- 「取消」或關閉視窗：整個載入作廢，UI 回到「（輸入網址後點「載入」）」的初始狀態，`self._aid`/`self._book_name`/`self._volumes` 清空

### 5. 下載 tab 卷列表顯示同步

`_build_checkbox_list()` 目前顯示 `f"  {str(v['index']).zfill(pad)}  {v['name']}"`，改為用 `vol["seq_index"]`／`vol["seq_total"]`／`vol["category"]`（`.get()` 保底同第 3 節）呼叫 `format_index_token()` 組出編號文字，確保畫面顯示的編號跟實際存檔檔名一致。

---

## 不在本次範圍內

- Preview 視窗內編輯檔名文字本身（只能改分類，不能自由改字）
- 外傳卷分資料夾存放（本次為分別編號、同一資料夾）
- 分類關鍵字以外的識別方式（仍用現有「識別」設定的外傳關鍵字清單）

---

## 測試計畫

- `classify_volumes()`：
  - 含外傳關鍵字的卷名 → category 判為 side，其餘為 main
  - 空 `side_keywords` → 全部歸類為 main（沿用 `classify_volume` 現有行為）
- `resequence_by_category()`：
  - 混合 main/side 的 volumes → 各自從 1 開始編號，互不影響
  - 全部同一 category → seq_index 等同原順序，seq_total 等於卷數
  - 原始順序保留（不重新排序 volumes list）
  - 手動改過的 category（例如全部 main）不會被這個函式改動，只重算編號
- `assign_categories_and_sequence()`：兩者組合行為正確（整合測試，等同 `resequence_by_category(classify_volumes(...))`）
- `format_index_token()`：
  - padded + prefix → `外傳01`；plain + prefix → `外傳1`；none + prefix → `""`
  - 無 prefix 時行為等同目前 `build_filepath` 內建的零補位/純數字邏輯
- `build_filepath()`：
  - `index_prefix="外傳"` + `index_fmt="padded"` → 檔名含 `外傳01`
  - `index_prefix=""`（預設）→ 行為與現有測試完全一致
  - `index_fmt="none"` + 有 `index_prefix` → 不顯示任何編號文字
- `run_download_all` / `run_repair_all`：
  - 傳入含 `category`/`seq_index`/`seq_total` 的 volumes → 檔名正確分開編號
  - 傳入舊格式 volumes（無分類欄位）→ 沿用舊行為，不報錯
