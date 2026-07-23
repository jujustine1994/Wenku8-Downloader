# 下載完自動接續修復 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 下載完成後，若有失敗/亂碼卷，程式自動接續觸發修復流程（不用使用者手動按「重試/修復」），並在有限/無限重試兩種模式下都有明確的停損機制，避免真的下載不到的卷讓程式無限空轉。

**Architecture:** `src/downloader.py` 的 `_fetch_bytes`/`_fetch_best_text`/`repair_volume`/`run_repair_all` 新增 `max_attempts` 參數，讓無限重試模式在自動流程中也能有界地放棄。`src/main.py` 新增 `_dispatch_repair()` 共用派工方法、`_start_auto_repair()` 觸發方法，以及 `self._auto_repair_active`/`self._auto_round` 狀態，在 `"done"` 訊息 handler 裡串接自動修復鏈（有限重試模式最多 3 輪，無限重試模式 1 輪但單一編碼嘗試上限 50 次）。另外在 `docs/PITFALLS.md` 補一條記錄，說明為何不採用「下載端加 Big5 候選」。

**Tech Stack:** Python 3.10+, tkinter, pytest

## Global Constraints

- 向下相容：`max_attempts` 一律有預設值 `None`（不限制），既有呼叫端（`download_volume`/`run_download_all`）不用改，行為不變
- `max_attempts` 只在自動修復流程內部使用；使用者手動點「重試/修復」（`_on_recover()`）一律不傳這個參數，維持現有的真無限重試行為
- 有限重試模式：自動修復最多 `AUTO_REPAIR_ROUND_LIMIT = 3` 輪
- 無限重試模式：自動修復只跑 1 輪，`AUTO_REPAIR_MAX_ATTEMPTS = 50`（單一編碼嘗試次數上限）
- 「掃描既有檔案」按鈕行為不變（掃描只補清單，不自動觸發修復）
- 被自動流程放棄的卷不會從 `self._recovery_volumes` 消失，使用者隨時可手動再點「重試/修復」

---

## 檔案異動總覽

| 檔案 | 動作 |
|---|---|
| `src/downloader.py` | `_fetch_bytes`/`_fetch_best_text`/`repair_volume`/`run_repair_all` 新增 `max_attempts` 參數 |
| `tests/test_downloader.py` | 新增測試 |
| `src/main.py` | 新增 `_dispatch_repair()`、`_start_auto_repair()`；新增狀態欄位；`"done"` handler 串接自動鏈；`_on_recover()` 重置自動狀態 |
| `docs/PITFALLS.md` | 新增 P5 條目 |
| `docs/CHANGELOG.md` | 記錄本次功能 |

---

### Task 1: `_fetch_bytes` 新增 `max_attempts` 參數

**Files:**
- Modify: `src/downloader.py:20-48`
- Test: `tests/test_downloader.py`

**Interfaces:**
- Consumes: 無
- Produces: `_fetch_bytes(aid, vid, charset, retry_count, retry_delay, skip_event=None, max_attempts=None) -> bytes | None`——Task 2 的 `_fetch_best_text` 會呼叫這個新簽名

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_downloader.py` 尾端加入（`import` 區塊不用改，測試直接用 `patch("src.downloader._get_session", ...)` 既有模式）：

```python
def test_fetch_bytes_max_attempts_gives_up_in_infinite_mode(tmp_path):
    """retry_count<=0（無限模式）時，max_attempts 到了也要放棄回傳 None"""
    from src.downloader import _fetch_bytes
    session = MagicMock()
    session.get.side_effect = Exception("network error")
    with patch("src.downloader._get_session", return_value=session), \
         patch("src.downloader.time.sleep"):
        result = _fetch_bytes("1", 99, "utf-8", retry_count=0, retry_delay=0, max_attempts=3)
    assert result is None
    assert session.get.call_count == 3


