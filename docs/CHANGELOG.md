# CHANGELOG

## 現狀

**已完成功能：**
- URL 解析（aid 提取，支援 reader.php?aid=、/book/XXXX.htm、純數字書號）
- 目錄頁爬取與卷列表解析（curl_cffi 模擬 Chrome TLS，繞過 Cloudflare）
- 逐卷下載（retry 3x）
- tkinter UI（進度條、記錄區、主題切換）
- 卷選單（可勾選指定卷下載，全選/全不選）
- 啟動器（BAT + PS1）

**尚未完成：**
- 見 docs/TODO.md

---

## 更新記錄

### 2026-06-10（v2）
- 修正：改用 `curl_cffi` 模擬 Chrome 120 TLS 指紋，解決 Cloudflare 403 問題
- 新增：卷選單（勾選清單 + 全選/全不選），可選擇要下載的卷
- 新增：URL 格式提示標籤，支援三種輸入格式
- 新增：`parse_aid_from_url` 支援 `/book/XXXX.htm`、純數字書號
- 修正：錯誤訊息過長造成視窗自動變寬

### 2026-06-10（v1）
- 新增：初始版本，完成主要下載功能
