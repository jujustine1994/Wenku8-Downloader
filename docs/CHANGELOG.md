# CHANGELOG

## 現狀

**已完成功能：**
- URL 解析（aid 提取，支援 reader.php?aid=、/book/XXXX.htm、純數字書號）
- 目錄頁爬取與卷列表解析（curl_cffi 模擬 Chrome TLS，繞過 Cloudflare）
- 逐卷下載（retry 3x）
- tkinter UI（進度條、記錄區、主題切換）
- 卷選單（可勾選指定卷下載，全選/全不選）
- 啟動器（BAT + PS1）
- 輸出資料夾選擇（主 UI 直接顯示 + 可編輯 + 瀏覽按鈕）
- 設定視窗「下載」tab：retry 次數與間隔可調整（持久化至 config.json）

**尚未完成：**
- 見 docs/TODO.md

---

## 更新記錄

### 2026-06-10（v4）
- 新增：主 UI「書籍目錄網址」框加「下載至」列，可直接輸入或瀏覽選擇輸出資料夾
- 新增：設定視窗加「下載」tab，支援調整重試次數（1–10）與重試間隔（1–30 秒）
- 改善：downloader 的 retry 設定改為參數傳入，不再依賴 module-level hardcode

### 2026-06-10（v3）
- 新增：下載失敗後出現「重試 N 卷失敗」按鈕，一鍵重跑失敗卷
- 修正：下載也改用 `curl_cffi` Chrome TLS 指紋，解決 dl.wenku8.com 的 429 問題
- 修正：目錄頁為 GBK 編碼，改傳 bytes 給 BeautifulSoup 自動偵測，解決書名亂碼
- 修正：`parse_book_title` 加 regex 去除 title tag 的網站垃圾（「小说在线阅读與TXT下载…」）
- 修正：`ttk.Checkbutton` 不接受 `font=` 參數導致載入後 crash
- 修正：視窗最小寬度 600 → 800
- 修正：title_label 和 status_bar 綁定 wraplength，防止長文字撐寬視窗
- 技術：scraper 和 downloader 各自維護 module-level curl_cffi Session，重用 TLS 連線

### 2026-06-10（v2）
- 修正：改用 `curl_cffi` 模擬 Chrome 120 TLS 指紋，解決 Cloudflare 403 問題（目錄頁）
- 新增：卷選單（勾選清單 + 全選/全不選），可選擇要下載的卷
- 新增：`parse_aid_from_url` 支援 `/book/XXXX.htm`、純數字書號
- 修正：錯誤訊息過長造成視窗自動變寬

### 2026-06-10（v1）
- 新增：初始版本，完成主要下載功能