def test_fetch_bytes_max_attempts_none_means_unbounded(tmp_path):
    """max_attempts 為 None（預設）時，無限模式維持原本一直重試的行為（不會被提早放棄）"""
    from src.downloader import _fetch_bytes
    session = MagicMock()
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 10:
            raise Exception("network error")
        return _ok_resp()

    session.get.side_effect = side_effect
    with patch("src.downloader._get_session", return_value=session), \
         patch("src.downloader.time.sleep"):
        result = _fetch_bytes("1", 99, "utf-8", retry_count=0, retry_delay=0)
    assert result == CONTENT
    assert call_count == 10
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest tests/test_downloader.py -k max_attempts -v`
Expected: FAIL（`_fetch_bytes()` 目前沒有 `max_attempts` 參數，`TypeError: unexpected keyword argument`）

- [ ] **Step 3: 修改 `_fetch_bytes`**

把 `src/downloader.py:20-48`：

```python
def _fetch_bytes(aid: str, vid: int, charset: str,
                 retry_count: int, retry_delay: float,
                 skip_event=None) -> bytes | None:
    """retry_count <= 0 表示無限重試，直到成功或 skip_event 被觸發。"""
    url = f"{DOWNLOAD_BASE_URL}?aid={aid}&vid={vid}&charset={charset}"
    infinite = retry_count <= 0
    attempt = 0
    while True:
        attempt += 1
        if skip_event and skip_event.is_set():
            return None
        resp = None
        try:
            resp = _get_session().get(url, impersonate="chrome120", timeout=30)
            resp.raise_for_status()
            # 回應內容不應是 HTML（< 開頭 = 錯誤頁面）
            if len(resp.content) < 50 or resp.content[:5].strip().startswith(b"<"):
                raise ValueError("Response is HTML error page, not TXT")
            return resp.content
        except Exception as e:
            # 只記類型 + status code + 重試次數，絕不記 url（見 windows-tool.md「錯誤行怎麼寫」）
            status = resp.status_code if resp is not None else _extract_status(e)
            retry_label = "無限次" if infinite else f"{attempt}/{retry_count}"
            _write_log(f"vid={vid} charset={charset} -> {type(e).__name__}: HTTP {status} | 重試 {retry_label}", "ERROR")
            if not infinite and attempt >= retry_count:
                return None
            if skip_event and skip_event.is_set():
                return None
            time.sleep(retry_delay)
```

改成：

```python
def _fetch_bytes(aid: str, vid: int, charset: str,
                 retry_count: int, retry_delay: float,
                 skip_event=None, max_attempts: int | None = None) -> bytes | None:
    """retry_count <= 0 表示無限重試，直到成功或 skip_event 被觸發。
    max_attempts 有設定時，即使無限重試模式也會在達到次數上限後放棄
    （自動修復流程用來避免真的下載不到的卷讓程式無限空轉；手動操作不傳這個參數）。"""
    url = f"{DOWNLOAD_BASE_URL}?aid={aid}&vid={vid}&charset={charset}"
    infinite = retry_count <= 0
    attempt = 0
    while True:
        attempt += 1
        if skip_event and skip_event.is_set():
            return None
        resp = None
        try:
            resp = _get_session().get(url, impersonate="chrome120", timeout=30)
            resp.raise_for_status()
            # 回應內容不應是 HTML（< 開頭 = 錯誤頁面）
            if len(resp.content) < 50 or resp.content[:5].strip().startswith(b"<"):
                raise ValueError("Response is HTML error page, not TXT")
            return resp.content
        except Exception as e:
            # 只記類型 + status code + 重試次數，絕不記 url（見 windows-tool.md「錯誤行怎麼寫」）
            status = resp.status_code if resp is not None else _extract_status(e)
            retry_label = "無限次" if infinite else f"{attempt}/{retry_count}"
            _write_log(f"vid={vid} charset={charset} -> {type(e).__name__}: HTTP {status} | 重試 {retry_label}", "ERROR")
            if not infinite and attempt >= retry_count:
                return None
            if max_attempts is not None and attempt >= max_attempts:
                return None
            if skip_event and skip_event.is_set():
                return None
            time.sleep(retry_delay)
