"""Fetch a Letterboxd watchlist by scraping the public watchlist page."""

import re
from dataclasses import dataclass
from html import unescape

import cloudscraper


@dataclass
class WatchlistEntry:
    title: str
    slug: str


_FILM_PATTERN = re.compile(
    r'data-target-link="/film/([^"]+)/"[^>]*>.*?alt="([^"]+)"',
    re.DOTALL,
)
_PAGE_PATTERN = re.compile(r'/watchlist/page/(\d+)/')
_MAX_PAGES = 10


def fetch_watchlist(username: str) -> list[WatchlistEntry]:
    scraper = cloudscraper.create_scraper()
    entries, max_page = _fetch_page(scraper, username, 1)

    for page in range(2, min(max_page, _MAX_PAGES) + 1):
        page_entries, _ = _fetch_page(scraper, username, page)
        if not page_entries:
            break
        entries.extend(page_entries)

    return entries


def _fetch_page(
    scraper: cloudscraper.CloudScraper, username: str, page: int
) -> tuple[list[WatchlistEntry], int]:
    if page == 1:
        url = f"https://letterboxd.com/{username}/watchlist/"
    else:
        url = f"https://letterboxd.com/{username}/watchlist/page/{page}/"

    resp = scraper.get(url, timeout=15)
    resp.raise_for_status()

    entries = []
    for slug, title in _FILM_PATTERN.findall(resp.text):
        entries.append(WatchlistEntry(title=unescape(title), slug=slug))

    page_nums = _PAGE_PATTERN.findall(resp.text)
    max_page = max((int(p) for p in page_nums), default=1)

    return entries, max_page
