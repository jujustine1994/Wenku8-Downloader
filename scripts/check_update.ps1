# check_update.ps1 — 檢查 / 安裝 GitHub 上的程式碼更新
#
# 給 GUI（設定 Tab 的「檢查更新」按鈕）呼叫，也可以獨立在終端機執行測試。
# 刻意做成「純資料輸出」：不印任何人類可讀的中文訊息，只在 stdout 最後一行
# 印一個 JSON，呼叫端（Python / 未來其他 launcher.ps1）自己決定怎麼呈現。
#
# 用法：
#   powershell -File scripts\check_update.ps1 -DryRun   # 只檢查，不動任何檔案
#   powershell -File scripts\check_update.ps1            # 檢查且有新版就直接安裝
#
# 回傳 JSON 的 status 欄位：
#   no_git            - 不是 git clone（zip 下載版），無法自動更新
#   offline           - git fetch 失敗（連不上 GitHub）
#   dirty             - 程式碼路徑有手動修改，避免覆蓋，不動作
#   ahead             - 本機有未 push 的 commit，避免覆蓋，不動作
#   up_to_date        - 已是最新版本
#   update_available  - 有新版本（DryRun 模式下停在這裡，不安裝）
#   updated           - 已完成安裝（非 DryRun 且原本 update_available）
#   error             - 其他未預期錯誤
#
# ⚠ 這支腳本只碰「程式碼」路徑，刻意排除 .tool_config.json 等使用者本機資料
#   （見下方 $CodePaths，對照 .gitignore）。套用到其他 Windows 工具專案時
#   只要照自己的專案結構調整這個清單即可（見
#   project-rules\windows-tool-templates.md「GitHub 自動更新（手動按鈕）」）。

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot

function Write-Result {
    param([hashtable]$Result)
    $Result | ConvertTo-Json -Depth 5 -Compress | Write-Output
}

try {
    if (-not (Test-Path ".git")) {
        Write-Result @{ status = "no_git" }
        exit 0
    }

    # 只同步「程式碼」路徑，排除 .tool_config.json（.gitignore 已排除，這裡再保險
    # 一次）、logs/、cache/、downloads/、__pycache__ 這些本機產生物或使用者資料。
    $CodePaths = @(
        "src", "requirements.txt", "requirements_test.txt",
        "docs", "tests", "scripts", "launcher.ps1"
    )
    Get-ChildItem -Path . -Filter "*.bat" -File | ForEach-Object { $CodePaths += $_.Name }
    $CodePaths = $CodePaths | Where-Object { Test-Path $_ }

    git fetch origin --quiet 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Result @{ status = "offline" }
        exit 0
    }

    $upstream = git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>$null
    if (-not $upstream) {
        $branch = git rev-parse --abbrev-ref HEAD
        $upstream = "origin/$branch"
    }

    $changed = git diff --name-only HEAD $upstream -- $CodePaths 2>$null
    if (-not $changed) {
        Write-Result @{ status = "up_to_date" }
        exit 0
    }

    $dirty = git status --porcelain -- $CodePaths 2>$null
    if ($dirty) {
        Write-Result @{ status = "dirty" }
        exit 0
    }

    # 只數「不是自動更新自己產生的」commit——自動更新成功一次後本機會永遠
    # ahead>=1（chore: auto-sync 那個 commit），照單全收會把自動更新鎖死。
    $autoSyncPrefix = "chore: auto-sync code from"
    $aheadCommits = @(git log --format="%s" "$upstream..HEAD" 2>$null |
                      Where-Object { $_ -and (-not $_.StartsWith($autoSyncPrefix)) })
    if ($aheadCommits.Count -gt 0) {
        Write-Result @{ status = "ahead"; count = $aheadCommits.Count }
        exit 0
    }

    $logLines = git log --format="%h %s" "HEAD..$upstream" 2>$null
    $commitCount = @($logLines).Count
    $summary = ($logLines | Select-Object -First 10) -join "`n"

    if ($DryRun) {
        Write-Result @{
            status  = "update_available"
            commits = $commitCount
            summary = $summary
        }
        exit 0
    }

    git checkout $upstream -- $CodePaths 2>$null
    git add -- $CodePaths
    $shortHash = git rev-parse --short $upstream
    git commit -m "chore: auto-sync code from $upstream ($shortHash)" --quiet 2>$null | Out-Null

    Write-Result @{
        status  = "updated"
        commit  = $shortHash
        commits = $commitCount
        summary = $summary
    }
}
catch {
    Write-Result @{ status = "error"; message = $_.Exception.Message }
}
