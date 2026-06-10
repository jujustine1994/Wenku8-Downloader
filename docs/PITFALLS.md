# PITFALLS

## P1: 網站返回 403
- **問題**：requests 未設 User-Agent 時 wenku8.net 返回 403
- **解法**：在 config.py 的 HEADERS 設定完整 Chrome User-Agent + Referer
- **禁止**：不帶 headers 直接 requests.get

## P2: launcher.ps1 必須有 UTF-8 BOM
- **問題**：PS1 無 BOM 時中文訊息亂碼或語法錯誤閃退
- **解法**：Write 工具建立 PS1 後立即執行：
  `$c = Get-Content 'launcher.ps1' -Raw -Encoding UTF8; [System.IO.File]::WriteAllText((Resolve-Path 'launcher.ps1'), $c, [System.Text.UTF8Encoding]::new($true))`
- **禁止**：用 Set-Content / Out-File 寫 PS1（預設 UTF-16）

## P3: BAT 路徑不可含中文
- **問題**：BAT 用 CMD CP950 讀取，路徑含中文會亂碼導致無法呼叫 PS1
- **解法**：launcher.ps1 統一用英文命名，BAT 只含兩行

## P4: wenku8 HTML 結構變動
- **問題**：parse_volumes 依賴 colspan=1 的 td 當卷標題，若網站改版結構可能失效
- **解法**：失效時檢查卷標題行的 HTML，調整 scraper.py 的偵測邏輯
- **注意**：測試用的 SAMPLE_HTML 要同步更新
