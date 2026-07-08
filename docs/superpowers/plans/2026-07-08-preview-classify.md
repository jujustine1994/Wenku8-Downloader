# 下載前 Preview + 正式卷/外傳分類編輯 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 載入目錄後跳出 Preview 視窗，讓使用者確認/調整每卷「正式卷」或「外傳」分類（含批次選取多列一次改），確認後才把結果帶入下載 tab 卷列表；正式卷與外傳卷各自獨立編號（外傳加「外傳」前綴）。

**Architecture:** `scraper.py` 新增純函式做分類與編號計算（`classify_volumes` / `resequence_by_category` / `assign_categories_and_sequence` / `format_index_token`）；`downloader.py` 的 `build_filepath` 與 `run_download_all`/`run_repair_all` 改用這些欄位並共用 `format_index_token`；`main.py` 新增 `_open_preview_dialog()` Modal 視窗，插在「載入完成」與「填入卷列表」中間。

**Tech Stack:** Python 3.10+, tkinter, pytest

## Global Constraints

- 向下相容：`build_filepath()` 新參數必須有預設值，既有呼叫端與測試不用改
- 向下相容：`run_download_all`/`run_repair_all` 收到沒有 `category`/`seq_index`/`seq_total` 欄位的 volumes 時（例如既有測試直接構造 dict）要用 `.get()` 退回舊行為，不可拋例外
- 外傳前綴固定寫死中文「外傳」二字，不做成可設定項（本次範圍外）
- 設計依據：`docs/superpowers/specs/2026-07-08-preview-classify-design.md`

---

## File Map

| 動作 | 檔案 |
|------|------|
| Modify | `src/scraper.py` — 新增 `format_index_token`、`classify_volumes`、`resequence_by_category`、`assign_categories_and_sequence` |
| Modify | `src/downloader.py` — `build_filepath` 新增 `index_prefix`；`run_download_all`/`run_repair_all` 改用分類後欄位 |
| Modify | `src/main.py` — import 新函式；`_build_checkbox_list` 改用 `format_index_token`；新增 `_open_preview_dialog`；`catalog_done` handler 改觸發 Preview |
| Modify | `tests/test_scraper.py` — 新增分類/編號相關測試 |
| Modify | `tests/test_downloader.py` — 新增 `index_prefix`、分類欄位相關測試 |
| Modify | `docs/CHANGELOG.md`、`docs/TODO.md` |

---

## Task 1: `format_index_token()`（TDD）

**Files:**
- Modify: `src/scraper.py`
- Test: `tests/test_scraper.py`

**Interfaces:**
- Produces: `format_index_token(seq_index: int, seq_total: int, index_fmt: str = "padded", index_prefix: str = "") -> str`
  - `index_fmt == "none"` → 回傳 `""`（忽略 prefix）
  - `index_fmt == "padded"` → `{prefix}{零補位數字}`，補位寬度 `max(len(str(seq_total)), 2)`
  - `index_fmt == "plain"` → `{prefix}{數字}`，不補零

- [ ] **Step 1: 在 `tests/test_scraper.py` 加入失敗測試**

```python
from src.scraper import format_index_token


def test_format_index_token_padded_no_prefix():
    assert format_index_token(1, 18, "padded", "") == "01"


def test_format_index_token_padded_with_prefix():
    assert format_index_token(1, 5, "padded", "外傳") == "外傳01"


def test_format_index_token_plain_with_prefix():
    assert format_index_token(1, 5, "plain", "外傳") == "外傳1"


def test_format_index_token_none_ignores_prefix():
    assert format_index_token(1, 5, "none", "外傳") == ""


def test_format_index_token_triple_digit_padding():
    assert format_index_token(1, 100, "padded", "") == "001"
```

- [ ] **Step 2: 執行測試，確認全部失敗**

```
venv\Scripts\python -m pytest tests/test_scraper.py -k format_index_token -v
```

Expected: 5 FAILED（ImportError: cannot import name 'format_index_token'）

- [ ] **Step 3: 在 `src/scraper.py` 末尾（`parse_volumes` 函式之後）加入實作**

```python
def format_index_token(seq_index: int, seq_total: int,
                       index_fmt: str = "padded", index_prefix: str = "") -> str:
    """
    組出檔名/畫面顯示共用的編號文字。index_fmt == "none" 時忽略 index_prefix，
    回傳空字串（維持「不顯示」語意一致）。
    """
    if index_fmt == "none":
        return ""
    if index_fmt == "padded":
        pad = max(len(str(seq_total)), 2)
        num = str(seq_index).zfill(pad)
    else:  # "plain"
        num = str(seq_index)
    return f"{index_prefix}{num}"
```

