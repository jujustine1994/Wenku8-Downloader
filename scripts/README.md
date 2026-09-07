# scripts/ — 輔助腳本索引

**規則**：不可刪除本資料夾下的任何腳本。若冗餘或過時，在下表標註 `(停用)`，保留檔案本體。

| 腳本 | 用途 | 呼叫方式 |
|---|---|---|
| `check_update.ps1` | 檢查 / 安裝 GitHub 上的程式碼更新，供設定分頁「版本更新」按鈕呼叫。`-DryRun` 只檢查不動檔案，只在 stdout 印一行 JSON | `powershell -File scripts\check_update.ps1 [-DryRun]`（Python 端由 `src\update_checker.py` 呼叫） |