```

- [ ] **Step 4: 執行測試確認通過**

Run: `pytest tests/test_downloader.py -k max_attempts -v`
Expected: PASS（2 個新測試）

- [ ] **Step 5: 跑全套 downloader 測試確認沒有回歸**

Run: `pytest tests/test_downloader.py -v`
Expected: PASS（全部通過）

- [ ] **Step 6: Commit**

```bash
git add src/downloader.py tests/test_downloader.py
git commit -m "feat: _fetch_bytes 新增 max_attempts，無限重試模式下也能有界放棄"
```

---

### Task 2: `_fetch_best_text`／`repair_volume`／`run_repair_all` 透傳 `max_attempts`

**Files:**
- Modify: `src/downloader.py:66-83`（`_fetch_best_text`）、`src/downloader.py:113-162`（`repair_volume`）、`src/downloader.py:268-326`（`run_repair_all`）
- Test: `tests/test_downloader.py`

**Interfaces:**
- Consumes: `_fetch_bytes(aid, vid, charset, retry_count, retry_delay, skip_event=None, max_attempts=None) -> bytes | None`（Task 1）
- Produces: `_fetch_best_text(aid, vid, retry_count, retry_delay, skip_event=None, max_attempts=None) -> str | None`；`repair_volume(aid, vid, filepath, retry_count=RETRY_COUNT, retry_delay=RETRY_DELAY, skip_event=None, max_attempts=None) -> bool | None`；`run_repair_all(aid, book_name, volumes, output_dir, msg_queue, retry_count=RETRY_COUNT, retry_delay=RETRY_DELAY, index_fmt="padded", include_book_name=True, separator=" ", skip_event=None, max_attempts=None) -> None`——Task 4 的 `main.py` `_dispatch_repair()` 會呼叫 `run_repair_all` 並視情況傳入 `max_attempts`

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_downloader.py` 尾端加入：

```python
def test_repair_volume_infinite_mode_gives_up_with_max_attempts(tmp_path):
    """無限重試模式 + max_attempts 設定時，repair_volume 的外層停滯偵測要生效，不會無限迴圈"""
    session = MagicMock()
    session.get.side_effect = Exception("network error")
    fp = str(tmp_path / "書名" / "vol.txt")
    os.makedirs(os.path.dirname(fp), exist_ok=True)

    with patch("src.downloader._get_session", return_value=session), \
         patch("src.downloader.time.sleep"):
        result = repair_volume("1", 99, fp, retry_count=0, retry_delay=0, max_attempts=2)

    assert result is None  # 從未成功取得任何內容


def test_repair_volume_infinite_mode_without_max_attempts_unaffected():
    """max_attempts 為 None（預設）時，無限重試模式的函式簽名/預設值不受影響"""
    sig = inspect.signature(repair_volume)
    assert sig.parameters["max_attempts"].default is None


def test_run_repair_all_passes_max_attempts_through(tmp_path):
    """run_repair_all 收到的 max_attempts 會原封不動傳給每一卷的 repair_volume 呼叫"""
    vol = {"index": 1, "name": "第一卷", "first_cid": 100, "vid": 99}
    q = queue.Queue()
    with patch("src.downloader.repair_volume", return_value=False) as mock_repair:
        run_repair_all("1", "書名", [vol], str(tmp_path), q, max_attempts=50)
    _, kwargs = mock_repair.call_args
    assert mock_repair.call_args[0][3:5] == (RETRY_COUNT, RETRY_DELAY)
    assert mock_repair.call_args.kwargs.get("max_attempts") == 50 or \
           (len(mock_repair.call_args[0]) > 5 and mock_repair.call_args[0][-1] == 50)
```