- [ ] **Step 4: 執行測試，確認全過**

```
venv\Scripts\python -m pytest tests/test_scraper.py -v
```

Expected: 全部 PASSED

- [ ] **Step 5: Commit**

```
git add tests/test_scraper.py src/scraper.py
git commit -m "feat: add format_index_token for shared filename/display numbering"
```

---

## Task 2: `classify_volumes()`（TDD）

**Files:**
- Modify: `src/scraper.py`
- Test: `tests/test_scraper.py`

**Interfaces:**
- Consumes: `classify_volume(name: str, side_keywords: list[str]) -> str`（既有函式，見 `src/scraper.py` 現有的 `_MAIN_VOL_RE`/`classify_volume`）
- Produces: `classify_volumes(volumes: list[dict], side_keywords: list[str]) -> list[dict]`
  - 每個 volume dict 沿用輸入既有欄位，新增 `category: "main" | "side"`
  - 回傳新 list（新的 dict 物件），不修改輸入的原始 dict
  - 保留原始順序

- [ ] **Step 1: 在 `tests/test_scraper.py` 加入失敗測試**

```python
from src.scraper import classify_volumes


def test_classify_volumes_detects_side_keyword():
    volumes = [
        {"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99},
        {"index": 2, "name": "番外篇·SS", "first_cid": 200, "vid": 199},
    ]
    result = classify_volumes(volumes, ["番外", "SS"])
    assert result[0]["category"] == "main"
    assert result[1]["category"] == "side"


def test_classify_volumes_empty_keywords_all_main():
    volumes = [{"index": 1, "name": "任何名字", "first_cid": 100, "vid": 99}]
    result = classify_volumes(volumes, [])
    assert result[0]["category"] == "main"


def test_classify_volumes_does_not_mutate_input():
    volumes = [{"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99}]
    classify_volumes(volumes, [])
    assert "category" not in volumes[0]


def test_classify_volumes_preserves_order():
    volumes = [
        {"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99},
        {"index": 2, "name": "第二卷", "first_cid": 200, "vid": 199},
    ]
    result = classify_volumes(volumes, [])
    assert [v["name"] for v in result] == ["第一卷", "第二卷"]
```

- [ ] **Step 2: 執行測試，確認全部失敗**

```
venv\Scripts\python -m pytest tests/test_scraper.py -k classify_volumes -v
```

Expected: 4 FAILED

- [ ] **Step 3: 在 `src/scraper.py` 加入實作（放在 `classify_volume` 函式之後）**

```python
def classify_volumes(volumes: list[dict], side_keywords: list[str]) -> list[dict]:
    """為每一卷加上 category（'main'/'side'），用 classify_volume() 判斷。
    回傳新 list，不修改原始輸入，保留原始順序。"""
    return [
        {**v, "category": classify_volume(v["name"], side_keywords)}
        for v in volumes
    ]
```

- [ ] **Step 4: 執行測試，確認全過**

```
venv\Scripts\python -m pytest tests/test_scraper.py -v
```

Expected: 全部 PASSED

- [ ] **Step 5: Commit**

```
git add tests/test_scraper.py src/scraper.py
git commit -m "feat: add classify_volumes to tag each volume with main/side category"
```

---

## Task 3: `resequence_by_category()`（TDD）

**Files:**
- Modify: `src/scraper.py`
- Test: `tests/test_scraper.py`

**Interfaces:**
- Consumes: volumes 必須每個都已有 `category` 欄位（來自 Task 2 或手動編輯）
- Produces: `resequence_by_category(volumes: list[dict]) -> list[dict]`
  - 每個 volume dict 新增 `seq_index: int`（1-based，同 category 內的順位）、`seq_total: int`（同 category 總數）
  - 回傳新 list，不修改輸入，保留原始順序

- [ ] **Step 1: 在 `tests/test_scraper.py` 加入失敗測試**

