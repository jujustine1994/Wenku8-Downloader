/*  ================================  *\
 *                                    *
 *          C  T  H                   *
 *        created by CTH              *
 *                                    *
\*  ================================  */

規則檔: windows-tool.md
類型: Windows 工具

# Wenku8 Downloader

從 wenku8.net 輕小說網站批次下載整本書所有卷次，自動爬取目錄、逐卷下載並儲存為 TXT 檔。

## 執行方式

雙擊 `Wenku8下載器啟動器.bat`，首次執行會自動安裝所需套件。

## 系統需求

- Windows 10/11
- Python 3.10+（首次執行自動安裝）
- uv（首次執行自動安裝）
- 網路連線

## 技術棧

- 語言：Python 3.10+
- UI：tkinter（原生 ttk 主題；sv-ttk 已停用，見 CHANGELOG v13）
- 套件：curl_cffi（模擬 Chrome TLS 指紋繞過 Cloudflare）, beautifulsoup4, lxml, opencc-python-reimplemented（簡轉繁）

## .gitignore 必含項目

venv/
__pycache__/
*.pyc
.env
*.log
cache/
downloads/
