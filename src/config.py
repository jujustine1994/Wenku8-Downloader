CATALOG_BASE_URL = "https://www.wenku8.net/modules/article/reader.php"
# reader.php 被 Cloudflare 擋下時的備援來源（見 scraper.fetch_catalog）
BOOK_BASE_URL = "https://www.wenku8.net/book"
NOVEL_BASE_URL = "https://www.wenku8.net/novel"
DOWNLOAD_BASE_URL = "http://dl.wenku8.com/packtxt.php"
OUTPUT_DIR = "downloads"
RETRY_COUNT = 3
RETRY_DELAY = 2  # seconds between retries

# 每次送出請求之間的基礎間隔（秒）。對付 wenku8 的 HTTP 429 限流用，
# 詳見 src/ratelimit.py。使用者可在「設定」分頁調整，存進 .tool_config.json。
#
# 預算依據：使用者可接受 60 檔 / 5 分鐘 = 每卷 5 秒。單卷抓取約 1.5–2.5 秒，
# 2.5 秒的間隔讓 60 卷落在 240–300 秒。
REQUEST_INTERVAL = 2.5

