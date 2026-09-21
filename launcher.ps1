# Wenku8 Downloader 啟動器

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$host.UI.RawUI.WindowTitle = "Wenku8 Downloader"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# ======================================
# venv 位置（刻意放在專案資料夾外）
# ======================================
# 這個專案在 Documents\Code 底下，而 Google Drive 桌面版正在備份整個
# Documents\Code（2026-09-21 從 root_preference_sqlite.db 的 roots 表確認，
# root_id=4）。venv 跟著被同步會出事：site-packages 底下的目錄被設成唯讀
# → uv 換套件版本時 RemoveDirectory 一律回 ERROR_ACCESS_DENIED
# （os error 5 存取被拒）；另外會生出一堆 "xxx (1).py" 影子檔，套件被同步
# 工具切成兩半（實測 idna 被刪到只剩影子檔，變成 namespace package）。
# Drive 桌面版不支援排除子資料夾，只能整個資料夾勾或不勾，所以改成把 venv
# 放到同步範圍外的集中目錄。詳見 windows-tool.md「venv 位置」。
$VenvPath   = Join-Path $env:USERPROFILE "venvs\Wenku8 Downloader"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"

# ======================================
# 執行紀錄（必加，須放在 trap 之前，閃退才記得到）
# 完整規則見 windows-tool.md「執行紀錄」；範本說明見 windows-tool-templates.md「執行紀錄範本」
# ======================================
$LogFile = Join-Path $ScriptDir "logs\app.log"
New-Item -ItemType Directory -Force (Split-Path $LogFile) | Out-Null
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)   # 不可用 Add-Content -Encoding UTF8，會寫 BOM（地雷十一）

function Write-Log {
    param([string]$Msg, [string]$Level = "INFO")
    $line = "[{0}] [{1,-5}] {2}`r`n" -f (Get-Date -Format "HH:mm:ss"), $Level, $Msg
    try { [System.IO.File]::AppendAllText($LogFile, $line, $Utf8NoBom) } catch {}   # 不持有 handle（地雷十）
}

function Write-LogHeader {
    param([string]$Msg)
    $line = "=== {0} {1} ===`r`n" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Msg
    try { [System.IO.File]::AppendAllText($LogFile, $line, $Utf8NoBom) } catch {}
}

Write-LogHeader "啟動"

# 攔截所有未預期例外，防止視窗直接閃退
trap {
    Write-Log "[CRASH] $($_.Exception.Message) @ 第 $($_.InvocationInfo.ScriptLineNumber) 行" "FATAL"
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Red
    Write-Host "[CRASH] 意外錯誤，程式無法繼續執行" -ForegroundColor Red
    Write-Host ""
    Write-Host "  錯誤訊息：$($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "  發生位置：$($_.InvocationInfo.ScriptLineNumber) 行" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  已記錄至 logs\app.log，請連同此畫面回報給開發者。" -ForegroundColor White
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Red
    Read-Host "按 Enter 關閉"
    exit 1
}

Clear-Host
Write-Host "[INFO] Starting Wenku8 Downloader..." -ForegroundColor Green
Write-Host ""

# ======================================
# [1/2] 檢查 uv
#
# ⚠ 只檢查 uv，不檢查系統 Python——uv 自己就會下載 Python（地雷十二）。
# ======================================
Write-Host "[1/2] 檢查 uv 套件管理工具..." -ForegroundColor Cyan
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Log "找不到 uv，準備安裝" "WARN"
    Write-Host "[WARNING] 找不到 uv，正在安裝..." -ForegroundColor Yellow
    try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" + $env:PATH
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Log "uv 安裝失敗" "ERROR"
        Write-Host "[ERROR] uv 安裝失敗，請關閉視窗後重新點兩下啟動檔再試。" -ForegroundColor Red
        Read-Host "按 Enter 關閉"; exit 1
    }
    $uvVer = uv --version
    Write-Host "[OK] uv 安裝完成。" -ForegroundColor Green
} else {
    $uvVer = uv --version
    Write-Host "[OK] $uvVer 已安裝。" -ForegroundColor Green
}

