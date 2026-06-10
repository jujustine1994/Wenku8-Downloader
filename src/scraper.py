import re
import urllib.parse
from bs4 import BeautifulSoup
from curl_cffi import requests as cf_requests
from src.config import CATALOG_BASE_URL


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
    resp = cf_requests.get(url, impersonate="chrome120", timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "lxml")


def parse_book_title(soup: BeautifulSoup) -> str:
    h2 = soup.find("h2")
    if h2:
        return h2.get_text(strip=True)
    title_tag = soup.find("title")
    if title_tag:
        return title_tag.get_text(strip=True).split(" - ")[0].strip()
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
