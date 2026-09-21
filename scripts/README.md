# scripts/ — 輔助腳本索引

**規則**：不可刪除本資料夾下的任何腳本。若冗餘或過時，在下表標註 `(停用)`，保留檔案本體。

| 腳本 | 用途 | 呼叫方式 |
|---|---|---|
| `check_update.ps1` | 檢查 / 安裝 GitHub 上的程式碼更新，供設定分頁「版本更新」按鈕呼叫。`-DryRun` 只檢查不動檔案，只在 stdout 印一行 JSON | `powershell -File scripts\check_update.ps1 [-DryRun]`（Python 端由 `src\update_checker.py` 呼叫） |
| `gui_acceptance.py` | GUI 互動路徑驗收（**需要網路、會下載檔案**）。用程式驅動真正的對話框與按鈕 callback，驗「已有 N 卷」提示、「更新」六組分類視窗、單卷網址載入共 23 項。驗不到視覺排版，不能取代人工驗收。有 FAIL 時 exit 1 | `python scripts\gui_acceptance.py --aid 1861 --out "<測試資料夾>" [--setup 10]` |

> `gui_acceptance.py` 刻意不放進 `tests/`：它要連網抓真實目錄、會下載檔案到磁碟，
> 而 `pytest` 那套是純本地毫秒級的單元測試，混進來會讓日常開發變慢又不穩。