**注意**：最後一個測試對「`max_attempts` 到底是用位置參數還是關鍵字參數傳給 `repair_volume`」保留彈性判斷（你實作時用關鍵字傳遞會最清楚，測試允許兩種寫法都過）。

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest tests/test_downloader.py -k "max_attempts" -v`
Expected: FAIL（`repair_volume()`/`run_repair_all()` 目前沒有 `max_attempts` 參數）

- [ ] **Step 3: 修改 `_fetch_best_text`**

把 `src/downloader.py:66-83`：

```python
def _fetch_best_text(aid: str, vid: int,
                     retry_count: int, retry_delay: float,
                     skip_event=None) -> str | None:
    """先抓 UTF-8，若含亂碼字元就自動改抓 GBK 版本並取亂碼較少者。"""
    utf8_bytes = _fetch_bytes(aid, vid, "utf-8", retry_count, retry_delay, skip_event)
    if utf8_bytes is None:
        return None
    utf8_text = _decode_response(utf8_bytes, "utf-8")

    if "�" not in utf8_text or (skip_event and skip_event.is_set()):
        return utf8_text

    gbk_bytes = _fetch_bytes(aid, vid, "gbk", retry_count, retry_delay, skip_event)
    if gbk_bytes is not None:
        gbk_text = _decode_response(gbk_bytes, "gbk")
        if gbk_text.count("�") < utf8_text.count("�"):
            return gbk_text
    return utf8_text
```

改成：

```python
def _fetch_best_text(aid: str, vid: int,
                     retry_count: int, retry_delay: float,
                     skip_event=None, max_attempts: int | None = None) -> str | None:
    """先抓 UTF-8，若含亂碼字元就自動改抓 GBK 版本並取亂碼較少者。"""
    utf8_bytes = _fetch_bytes(aid, vid, "utf-8", retry_count, retry_delay, skip_event, max_attempts)
    if utf8_bytes is None:
        return None
    utf8_text = _decode_response(utf8_bytes, "utf-8")

    if "�" not in utf8_text or (skip_event and skip_event.is_set()):
        return utf8_text

    gbk_bytes = _fetch_bytes(aid, vid, "gbk", retry_count, retry_delay, skip_event, max_attempts)
    if gbk_bytes is not None:
        gbk_text = _decode_response(gbk_bytes, "gbk")
        if gbk_text.count("�") < utf8_text.count("�"):
            return gbk_text
    return utf8_text
```

- [ ] **Step 4: 修改 `repair_volume`**

把 `src/downloader.py:113-116`：

```python
def repair_volume(aid: str, vid: int, filepath: str,
                  retry_count: int = RETRY_COUNT,
                  retry_delay: float = RETRY_DELAY,
                  skip_event=None) -> bool | None:
```

改成：

```python
def repair_volume(aid: str, vid: int, filepath: str,
                  retry_count: int = RETRY_COUNT,
                  retry_delay: float = RETRY_DELAY,
                  skip_event=None, max_attempts: int | None = None) -> bool | None:
```

把 `src/downloader.py:135`：

```python
        text = _fetch_best_text(aid, vid, retry_count, retry_delay, skip_event)
```

改成：

```python
        text = _fetch_best_text(aid, vid, retry_count, retry_delay, skip_event, max_attempts)
```

把 `src/downloader.py:150`：

```python
        if not infinite and stale_rounds >= REPAIR_STALE_LIMIT:
            break
```

改成：

```python
        if (not infinite or max_attempts is not None) and stale_rounds >= REPAIR_STALE_LIMIT:
            break
```

- [ ] **Step 5: 修改 `run_repair_all`**

把 `src/downloader.py:268-275`：

```python
def run_repair_all(aid: str, book_name: str, volumes: list[dict],
                   output_dir: str, msg_queue: queue.Queue,
                   retry_count: int = RETRY_COUNT,
                   retry_delay: float = RETRY_DELAY,
                   index_fmt: str = "padded",
                   include_book_name: bool = True,
                   separator: str = " ",
                   skip_event=None) -> None:
```

改成：

```python
def run_repair_all(aid: str, book_name: str, volumes: list[dict],
                   output_dir: str, msg_queue: queue.Queue,
                   retry_count: int = RETRY_COUNT,
                   retry_delay: float = RETRY_DELAY,
                   index_fmt: str = "padded",
                   include_book_name: bool = True,
                   separator: str = " ",
                   skip_event=None, max_attempts: int | None = None) -> None:
```

把 `src/downloader.py:295`：

```python
            result = repair_volume(aid, vol["vid"], filepath, retry_count, retry_delay, skip_event)