```python
from src.scraper import resequence_by_category


def test_resequence_by_category_mixed():
    volumes = [
        {"index": 1, "name": "第一卷", "category": "main"},
        {"index": 2, "name": "番外·SS", "category": "side"},
        {"index": 3, "name": "第二卷", "category": "main"},
    ]
    result = resequence_by_category(volumes)
    assert result[0]["seq_index"] == 1 and result[0]["seq_total"] == 2
    assert result[1]["seq_index"] == 1 and result[1]["seq_total"] == 1
    assert result[2]["seq_index"] == 2 and result[2]["seq_total"] == 2


def test_resequence_by_category_all_same_category():
    volumes = [
        {"index": 1, "name": "第一卷", "category": "main"},
        {"index": 2, "name": "第二卷", "category": "main"},
    ]
    result = resequence_by_category(volumes)
    assert [v["seq_index"] for v in result] == [1, 2]
    assert all(v["seq_total"] == 2 for v in result)


def test_resequence_by_category_preserves_order():
    volumes = [
        {"index": 1, "name": "A", "category": "side"},
        {"index": 2, "name": "B", "category": "main"},
    ]
    result = resequence_by_category(volumes)
    assert [v["name"] for v in result] == ["A", "B"]


def test_resequence_by_category_does_not_change_category():
    volumes = [{"index": 1, "name": "第一卷", "category": "main"}]
    result = resequence_by_category(volumes)
    assert result[0]["category"] == "main"
```

- [ ] **Step 2: 執行測試，確認全部失敗**

```
venv\Scripts\python -m pytest tests/test_scraper.py -k resequence_by_category -v
```

Expected: 4 FAILED

- [ ] **Step 3: 在 `src/scraper.py` 加入實作（放在 `classify_volumes` 之後）**

```python
def resequence_by_category(volumes: list[dict]) -> list[dict]:
    """volumes 每個 dict 必須已有 'category' 欄位。依 category 分開計算
    seq_index（1-based）、seq_total，回傳新 list，不修改輸入，保留原始順序。"""
    totals: dict[str, int] = {}
    for v in volumes:
        totals[v["category"]] = totals.get(v["category"], 0) + 1

    counters: dict[str, int] = {}
    result = []
    for v in volumes:
        cat = v["category"]
        counters[cat] = counters.get(cat, 0) + 1
        result.append({**v, "seq_index": counters[cat], "seq_total": totals[cat]})
    return result
```

- [ ] **Step 4: 執行測試，確認全過**

```
venv\Scripts\python -m pytest tests/test_scraper.py -v
```

Expected: 全部 PASSED

- [ ] **Step 5: Commit**

```
git add tests/test_scraper.py src/scraper.py
git commit -m "feat: add resequence_by_category for independent main/side numbering"
```

---

## Task 4: `assign_categories_and_sequence()`（TDD）

**Files:**
- Modify: `src/scraper.py`
- Test: `tests/test_scraper.py`

**Interfaces:**
- Consumes: `classify_volumes`（Task 2）、`resequence_by_category`（Task 3）
- Produces: `assign_categories_and_sequence(volumes: list[dict], side_keywords: list[str]) -> list[dict]`

- [ ] **Step 1: 在 `tests/test_scraper.py` 加入失敗測試**

```python
from src.scraper import assign_categories_and_sequence


def test_assign_categories_and_sequence_combines_both_steps():
    volumes = [
        {"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99},
        {"index": 2, "name": "番外篇·SS", "first_cid": 200, "vid": 199},
        {"index": 3, "name": "第二卷", "first_cid": 300, "vid": 299},
    ]
    result = assign_categories_and_sequence(volumes, ["番外", "SS"])
    assert result[0]["category"] == "main"
    assert result[0]["seq_index"] == 1
    assert result[0]["seq_total"] == 2
    assert result[1]["category"] == "side"
    assert result[1]["seq_index"] == 1
    assert result[1]["seq_total"] == 1
    assert result[2]["category"] == "main"
    assert result[2]["seq_index"] == 2
```

- [ ] **Step 2: 執行測試，確認失敗**

```
venv\Scripts\python -m pytest tests/test_scraper.py -k assign_categories_and_sequence -v
```

Expected: 1 FAILED

- [ ] **Step 3: 在 `src/scraper.py` 加入實作（放在 `resequence_by_category` 之後）**

```python
def assign_categories_and_sequence(volumes: list[dict], side_keywords: list[str]) -> list[dict]:
    """便利包裝：classify_volumes() 接 resequence_by_category()。
    Preview 視窗開啟時的預設分類/編號用這個；Preview 確認時改用 resequence_by_category()
    （避免重跑關鍵字分類蓋掉使用者手動調整的結果）。"""
    return resequence_by_category(classify_volumes(volumes, side_keywords))
```

- [ ] **Step 4: 執行全部 scraper 測試，確認全過**

```
venv\Scripts\python -m pytest tests/test_scraper.py -v
```

Expected: 全部 PASSED

- [ ] **Step 5: Commit**

```
git add tests/test_scraper.py src/scraper.py
git commit -m "feat: add assign_categories_and_sequence convenience wrapper"
```

