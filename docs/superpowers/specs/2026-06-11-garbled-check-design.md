# 設計規格：亂碼檢查與修復

日期：2026-06-11
狀態：已核准

---

## 需求摘要

下載完成後驗證 TXT 內容是否有亂碼（encoding mismatch），在記錄區顯示 ⚠️ 警告，並提供「修復亂碼 N 卷」按鈕讓使用者重新下載並自動換編碼修復。

---

## 架構設計

### 1. 亂碼偵測：`check_garbled(filepath)` — 新增至 `downloader.py`

```python
def check_garbled(filepath: str) -> bool:
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    return "�" in content
```

- `�`（Unicode replacement character）是 `errors="replace"` 解碼失敗的直接產物
- 任何一個 `�` = 亂碼，無最低比例門檻
- 在 `run_download_all` 中，`download_volume` 成功後立即呼叫此函式

---

### 2. 修復：`repair_volume(aid, vid, filepath)` — 新增至 `downloader.py`

1. 用 `charset=utf-8` 下載 raw bytes → decode UTF-8 → 數 `�`
2. 若 `�` > 0：改用 `charset=gbk` 下載 → decode GBK
3. 挑 `�` 少的那個版本 → 轉繁體（`convert_to_traditional`） → 覆寫原檔
4. 回傳 `bool`（是否還有 `�`）

```python
def repair_volume(aid: str, vid: int, filepath: str,
                  retry_count: int = RETRY_COUNT,
                  retry_delay: float = RETRY_DELAY) -> bool:
    ...
```

---

### 3. `run_download_all` 流程變更

新增參數：無（行為變更是內部的）。

新增回傳訊息類型：
- 下載成功但偵測到亂碼：`("log", "warn", index_str, vol_name, "偵測到亂碼")`
- `done` 訊息加第四欄位：`("done", success_count, fail_volumes, garbled_volumes)`

流程：
```
download_volume 成功
  → check_garbled(filepath)
    → 有 � → ("log", "warn", ...) + 加入 garbled_volumes
    → 無 � → ("log", "ok", ...)（現有行為）
```

`garbled_volumes` 與 `fail_volumes` 格式相同（`list[dict]`，每個 dict 含 `index`, `name`, `vid`）。

> ⚠️ **Breaking change**：`done` 訊息從 3-tuple 改為 4-tuple。`_poll_queue` 的 `"done"` handler 必須同步更新為 `_, success_count, fail_volumes, garbled_volumes = msg`。

---

### 4. 新增 `run_repair_all(aid, book_name, garbled_volumes, output_dir, msg_queue, ...)`

與 `run_download_all` 結構相同，但呼叫 `repair_volume` 而非 `download_volume`：
- 修復成功（無 `�`）→ `("log", "ok", ...)`
- 修復後仍有 `�` → `("log", "warn", ...)`（留在 garbled list，按鈕繼續亮）
- 修復失敗（網路錯誤）→ `("log", "fail", ...)`（加入 fail_volumes）
- 完成訊息：`("done", success_count, fail_volumes, garbled_volumes)`

---

### 5. UI 變更（`main.py`）

**記錄區**：在 `_poll_queue` 的 `"log"` handler 加入 `"warn"` 分支：
```python
icon = "✅" if status == "ok" else ("⚠️" if status == "warn" else "❌")
```

**按鈕列**：新增 `btn_repair`，位置在 `btn_retry` 左邊：
```
全選 | 全不選 | …… | 修復亂碼 N 卷 | 重試失敗 N 卷 | 下載選取
```

`btn_repair` 行為：
- 預設 disabled
- `done` 訊息有 `garbled_volumes` → `state="normal"`, `text=f"修復亂碼 {n} 卷"`
- 點擊 → `messagebox.askokcancel("亂碼修復", "以下卷偵測到亂碼：\n{vol_names}\n\n嘗試換編碼修復？")`
- 確認後 → 背景 thread 執行 `run_repair_all`，使用與 `_on_retry` 相同的 lock 模式

**`App` 新增屬性**：
```python
self._garbled_volumes: list = []
```

**`done` 訊息 handler 變更**：
```python
elif kind == "done":
    _, success_count, fail_volumes, garbled_volumes = msg
    ...
    if garbled_volumes:
        n = len(garbled_volumes)
        self.btn_repair.config(state="normal", text=f"修復亂碼 {n} 卷")
    else:
        self.btn_repair.config(state="disabled", text="修復亂碼")
```

---

## 不在本次範圍內

- 修復時嘗試 UTF-8 以外和 GBK 以外的其他編碼（Big5 等）
- 下載時靜默自動換編碼（使用者不知情）
- 亂碼比例閾值（任何 `�` 都算亂碼）
