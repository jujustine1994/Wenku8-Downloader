import re
import urllib.parse
from bs4 import BeautifulSoup
from curl_cffi import requests as cf_requests
from src.config import CATALOG_BASE_URL

_MAIN_VOL_RE = re.compile(
    r'第[一二三四五六七八九十百千萬\d]+[卷册冊部篇章]'
    r'|Vol\.?\s*\d+'
    r'|卷[一二三四五六七八九十百千萬\d]+'
    r'|\d+[卷册冊部篇章]',
    re.IGNORECASE,
)

# Module-level session：重用 TLS 連線，避免每次重建握手
_session: cf_requests.Session | None = None


def _get_session() -> cf_requests.Session:
    global _session
    if _session is None:
        _session = cf_requests.Session()
    return _session


def classify_volume(name: str, side_keywords: list[str]) -> str:
    """Returns 'main' or 'side'. Main-pattern whitelist takes priority."""
    if _MAIN_VOL_RE.search(name):
        return "main"
    name_lower = name.lower()
    for kw in side_keywords:
        if kw.lower() in name_lower:
            return "side"
    return "main"


def parse_aid_from_url(url: str) -> str:
    url = url.strip()

    # 純數字書號，如 "1861"
    if re.fullmatch(r"\d+", url):
        return url

    # reader.php?aid=XXXX 或 ...&aid=XXXX
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    if "aid" in params:
        return params["aid"][0]

    # wenku8.net/book/1861.htm 或 /novel/1861/
    m = re.search(r"/(?:book|novel)/(\d+)", url)
    if m:
        return m.group(1)

    raise ValueError("無法識別書號，請貼上目錄網址或直接輸入書號數字")


def fetch_catalog(aid: str) -> BeautifulSoup:
    url = f"{CATALOG_BASE_URL}?aid={aid}"
    # impersonate="chrome120" 模擬 Chrome TLS 指紋，繞過 Cloudflare Bot Management
    # 傳 resp.content（bytes）給 BeautifulSoup，讓 lxml 從 meta charset 自動偵測 GBK/UTF-8
    resp = _get_session().get(url, impersonate="chrome120", timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.content, "lxml")


def parse_book_title(soup: BeautifulSoup) -> str:
    h2 = soup.find("h2")
    if h2:
        return h2.get_text(strip=True)
    title_tag = soup.find("title")
    if title_tag:
        raw = title_tag.get_text(strip=True)
        # wenku8 格式："書名小說在線閱讀與TXT電子書下載-作者-出版社-網站名"
        # 取書名關鍵字前的部分
        m = re.match(r"^(.+?)(?:小说|TXT|全文|在线|电子书)", raw, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return raw.split(" - ")[0].strip()
    return "未知書名"


def parse_volumes(soup: BeautifulSoup) -> list[dict]:
    volumes = []
    current_volume = None
    volume_index = 0
    found_first_chapter = False

    for row in soup.find_all("tr"):
        cells = row.find_all("td")

        # Volume header: single full-width cell, no links inside
        if (len(cells) == 1
                and cells[0].get("colspan")
                and not cells[0].find("a")):
            current_volume = {
                "index": volume_index + 1,
                "name": cells[0].get_text(strip=True),
            }
            volume_index += 1
            found_first_chapter = False
            continue

        # First chapter link under current volume
        if current_volume and not found_first_chapter:
            first_link = row.find("a")
            if first_link and first_link.get("href"):
                parsed = urllib.parse.urlparse(first_link["href"])
                params = urllib.parse.parse_qs(parsed.query)
                if "cid" in params:
                    cid = int(params["cid"][0])
                    volumes.append({
                        **current_volume,
                        "first_cid": cid,
                        "vid": cid - 1,
                    })
                    found_first_chapter = True

    return volumes