---

## Task 5: `build_filepath()` 新增 `index_prefix`（TDD）

**Files:**
- Modify: `src/downloader.py`
- Test: `tests/test_downloader.py`

**Interfaces:**
- Consumes: `format_index_token`（Task 1，`from src.scraper import format_index_token`）
- Produces: `build_filepath(..., index_prefix: str = "")` — 向下相容，既有呼叫端不用改

- [ ] **Step 1: 在 `tests/test_downloader.py` 加入失敗測試**

找到現有的 `test_build_filepath_basic` 附近，加入：

```python
def test_build_filepath_with_index_prefix():
    path = build_filepath("downloads", "書名", 1, "番外篇·SS", 5,
                          index_prefix="外傳")
    assert path == os.path.join("downloads", "外傳01 書名 番外篇·SS.txt")


def test_build_filepath_index_prefix_default_empty():
    """不傳 index_prefix 時行為跟現有測試完全一致"""
    path = build_filepath("downloads", "書名", 1, "第一卷", 10)
    assert path == os.path.join("downloads", "01 書名 第一卷.txt")


def test_build_filepath_index_prefix_ignored_when_none_fmt():
    path = build_filepath("downloads", "書名", 1, "番外篇·SS", 5,
                          index_fmt="none", index_prefix="外傳")
    assert path == os.path.join("downloads", "書名 番外篇·SS.txt")
```

- [ ] **Step 2: 執行測試，確認新測試失敗、其餘 build_filepath 測試仍過**

```
venv\Scripts\python -m pytest tests/test_downloader.py -k build_filepath -v
```

Expected: 3 個新測試 FAILED（`unexpected keyword argument 'index_prefix'`），其餘既有 `test_build_filepath_*` 仍 PASSED

- [ ] **Step 3: 修改 `src/downloader.py` 頂部 import，加入 `format_index_token`**

找到：
```python
from src.config import DOWNLOAD_BASE_URL, RETRY_COUNT, RETRY_DELAY
from src.converter import convert_to_traditional
```
改為：
```python
from src.config import DOWNLOAD_BASE_URL, RETRY_COUNT, RETRY_DELAY
from src.converter import convert_to_traditional
from src.scraper import format_index_token
```

- [ ] **Step 4: 完整替換 `build_filepath` 函式**

找到：
```python
def build_filepath(output_dir: str, book_name: str, volume_index: int,
                   volume_name: str, total: int,
                   index_fmt: str = "padded",
                   include_book_name: bool = True,
                   separator: str = " ") -> str:
    pad = max(len(str(total)), 2)
    safe = lambda s: "".join(c for c in s if c not in r'\/:*?"<>|')
    parts = []
    if index_fmt == "padded":
        parts.append(str(volume_index).zfill(pad))
    elif index_fmt == "plain":
        parts.append(str(volume_index))
    if include_book_name:
        parts.append(safe(book_name))
    parts.append(safe(volume_name))
    safe_sep = safe(separator) or " "
    filename = safe_sep.join(parts) + ".txt"
    return os.path.join(output_dir, filename)
```

改為：

```python
def build_filepath(output_dir: str, book_name: str, volume_index: int,
                   volume_name: str, total: int,
                   index_fmt: str = "padded",
                   include_book_name: bool = True,
                   separator: str = " ",
                   index_prefix: str = "") -> str:
    safe = lambda s: "".join(c for c in s if c not in r'\/:*?"<>|')
    parts = []
    token = format_index_token(volume_index, total, index_fmt, index_prefix)
    if token:
        parts.append(safe(token))
    if include_book_name:
        parts.append(safe(book_name))
    parts.append(safe(volume_name))
    safe_sep = safe(separator) or " "
    filename = safe_sep.join(parts) + ".txt"
    return os.path.join(output_dir, filename)
```

- [ ] **Step 5: 執行全部 downloader 測試，確認全過**

```
venv\Scripts\python -m pytest tests/test_downloader.py -v
```

Expected: 全部 PASSED（既有 `test_build_filepath_*` 系列不受影響）

- [ ] **Step 6: Commit**

```
git add tests/test_downloader.py src/downloader.py
git commit -m "feat: add index_prefix param to build_filepath for side-volume numbering"
```

---

## Task 6: `run_download_all` / `run_repair_all` 改用分類後欄位（TDD）

**Files:**
- Modify: `src/downloader.py`
- Test: `tests/test_downloader.py`