```

改成：

```python
            result = repair_volume(aid, vol["vid"], filepath, retry_count, retry_delay,
                                   skip_event, max_attempts)
```

- [ ] **Step 6: 執行測試確認通過**

Run: `pytest tests/test_downloader.py -k max_attempts -v`
Expected: PASS（本 Task 的 3 個新測試 + Task 1 的 2 個都過）

- [ ] **Step 7: 跑全套 downloader 測試確認沒有回歸**

Run: `pytest tests/test_downloader.py -v`
Expected: PASS（全部通過）

- [ ] **Step 8: Commit**

```bash
git add src/downloader.py tests/test_downloader.py
git commit -m "feat: _fetch_best_text/repair_volume/run_repair_all 透傳 max_attempts"
```

---

### Task 3: `docs/PITFALLS.md` 新增 P5 條目

**Files:**
- Modify: `docs/PITFALLS.md`

**Interfaces:**
- Consumes: 無
- Produces: 無（純文件）

- [ ] **Step 1: 加入 P5 條目**

在 `docs/PITFALLS.md` 尾端（P4 之後）加入：

```markdown

## P5: wenku8 下載 API 的 charset 參數不可信
- **問題**：`dl.wenku8.com/packtxt.php` 的 `charset` query 參數名稱不能反映實際回傳的編碼——實測 `charset=utf-8` 實際回傳 UTF-16 LE bytes（帶 BOM），`charset=big5` 實際回傳 UTF-8 bytes（帶 BOM）。這代表無法靠切換 `charset` 參數的值來讓 API 老實回傳「你要求的」編碼內容
- **解法**：一律先偵測 BOM 決定實際解碼方式（`_decode_response`），不要相信 `charset` 參數名稱；`_fetch_best_text` 只在 utf-8 結果含亂碼時額外嘗試 `charset=gbk` 做比對（這是目前唯一驗證過有意義的候選組合）
- **禁止**：不要為了「增加編碼候選」而對這個 API 加更多不同的 `charset` 值去打（例如 `charset=big5`）——已驗證這類請求不會取得跟其他候選不同的實際內容，只會浪費一次網路請求，對修復亂碼沒有幫助
```

- [ ] **Step 2: Commit**

```bash
git add docs/PITFALLS.md
git commit -m "docs: 補 PITFALLS P5，記錄 wenku8 charset 參數不可信、Big5候選無效"
```

---

### Task 4: `main.py` 下載完自動接續修復

**Files:**
- Modify: `src/main.py:112-129`（狀態初始化）、`src/main.py:940-946`（`_reset_book_state`）、`src/main.py:1136-1173`（`_on_download`）、`src/main.py:1175-1208`（`_on_recover` → 抽出 `_dispatch_repair`）、`src/main.py:1348-1390`（`"done"` handler）

**Interfaces:**
- Consumes: `run_repair_all(aid, book_name, volumes, output_dir, msg_queue, retry_count, retry_delay, index_fmt, include_book_name, separator, skip_event=None, max_attempts=None)`（Task 2）
- Produces: `self._dispatch_repair(vols, output_dir, log_label, max_attempts=None)`、`self._start_auto_repair()`、`self._auto_repair_active: bool`、`self._auto_round: int`——本任務內部自用，無其他模組依賴

- [ ] **Step 1: 新增狀態欄位**

把 `src/main.py:127-128`：

```python
        self._last_batch_vids: set = set()
        self._repair_mode = False
```

改成：

```python
        self._last_batch_vids: set = set()
        self._repair_mode = False
        self._auto_repair_active = False
        self._auto_round = 0
```

- [ ] **Step 2: `_reset_book_state()` 加入重置**

把 `src/main.py:940-946`：

```python
    def _reset_book_state(self):
        """清空跟目前這本書相關的狀態：卷列表、待處理清單與對應按鈕。
        載入新書、或 Preview 視窗取消時共用，避免舊書的清單/按鈕狀態殘留到下一本書。"""
        self._recovery_volumes = []
        self._build_checkbox_list([])
        self.btn_download.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
        self.btn_recover.config(state="disabled", text="重試/修復")
        self.btn_manage.config(state="disabled")
        self.btn_scan.config(state="disabled")
