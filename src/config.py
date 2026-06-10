CATALOG_BASE_URL = "https://www.wenku8.net/modules/article/reader.php"
DOWNLOAD_BASE_URL = "http://dl.wenku8.com/packtxt.php"
OUTPUT_DIR = "downloads"
RETRY_COUNT = 3
RETRY_DELAY = 2  # seconds between retries

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.wenku8.net/",
}