**Interfaces:**
- Consumes: `format_index_token`（Task 1，已 import）；volumes dict 可能含 `category`/`seq_index`/`seq_total`（Task 2-4 產生），也可能沒有（舊呼叫端）
- 行為：有分類欄位時依 category 分開編號並加前綴；沒有時 `.get()` 保底退回舊行為（`vol["index"]` 當 seq_index、`len(volumes)` 當 seq_total、無 prefix）

- [ ] **Step 1: 在 `tests/test_downloader.py` 加入失敗測試**

```python
def test_run_download_all_uses_side_prefix(tmp_path):
    """帶 category='side' 的卷，檔名要有「外傳」前綴，且編號跟 main 分開算"""
    session = MagicMock()
    session.get.return_value = _ok_resp()
    volumes = [
        {"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99,
         "category": "main", "seq_index": 1, "seq_total": 1},
        {"index": 2, "name": "番外篇·SS", "first_cid": 200, "vid": 199,
         "category": "side", "seq_index": 1, "seq_total": 1},
    ]
    q = queue.Queue()
    with patch("src.downloader._get_session", return_value=session):
        run_download_all("1", "書名", volumes, str(tmp_path), q)
    main_path = os.path.join(str(tmp_path), "01 書名 第一卷.txt")
    side_path = os.path.join(str(tmp_path), "外傳01 書名 番外篇·SS.txt")
    assert os.path.exists(main_path)
    assert os.path.exists(side_path)


def test_run_download_all_backward_compatible_without_category(tmp_path):
    """volumes 沒有 category/seq_index/seq_total 時沿用舊行為，不報錯"""
    session = MagicMock()
    session.get.return_value = _ok_resp()
    volumes = [{"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99}]
    q = queue.Queue()
    with patch("src.downloader._get_session", return_value=session):
        run_download_all("1", "書名", volumes, str(tmp_path), q)
    expected = os.path.join(str(tmp_path), "01 書名 第一卷.txt")
    assert os.path.exists(expected)
```

- [ ] **Step 2: 執行測試，確認新測試失敗**

```
venv\Scripts\python -m pytest tests/test_downloader.py -k "side_prefix or backward_compatible_without_category" -v
```

Expected: `test_run_download_all_uses_side_prefix` FAILED（找不到外傳前綴的檔案），`test_run_download_all_backward_compatible_without_category` 可能已經 PASSED（因為還沒改邏輯，先確認這個先跑一次是綠的，改完後仍要維持綠）

- [ ] **Step 3: 修改 `run_download_all`**

找到：
```python
    total = len(volumes)
    success = 0
    fail_volumes: list[dict] = []
    garbled_volumes: list[dict] = []
    pad = max(len(str(total)), 2)

    for i, vol in enumerate(volumes, 1):
        msg_queue.put(("progress", i, total, vol["name"]))
        index_str = str(vol["index"]).zfill(pad)
        try:
            filepath = build_filepath(output_dir, book_name, vol["index"], vol["name"], total,
                                      index_fmt, include_book_name, separator)
            ok = download_volume(aid, vol["vid"], filepath, retry_count, retry_delay, skip_event)
```

改為：
```python
    total = len(volumes)
    success = 0
    fail_volumes: list[dict] = []
    garbled_volumes: list[dict] = []

    for i, vol in enumerate(volumes, 1):
        msg_queue.put(("progress", i, total, vol["name"]))
        seq_index = vol.get("seq_index", vol["index"])
        seq_total = vol.get("seq_total", total)
        prefix = "外傳" if vol.get("category") == "side" else ""
        index_str = format_index_token(seq_index, seq_total, "padded", prefix)
        try:
            filepath = build_filepath(output_dir, book_name, seq_index, vol["name"], seq_total,
                                      index_fmt, include_book_name, separator,
                                      index_prefix=prefix)
            ok = download_volume(aid, vol["vid"], filepath, retry_count, retry_delay, skip_event)
```

（下面 `if ok: ... else: ...` 區塊維持不變，只是 `index_str` 現在含分類前綴）

- [ ] **Step 4: 修改 `run_repair_all`（同樣的改法）**

找到：
```python
    total = len(volumes)
    success = 0
    fail_volumes: list[dict] = []
    garbled_volumes: list[dict] = []
    pad = max(len(str(total)), 2)

    for i, vol in enumerate(volumes, 1):
        msg_queue.put(("progress", i, total, vol["name"]))
        index_str = str(vol["index"]).zfill(pad)
        try:
            filepath = build_filepath(output_dir, book_name, vol["index"], vol["name"], total,
                                      index_fmt, include_book_name, separator)
            result = repair_volume(aid, vol["vid"], filepath, retry_count, retry_delay, skip_event)
```