# ======================================
# [2/2] 檢查虛擬環境
# ======================================
Write-Host "[2/2] 檢查虛擬環境..." -ForegroundColor Cyan
if (-not (Test-Path $VenvPython)) {
    Write-Host ""
    Write-Host "  ============================================" -ForegroundColor Cyan
    Write-Host "    Wenku8 Downloader - 首次安裝說明" -ForegroundColor Cyan
    Write-Host "  ============================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  接下來程式會自動幫你安裝以下東西：" -ForegroundColor White
    Write-Host ""
    Write-Host "    1. Python 虛擬環境（venv）" -ForegroundColor Yellow
    Write-Host "       讓這個工具有獨立乾淨的執行空間，不影響電腦其他程式" -ForegroundColor Gray
    Write-Host ""
    Write-Host "    2. requests" -ForegroundColor Yellow
    Write-Host "       負責連上 wenku8.net 抓取網頁內容" -ForegroundColor Gray
    Write-Host ""
    Write-Host "    3. beautifulsoup4 + lxml" -ForegroundColor Yellow
    Write-Host "       負責解析網頁的目錄結構，找出每一卷的章節" -ForegroundColor Gray
    Write-Host ""
    Write-Host "    4. sv-ttk" -ForegroundColor Yellow
    Write-Host "       讓程式介面套用 Windows 11 風格" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  全程只需要一直按 Enter 同意即可。" -ForegroundColor Green
    Write-Host "  如果有任何疑問，可以把這段說明貼給 AI 詢問。" -ForegroundColor Green
    Write-Host ""
    Write-Host "  ============================================" -ForegroundColor Cyan
    Write-Host ""
    $ans = Read-Host "[WARNING] 找不到虛擬環境，現在建立並安裝套件？[Y/n] - 直接按 Enter 代表同意"
    if ($ans -eq "" -or $ans -ieq "Y") {
        Write-Host "[INFO] 建立虛擬環境中（電腦若沒有 Python 會自動下載，約 20MB）..." -ForegroundColor Gray
        New-Item -ItemType Directory -Force (Split-Path $VenvPath) | Out-Null
        uv venv "$VenvPath" --python 3.13
        if ($LASTEXITCODE -ne 0) {
            Write-Log "建立虛擬環境失敗（uv venv 回傳 $LASTEXITCODE）" "ERROR"
            Write-Host "[ERROR] 建立虛擬環境失敗，多半是下載 Python 時連不上網路。請確認網路連線後重新執行。" -ForegroundColor Red
            Read-Host "按 Enter 關閉"; exit 1
        }
        Write-Host "[INFO] 安裝套件中..." -ForegroundColor Gray
        uv pip install -r requirements.txt --python "$VenvPython"
        if ($LASTEXITCODE -ne 0) {
            Write-Log "套件安裝失敗（uv pip install 回傳 $LASTEXITCODE）" "ERROR"
            Write-Host "[ERROR] 套件安裝失敗，請確認網路連線後重新執行。" -ForegroundColor Red
            Read-Host "按 Enter 關閉"; exit 1
        }
        Write-Host "[OK] 套件安裝完成。" -ForegroundColor Green
    } else {
        Write-Host "已取消。" -ForegroundColor Gray; Read-Host "按 Enter 關閉"; exit 1
    }
} else {
    Write-Host "[OK] 虛擬環境已就緒，檢查套件更新..." -ForegroundColor Green
    # 清理損壞的 dist-info（METADATA 檔遺失時 uv 會拒絕安裝）
    $broken = Get-ChildItem (Join-Path $VenvPath "Lib\site-packages") -Directory -Filter "*dist-info" -ErrorAction SilentlyContinue | Where-Object {
        -not (Test-Path (Join-Path $_.FullName "METADATA"))
    }
    foreach ($dir in $broken) {
        Write-Host "[INFO] 清理損壞的套件資訊：$($dir.Name)" -ForegroundColor Yellow
        Remove-Item -Recurse -Force $dir.FullName
    }
    uv pip install -r requirements.txt --python "$VenvPython" -q
    if ($LASTEXITCODE -ne 0) {
        # uv 刪不掉唯讀目錄：Windows 的 RemoveDirectory 對唯讀目錄一律回
        # ERROR_ACCESS_DENIED，uv 會報 "os error 5 存取被拒"。檔案同步工具
        # （2026-09-21 實測是 Google Drive 在備份 Documents\Code）會把唯讀屬性
        # 加到 site-packages 底下的目錄上，還會留下 "xxx (1).py" 影子檔。
        # 上面那段只清「缺 METADATA 的 dist-info」，擋不到這個，所以改成
        # 失敗才修、修完重試一次：平常一毛錢不花，出事才動作。
        Write-Host "[INFO] 套件更新失敗，清除唯讀屬性與同步殘留檔後重試..." -ForegroundColor Yellow
        $sp = Join-Path $VenvPath "Lib\site-packages"
        Get-ChildItem $sp -Recurse -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Attributes -band [IO.FileAttributes]::ReadOnly } |
            ForEach-Object {
                $_.Attributes = $_.Attributes -band (-bnot [IO.FileAttributes]::ReadOnly)
            }
        Get-ChildItem $sp -Recurse -File -Filter "* (1).*" -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
        uv pip install -r requirements.txt --python "$VenvPython" -q
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[WARN] 套件更新仍失敗，將以現有套件繼續啟動。" -ForegroundColor Yellow
            Write-Log "套件更新失敗（清除唯讀屬性後重試仍失敗）" "WARN"
        }
    }
}

. ".\venv\Scripts\Activate.ps1"

$pyVer = (& ".\venv\Scripts\python.exe" --version 2>&1 | Out-String).Trim()
Write-Log "環境就緒 | $pyVer | $uvVer"

Write-Host ""
Write-Host "[START] 啟動中，請保持此視窗開啟..." -ForegroundColor Green
Write-Host ""

# 主程式執行期間由它自己寫 log，launcher 不寫（避免搶 handle，地雷十）
python -m src.main
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Log "主程式異常結束（exit code $exitCode）" "ERROR"
    Write-Host ""
    Write-Host "[ERROR] 程式意外停止，請回報上方錯誤訊息。" -ForegroundColor Red
    Read-Host "按 Enter 關閉"
} else {
    Write-Host ""
    Write-Host "5 秒後自動關閉..." -ForegroundColor Gray
    Start-Sleep -Seconds 5
}