```

改成：

```python
    def _reset_book_state(self):
        """清空跟目前這本書相關的狀態：卷列表、待處理清單與對應按鈕。
        載入新書、或 Preview 視窗取消時共用，避免舊書的清單/按鈕狀態殘留到下一本書。"""
        self._recovery_volumes = []
        self._auto_repair_active = False
        self._auto_round = 0
        self._build_checkbox_list([])
        self.btn_download.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
        self.btn_recover.config(state="disabled", text="重試/修復")
        self.btn_manage.config(state="disabled")
        self.btn_scan.config(state="disabled")
```

- [ ] **Step 3: `_on_download()` 開頭重置自動狀態**

把 `src/main.py:1151-1152`：

```python
        self._repair_mode = False
        self._last_batch_vids = {v["vid"] for v in selected}
```

改成：

```python
        self._repair_mode = False
        self._auto_repair_active = False
        self._auto_round = 0
        self._last_batch_vids = {v["vid"] for v in selected}
```

- [ ] **Step 4: 抽出 `_dispatch_repair()` 共用方法，`_on_recover()` 改用它**

把 `src/main.py:1175-1208`：

```python
    def _on_recover(self):
        if not self._recovery_volumes:
            return
        output_dir = self._ensure_output_dir()
        if output_dir is None:
            return
        vols = list(self._recovery_volumes)
        self._recovery_volumes = []
        self._last_batch_vids = {v["vid"] for v in vols}
        self._repair_mode = True
        self._skip_event.clear()
        self.btn_recover.config(state="disabled", text="重試/修復")
        self.btn_manage.config(state="disabled")
        self.btn_download.config(state="disabled")
        self.btn_load.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
        self.btn_scan.config(state="disabled")
        self.btn_skip.config(state="normal")
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"\n── 重試/修復 {len(vols)} 卷 ──\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = len(vols)
        self._set_status(f"處理中... 共 {len(vols)} 卷", "info")
        threading.Thread(
            target=run_repair_all,
            args=(self._aid, self._book_name, vols, output_dir, self.msg_queue,
                  self._retry_count, self._retry_delay,
                  self._fname_index, self._fname_book_name, self._fname_separator),
            kwargs={"skip_event": self._skip_event},
            daemon=True,
        ).start()
```

改成：

```python
    def _on_recover(self):
        if not self._recovery_volumes:
            return
        output_dir = self._ensure_output_dir()
        if output_dir is None:
            return
        vols = list(self._recovery_volumes)
        self._recovery_volumes = []
        self._auto_repair_active = False
        self._dispatch_repair(vols, output_dir, f"重試/修復 {len(vols)} 卷")

    # 有限重試模式下，自動修復整批最多跑幾輪；無限重試模式一律只跑 1 輪
    AUTO_REPAIR_ROUND_LIMIT = 3
    # 無限重試模式下，自動修復流程中單一編碼嘗試的次數上限
    AUTO_REPAIR_MAX_ATTEMPTS = 50

    def _dispatch_repair(self, vols, output_dir, log_label, max_attempts=None):
        """共用的修復執行緒派工，_on_recover()（手動）與自動修復流程都呼叫這個。"""
        self._last_batch_vids = {v["vid"] for v in vols}
        self._repair_mode = True
        self._skip_event.clear()
        self.btn_recover.config(state="disabled", text="重試/修復")
        self.btn_manage.config(state="disabled")
        self.btn_download.config(state="disabled")
        self.btn_load.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
        self.btn_scan.config(state="disabled")
        self.btn_skip.config(state="normal")
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"\n── {log_label} ──\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = len(vols)
        self._set_status(f"處理中... 共 {len(vols)} 卷", "info")
        kwargs = {"skip_event": self._skip_event}
        if max_attempts is not None:
            kwargs["max_attempts"] = max_attempts
        threading.Thread(
            target=run_repair_all,
            args=(self._aid, self._book_name, vols, output_dir, self.msg_queue,
                  self._retry_count, self._retry_delay,
                  self._fname_index, self._fname_book_name, self._fname_separator),
            kwargs=kwargs,
            daemon=True,
        ).start()

    def _start_auto_repair(self):
        """下載完成後若有失敗/亂碼卷，自動觸發修復（不用使用者按按鈕）。"""
        output_dir = self._ensure_output_dir()
        if output_dir is None:
            self._auto_repair_active = False
            return
        vols = list(self._recovery_volumes)
        self._recovery_volumes = []
        self._auto_repair_active = True
        self._auto_round = 1
        infinite = self._retry_count <= 0
        max_attempts = self.AUTO_REPAIR_MAX_ATTEMPTS if infinite else None
        self._dispatch_repair(vols, output_dir, f"自動修復 第1輪 共 {len(vols)} 卷", max_attempts)