改為：
```python
    total = len(volumes)
    success = 0
    fail_volumes: list[dict] = []
    garbled_volumes: list[dict] = []

    for i, vol in enumerate(volumes, 1):
        msg_queue.put(("progress", i, total, vol["name"]))
        seq_index = vol.get("seq_index", vol["index"])
        seq_total = vol.get("seq_total", total)
        prefix = "外傳" if vol.get("category") == "side" else ""
        index_str = format_index_token(seq_index, seq_total, "padded", prefix)
        try:
            filepath = build_filepath(output_dir, book_name, seq_index, vol["name"], seq_total,
                                      index_fmt, include_book_name, separator,
                                      index_prefix=prefix)
            result = repair_volume(aid, vol["vid"], filepath, retry_count, retry_delay, skip_event)
```

- [ ] **Step 5: 執行全部 downloader 測試，確認全過**

```
venv\Scripts\python -m pytest tests/test_downloader.py -v
```

Expected: 全部 PASSED

- [ ] **Step 6: Commit**

```
git add tests/test_downloader.py src/downloader.py
git commit -m "feat: run_download_all/run_repair_all number main/side volumes independently"
```

---

## Task 7: `main.py` — `_build_checkbox_list` 顯示同步（手動驗證）

**Files:**
- Modify: `src/main.py`

**Interfaces:**
- Consumes: `format_index_token`（Task 1）

這個 task 沒有自動化測試（GUI 顯示），改完後用 Step 3 手動驗證。

- [ ] **Step 1: 修改頂部 import，加入新函式**

找到：
```python
from src.scraper import parse_aid_from_url, fetch_catalog, parse_book_title, parse_volumes
```
改為：
```python
from src.scraper import (
    parse_aid_from_url, fetch_catalog, parse_book_title, parse_volumes,
    assign_categories_and_sequence, resequence_by_category, format_index_token,
)
```

- [ ] **Step 2: 修改 `_build_checkbox_list`**

找到：
```python
    def _build_checkbox_list(self, volumes: list[dict]):
        for w in self._cb_frame.winfo_children():
            w.destroy()
        self._check_vars = []
        pad = max(len(str(len(volumes))), 2)
        for v in volumes:
            var = tk.BooleanVar(value=True)
            self._check_vars.append(var)
            cb = ttk.Checkbutton(
                self._cb_frame,
                text=f"  {str(v['index']).zfill(pad)}  {v['name']}",
                variable=var,
            )
            cb.pack(anchor="w", fill="x", padx=4, pady=1)
        self._check_canvas.yview_moveto(0)
```

改為：
```python
    def _build_checkbox_list(self, volumes: list[dict]):
        for w in self._cb_frame.winfo_children():
            w.destroy()
        self._check_vars = []
        for v in volumes:
            var = tk.BooleanVar(value=True)
            self._check_vars.append(var)
            seq_index = v.get("seq_index", v["index"])
            seq_total = v.get("seq_total", len(volumes))
            prefix = "外傳" if v.get("category") == "side" else ""
            label = format_index_token(seq_index, seq_total, "padded", prefix)
            cb = ttk.Checkbutton(
                self._cb_frame,
                text=f"  {label}  {v['name']}",
                variable=var,
            )
            cb.pack(anchor="w", fill="x", padx=4, pady=1)
        self._check_canvas.yview_moveto(0)
```

- [ ] **Step 3: 執行全部測試（確保沒有語法錯誤/import 錯誤）**

```
venv\Scripts\python -m pytest tests/ -v
venv\Scripts\python -m py_compile src/main.py
```

Expected: 全部 PASSED，compile 無錯誤（這個 task 本身沒有新增測試，這裡是防止 import 打錯字或縮排錯誤）

- [ ] **Step 4: Commit**

```
git add src/main.py
git commit -m "feat: _build_checkbox_list shows category-aware numbering"
```

---

## Task 8: `main.py` — 新增 `_open_preview_dialog()` 並接上 `catalog_done`（手動驗證）

**Files:**
- Modify: `src/main.py`

**Interfaces:**
- Consumes: `assign_categories_and_sequence`、`resequence_by_category`（Task 4）、`self._enable_wheel_scroll`（既有方法）、`self._side_keywords`（既有屬性，設定 tab 的外傳關鍵字清單）、`self._build_checkbox_list`（Task 7 改過的版本）

這個 task 是最大的 UI 改動，沒有自動化測試，Step 5 手動驗證。

