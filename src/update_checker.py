"""update_checker.py — 呼叫 scripts/check_update.ps1，把結果轉成 dict。

只負責「呼叫子行程 + 解析 JSON」，不碰任何 tkinter，方便單獨測試。
UI 呈現（按鈕、訊息框、多語言文字）都在 src/main.py 的「設定」分頁。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

_SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "check_update.ps1"


def _run(dry_run: bool) -> dict:
    if not _SCRIPT_PATH.exists():
        return {"status": "error", "message": "check_update.ps1 not found"}

    args = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(_SCRIPT_PATH),
    ]
    if dry_run:
        args.append("-DryRun")

    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, encoding="utf-8",
            timeout=30, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return {"status": "offline", "message": "timeout"}
    except OSError as e:
        return {"status": "error", "message": str(e)}

    # 腳本規範只在最後一行印 JSON，但保險起見從後往前找第一個能 parse 的行,
    # 避免 PowerShell 額外雜訊（例如舊版模組載入警告）混進 stdout。
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue

    return {"status": "error", "message": proc.stderr.strip() or "no output"}


def check_for_update() -> dict:
    """只檢查，不動任何檔案。"""
    return _run(dry_run=True)


def install_update() -> dict:
    """真的執行更新（checkout + commit）。呼叫前應先讓使用者確認過。"""
    return _run(dry_run=False)