```

- [ ] **Step 5: `"done"` handler 串接自動鏈**

把 `src/main.py:1378-1390`：

```python
                    if fail_volumes or garbled_volumes:
                        level = "error" if fail_volumes else "info"
                        parts = []
                        if fail_volumes:
                            parts.append(f"失敗：{', '.join(v['name'] for v in fail_volumes)}")
                        if garbled_volumes:
                            parts.append(f"亂碼：{', '.join(v['name'] for v in garbled_volumes)}")
                        suffix = "，" + "；".join(parts)
                    else:
                        level = "success"
                        suffix = ""
                    prefix = "修復完成" if self._repair_mode else "下載完成"
                    self._set_status(f"{prefix} {success_count}/{total}{suffix}", level)
```

改成：

```python
                    if fail_volumes or garbled_volumes:
                        level = "error" if fail_volumes else "info"
                        parts = []
                        if fail_volumes:
                            parts.append(f"失敗：{', '.join(v['name'] for v in fail_volumes)}")
                        if garbled_volumes:
                            parts.append(f"亂碼：{', '.join(v['name'] for v in garbled_volumes)}")
                        suffix = "，" + "；".join(parts)
                    else:
                        level = "success"
                        suffix = ""
                    prefix = "修復完成" if self._repair_mode else "下載完成"
                    self._set_status(f"{prefix} {success_count}/{total}{suffix}", level)

                    if self._auto_repair_active:
                        infinite = self._retry_count <= 0
                        round_limit = 1 if infinite else self.AUTO_REPAIR_ROUND_LIMIT
                        if recovery_count == 0:
                            self._auto_repair_active = False
                        elif self._auto_round >= round_limit:
                            self._auto_repair_active = False
                            self._set_status(
                                f"自動處理完成，成功 {success_count}/{total} 卷，"
                                f"{recovery_count} 卷需要你手動處理"
                                "（可點「重試/修復」再試）",
                                "error",
                            )
                        else:
                            self._auto_round += 1
                            auto_output_dir = self._ensure_output_dir()
                            if auto_output_dir is None:
                                self._auto_repair_active = False
                            else:
                                next_vols = list(self._recovery_volumes)
                                self._recovery_volumes = []
                                max_attempts = self.AUTO_REPAIR_MAX_ATTEMPTS if infinite else None
                                self._dispatch_repair(
                                    next_vols, auto_output_dir,
                                    f"自動修復 第{self._auto_round}輪 共 {len(next_vols)} 卷",
                                    max_attempts,
                                )
                    elif not self._repair_mode and recovery_count > 0:
                        self._start_auto_repair()