- [ ] **Step 1: 修改 `_poll_queue` 的 `"catalog_done"` 分支**

找到：
```python
                if kind == "catalog_done":
                    _, book_name, volumes = msg
                    self._book_name = book_name
                    self._volumes = volumes
                    self.title_label.config(
                        text=f"書名：{book_name}　共 {len(volumes)} 卷"
                    )
                    self._build_checkbox_list(volumes)
                    self.progress_bar.stop()
                    self.progress_bar.config(mode="determinate")
                    self.progress_label.config(text="載入完成，勾選要下載的卷後按「下載選取」")
                    self.btn_load.config(state="normal")
                    self.btn_download.config(state="normal")
                    self.btn_select_all.config(state="normal")
                    self.btn_deselect_all.config(state="normal")
                    self._set_status(
                        f"已載入：{book_name}，共 {len(volumes)} 卷", "success"
                    )
```

改為：
```python
                if kind == "catalog_done":
                    _, book_name, volumes = msg
                    self.progress_bar.stop()
                    self.progress_bar.config(mode="determinate")
                    self.btn_load.config(state="normal")
                    classified = assign_categories_and_sequence(volumes, self._side_keywords)
                    self._open_preview_dialog(book_name, classified)
```

**注意**：`btn_download`/`btn_select_all`/`btn_deselect_all` 這裡不再直接啟用——它們在 `_on_load()` 一開始就已經被設成 `disabled`（既有邏輯不用改），要等 Preview 視窗按下「確認」才會啟用（見 Step 2 的 `_confirm()`）。

- [ ] **Step 2: 在 `_build_checkbox_list` 方法之後（Task 7 修改的方法後面）加入 `_open_preview_dialog`**

```python
    def _open_preview_dialog(self, book_name: str, volumes: list[dict]):
        win = tk.Toplevel(self.root)
        win.title(f"確認分類 - {book_name}")
        win.resizable(True, True)
        win.geometry("480x520")
        win.minsize(360, 300)
        win.grab_set()

        ttk.Label(
            win, text=f"書名：{book_name}　共 {len(volumes)} 卷", font=FB
        ).pack(anchor="w", padx=12, pady=(12, 6))

        list_outer = ttk.Frame(win)
        list_outer.pack(fill="both", expand=True, padx=12)
        list_outer.columnconfigure(0, weight=1)
        list_outer.rowconfigure(0, weight=1)

        canvas = tk.Canvas(list_outer, highlightthickness=0)
        sb = ttk.Scrollbar(list_outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self._enable_wheel_scroll(canvas)

        row_frame = ttk.Frame(canvas)
        row_win = canvas.create_window((0, 0), window=row_frame, anchor="nw")
        row_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(row_win, width=e.width),
        )

        batch_vars: list[tk.BooleanVar] = []
        category_vars: list[tk.StringVar] = []

        for v in volumes:
            row = ttk.Frame(row_frame)
            row.pack(fill="x", padx=4, pady=2)
            bvar = tk.BooleanVar(value=False)
            batch_vars.append(bvar)
            ttk.Checkbutton(row, variable=bvar).pack(side="left")
            ttk.Label(row, text=v["name"], font=F, anchor="w").pack(
                side="left", padx=(4, 8), fill="x", expand=True
            )
            cvar = tk.StringVar(value="正式卷" if v["category"] == "main" else "外傳")
            category_vars.append(cvar)
            ttk.Combobox(
                row, textvariable=cvar, values=["正式卷", "外傳"],
                state="readonly", width=8, font=F
            ).pack(side="right")

        def _select_all_batch(state: bool):
            for bv in batch_vars:
                bv.set(state)

        def _mark_selected(label: str):
            for bv, cv in zip(batch_vars, category_vars):
                if bv.get():
                    cv.set(label)

        btn_row1 = ttk.Frame(win)
        btn_row1.pack(fill="x", padx=12, pady=(8, 0))
        ttk.Button(
            btn_row1, text="全選", command=lambda: _select_all_batch(True), width=8
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            btn_row1, text="全不選", command=lambda: _select_all_batch(False), width=8
        ).pack(side="left")
        ttk.Button(
            btn_row1, text="已選標為正式卷",
            command=lambda: _mark_selected("正式卷"), width=14
        ).pack(side="right", padx=(4, 0))
        ttk.Button(
            btn_row1, text="已選標為外傳",
            command=lambda: _mark_selected("外傳"), width=12
        ).pack(side="right")

        def _confirm():
            edited = [
                {**v, "category": "main" if cv.get() == "正式卷" else "side"}
                for v, cv in zip(volumes, category_vars)
            ]
            final_volumes = resequence_by_category(edited)
            self._book_name = book_name
            self._volumes = final_volumes
            self.title_label.config(
                text=f"書名：{book_name}　共 {len(final_volumes)} 卷"
            )
            self._build_checkbox_list(final_volumes)
            self.progress_label.config(text="載入完成，勾選要下載的卷後按「下載選取」")
            self.btn_download.config(state="normal")
            self.btn_select_all.config(state="normal")
            self.btn_deselect_all.config(state="normal")
            self._set_status(
                f"已載入：{book_name}，共 {len(final_volumes)} 卷", "success"
            )
            win.destroy()

        def _cancel():
            self._aid = None
            self._book_name = None
            self._volumes = []
            self.title_label.config(text="（輸入網址後點「載入」）")
            self.progress_label.config(text="等待中...")
            self._set_status("已取消載入", "info")
            win.destroy()

        btn_row2 = ttk.Frame(win)
        btn_row2.pack(pady=(8, 12))
        ttk.Button(btn_row2, text="確認", command=_confirm, width=10).pack(
            side="left", padx=4, ipady=4
        )
        ttk.Button(btn_row2, text="取消", command=_cancel, width=10).pack(
            side="left", padx=4, ipady=4
        )
        win.protocol("WM_DELETE_WINDOW", _cancel)
```

