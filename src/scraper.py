import urllib.parse
import requests
from bs4 import BeautifulSoup
from src.config import CATALOG_BASE_URL, HEADERS


def parse_aid_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    if "aid" not in params:
        raise ValueError(f"No 'aid' parameter in URL: {url}")
    return params["aid"][0]


def fetch_catalog(aid: str) -> BeautifulSoup:
    url = f"{CATALOG_BASE_URL}?aid={aid}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
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
