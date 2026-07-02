"""
Validation of the prerendered newsletter.

Four checks gate the issue's "ready" status: completeness of the curation,
reachability of every image in the rendered HTML, freshness of the showtimes,
and integrity of the rendered output itself.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html.parser import HTMLParser

import requests

from . import issue as issue_store
from .prerender import PREVIEW_FILE, load_movie_lookup


class _PreviewParser(HTMLParser):
    """Collects image sources and visible text from the rendered newsletter."""

    def __init__(self):
        super().__init__()
        self.image_urls = []
        self.text_parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            src = dict(attrs).get("src")
            if src:
                self.image_urls.append(src)

    def handle_data(self, data):
        self.text_parts.append(data)


# Some CDNs (e.g. Wikimedia) reject the default python-requests user agent
_UA = {"User-Agent": "Mozilla/5.0 (compatible; newsletter-validator/1.0)"}


def _check_url(url: str) -> tuple:
    """Return (url, error or None) for one image URL."""
    try:
        resp = requests.head(url, timeout=10, allow_redirects=True, headers=_UA)
        if resp.status_code in (405, 403, 501):
            resp = requests.get(url, timeout=10, stream=True, headers=_UA)
        if resp.status_code >= 400:
            return url, f"HTTP {resp.status_code}"
        return url, None
    except requests.RequestException as e:
        return url, type(e).__name__


def check_completeness(current: dict, sections: dict, lookup: dict) -> dict:
    problems = []
    if not current["movies"]:
        problems.append("No movies selected for this issue.")
    for movie_id, entry in current["movies"].items():
        movie = lookup.get(str(movie_id))
        title = movie["title"] if movie else f"movie {movie_id}"
        if movie is None:
            problems.append(f"'{title}' is no longer in the scraped data — reselect or remove it.")
        section = entry.get("section")
        if not section:
            problems.append(f"'{title}' is not assigned to a section.")
        elif section not in sections:
            problems.append(f"'{title}' is assigned to unknown section '{section}'.")
        if not (entry.get("comment") or "").strip():
            problems.append(f"'{title}' has no comment yet.")
    return {"name": "completeness", "label": "Completeness",
            "passed": not problems, "problems": problems}


def check_images(parser: _PreviewParser) -> dict:
    urls = sorted(set(parser.image_urls))
    problems = []
    if urls:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for url, error in pool.map(_check_url, urls):
                if error:
                    problems.append(f"{url} — {error}")
    return {"name": "images", "label": f"Images ({len(urls)} checked)",
            "passed": not problems, "problems": problems}


def check_stale_showtimes(current: dict, lookup: dict) -> dict:
    problems = []
    now = datetime.now()
    for movie_id in current["movies"]:
        movie = lookup.get(str(movie_id))
        if movie is None:
            continue  # reported by completeness
        showtimes = movie.get("showtimes") or []
        if not showtimes:
            problems.append(f"'{movie['title']}' has no showtimes at all.")
            continue
        future = [st for st in showtimes
                  if st.get("datetime") and datetime.fromisoformat(st["datetime"]) > now]
        if not future:
            problems.append(f"'{movie['title']}' has only past showtimes — the scrape is stale.")
    return {"name": "showtimes", "label": "Showtimes freshness",
            "passed": not problems, "problems": problems}


def check_render_integrity(current: dict, lookup: dict, html: str,
                           parser: _PreviewParser) -> dict:
    problems = []
    text = " ".join(parser.text_parts)
    for movie_id in current["movies"]:
        movie = lookup.get(str(movie_id))
        if movie is None:
            continue  # reported by completeness
        if movie["title"] not in text:
            problems.append(f"'{movie['title']}' is missing from the rendered newsletter.")
    for artifact in ("undefined", "[object Object]", "NaN min"):
        if artifact in html:
            problems.append(f"Rendered HTML contains '{artifact}' — a template field is unresolved.")
    if "Non classés (brouillon)" in html:
        problems.append("Rendered newsletter still contains the draft 'unassigned' section.")
    return {"name": "render", "label": "Render integrity",
            "passed": not problems, "problems": problems}


def run_validation() -> dict:
    """Run all checks against the current prerender; update the issue status."""
    current = issue_store.load_issue()
    sections = issue_store.load_sections()
    lookup = load_movie_lookup()

    if not os.path.exists(PREVIEW_FILE):
        return {"passed": False, "status": "draft", "checks": [],
                "error": "No prerender found — render the preview first."}

    with open(PREVIEW_FILE, "r", encoding="utf-8") as f:
        html = f.read()
    parser = _PreviewParser()
    parser.feed(html)

    checks = [
        check_completeness(current, sections, lookup),
        check_images(parser),
        check_stale_showtimes(current, lookup),
        check_render_integrity(current, lookup, html, parser),
    ]

    passed = all(c["passed"] for c in checks)
    issue_store.set_issue_status("ready" if passed else "draft")
    return {"passed": passed, "status": "ready" if passed else "draft",
            "checks": checks, "error": None}