- [ ] **Step 3: 執行全部測試（確保沒有語法錯誤/import 錯誤）**

```
venv\Scripts\python -m pytest tests/ -v
venv\Scripts\python -m py_compile src/main.py
```

Expected: 全部 PASSED，compile 無錯誤

- [ ] **Step 4: Commit**

```
git add src/main.py
git commit -m "feat: add Preview dialog for classifying volumes before download"
```

- [ ] **Step 5: 手動驗證（無法自動化的 UI 測試）**

```
venv\Scripts\python -m src.main
```

驗證項目：
- 貼一個 wenku8 目錄網址（例如 `https://www.wenku8.net/novel/0/347/index.htm`），按「載入」
- 載入完成後應該跳出「確認分類 - <書名>」視窗，而不是直接顯示卷列表
- 視窗內每一列有：批次選取勾選框、卷名、分類下拉選單（正式卷/外傳）
- 勾選幾列後點「已選標為外傳」，確認這幾列的下拉選單變成「外傳」
- 點「全選」「全不選」確認批次選取勾選框正確全開/全關
- 點「確認」後，Preview 視窗關閉，下載 tab 的卷列表出現，編號格式是「外傳」卷顯示「外傳01」這種前綴、正式卷維持原本零補位數字
- 「下載選取」「全選」「全不選」按鈕變成可點擊
- 重新載入一次，這次點「取消」，確認畫面回到「（輸入網址後點「載入」）」的初始狀態，且沒有任何按鈕異常啟用

---

## Task 9: 文件更新

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TODO.md`

- [ ] **Step 1: 更新 `docs/CHANGELOG.md`**

在「已完成功能」清單末尾加一行：
```
- 載入目錄後跳出 Preview 視窗，確認/調整每卷「正式卷」「外傳」分類（含批次選取多列一次改），確認後才帶入下載 tab；正式卷與外傳卷各自獨立編號，外傳卷檔名加「外傳」前綴
```

在「更新記錄」頂部加入新版本區塊（沿用當天既有版本號序，接續最新一個）：
```markdown
### 2026-07-08（v14）
- 新增：載入目錄後跳出 Preview 視窗，使用者可確認/調整每卷「正式卷」「外傳」分類，支援批次選取多列一次改分類；確認後才帶入下載 tab 卷列表
- 新增：正式卷與外傳卷各自獨立編號（外傳卷檔名加「外傳」前綴），穿插存在同一資料夾；下載 tab 卷列表顯示的編號與實際檔名一致
- 技術：`build_filepath()` 新增 `index_prefix` 參數（向下相容）；`scraper.py` 新增 `classify_volumes`/`resequence_by_category`/`assign_categories_and_sequence`/`format_index_token` 四個可獨立測試的純函式
```

- [ ] **Step 2: 更新 `docs/TODO.md`**

移除已完成的「下載前 Preview + 命名編輯」項目（原第 2 項），保留其餘項目原樣，重新編號。

- [ ] **Step 3: Commit**

```
git add docs/CHANGELOG.md docs/TODO.md
git commit -m "docs: update CHANGELOG and TODO for Preview classify feature (v14)"
```