```

- [ ] **Step 6: 語法檢查**

Run: `python -m py_compile src/main.py`
Expected: 無輸出（無語法錯誤）

- [ ] **Step 7: 跑全套測試確認沒有回歸**

Run: `pytest tests/ -v`
Expected: PASS（全部通過）

- [ ] **Step 8: 手動驗證（啟動程式）**

Run: `python -m src.main`（或用現有的 `Wenku8下載器啟動器.bat`）

驗證步驟：
1. 載入一本書、確認分類、下載選取
2. 若這批全部成功（沒有失敗/亂碼卷），確認完成後狀態列顯示一般的「下載完成」訊息，不會誤觸發自動修復
3. 若想刻意測試自動修復鏈，可以斷網後下載幾卷讓它們失敗，確認完成後不用按「重試/修復」，記錄區會自動出現「── 自動修復 第1輪 共 N 卷 ──」，並自動開始重試
4. 確認自動修復跑到輪數上限（有限重試模式 3 輪 / 無限重試模式 1 輪）後，狀態列會顯示「自動處理完成，成功 X/Y 卷，Z 卷需要你手動處理」，且「重試/修復」按鈕仍可再手動點一次
5. 確認手動點「重試/修復」時（不是自動觸發的情境），行為（含無限重試設定）跟改動前一樣，不會被自動鏈邏輯影響

- [ ] **Step 9: Commit**

```bash
git add src/main.py
git commit -m "feat: 下載完自動接續修復，有限/無限重試模式各自有停損機制"
```

---

### Task 5: 更新 CHANGELOG

**Files:**
- Modify: `docs/CHANGELOG.md`

**Interfaces:**
- Consumes: 無
- Produces: 無（純文件）

- [ ] **Step 1: 在「已完成功能」清單補上一行**

在 `docs/CHANGELOG.md` 的「已完成功能」清單最後一行之後加入：

```
- 下載完成若有失敗/亂碼卷，自動接續觸發修復（不用手動按「重試/修復」）；有限重試模式最多自動跑 3 輪，無限重試模式單一編碼嘗試上限 50 次後自動視同跳過；跑到上限後仍有問題的卷會清楚留在待處理清單，狀態列會告知需要手動處理的卷數，使用者隨時可再手動點「重試/修復」
```

- [ ] **Step 2: 加入新版本條目**

在 `docs/CHANGELOG.md` 的「## 更新記錄」標題之後（目前第一條是 v17 的掃描既有檔案功能）插入：

```markdown
### 2026-07-23（v18）
- 新增：下載完成後若有失敗/亂碼卷，自動接續觸發修復流程，不用手動按「重試/修復」
- 新增：自動修復停損機制——有限重試模式最多自動跑 3 輪；無限重試模式因單卷請求設計上不會自然結束，改為單一編碼嘗試次數上限 50 次後視同放棄，只跑 1 輪；跑到上限仍有問題的卷保留在待處理清單，可隨時手動再處理
- 技術：`downloader.py` 的 `_fetch_bytes`/`_fetch_best_text`/`repair_volume`/`run_repair_all` 新增 `max_attempts` 參數（僅自動流程使用，手動操作不受影響）；`main.py` 新增 `_dispatch_repair()`/`_start_auto_repair()`
- 文件：`docs/PITFALLS.md` 新增 P5，記錄 wenku8 下載 API 的 `charset` 參數不可信，Big5 候選已驗證無效因此不採用
```

- [ ] **Step 3: Commit**

```bash
git add docs/CHANGELOG.md
git commit -m "docs: 記錄下載完自動接續修復功能到 CHANGELOG"
```

---

## 自我檢查（實作前）

- **spec 涵蓋度**：spec 的三大部分（自動接續修復／停損機制／PITFALLS 記錄）分別對應 Task 4（自動鏈邏輯）、Task 1+2（`max_attempts` 機制）、Task 3。CHANGELOG 記錄對應 Task 5。
- **型別/簽名一致性**：`max_attempts: int | None = None` 從 Task 1 的 `_fetch_bytes` 一路透傳到 Task 2 的 `_fetch_best_text`/`repair_volume`/`run_repair_all`，再到 Task 4 `main.py` 的 `_dispatch_repair()` 呼叫端，參數名稱與預設值全程一致。
- **手動操作不受影響**：`_on_recover()`（Task 4 Step 4）呼叫 `_dispatch_repair()` 時不傳 `max_attempts`（預設 `None`），確認手動觸發時 `run_repair_all` 收到 `max_attempts=None`，`repair_volume`/`_fetch_bytes` 內部邏輯在 `max_attempts is None` 時完全等同修改前的行為（Task 1/2 的測試也涵蓋了 `max_attempts=None` 時的向下相容）。
