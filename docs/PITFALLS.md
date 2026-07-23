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

## P5: wenku8 下載 API 的 charset 參數不可信
- **問題**：`dl.wenku8.com/packtxt.php` 的 `charset` query 參數名稱不能反映實際回傳的編碼——實測 `charset=utf-8` 實際回傳 UTF-16 LE bytes（帶 BOM），`charset=big5` 實際回傳 UTF-8 bytes（帶 BOM）。這代表無法靠切換 `charset` 參數的值來讓 API 老實回傳「你要求的」編碼內容
- **解法**：一律先偵測 BOM 決定實際解碼方式（`_decode_response`），不要相信 `charset` 參數名稱；`_fetch_best_text` 只在 utf-8 結果含亂碼時額外嘗試 `charset=gbk` 做比對（這是目前唯一驗證過有意義的候選組合）
- **禁止**：不要為了「增加編碼候選」而對這個 API 加更多不同的 `charset` 值去打（例如 `charset=big5`）——已驗證這類請求不會取得跟其他候選不同的實際內容，只會浪費一次網路請求，對修復亂碼沒有幫助
