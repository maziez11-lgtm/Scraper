"""Financial Times – World section scraper (public content only).

FT uses the Origami design system.  Article teasers live inside
``.o-teaser`` components on listing pages.  Paywalled article bodies are
not accessed; only headline, standfirst, date, and author from the listing
are extracted.

Pagination: ``?page=N`` (1-indexed).
"""
import time
import logging

from bs4 import BeautifulSoup

from .base import safe_get, parse_date, og_meta

logger = logging.getLogger(__name__)

SOURCE = "Financial Times"
BASE_URL = "https://www.ft.com/world"


def _parse_card(card) -> dict | None:
    # --- title + URL ---
    # Origami: .o-teaser__heading > a
    title_el = (
        card.select_one('.o-teaser__heading a')
        or card.select_one('[class*="heading"] a')
        or card.select_one('h3 a')
        or card.select_one('h2 a')
        or card.select_one('a[href*="/content/"]')
    )
    if not title_el:
        return None

    title = title_el.get_text(strip=True)
    href = title_el.get("href", "")
    if not title or not href:
        return None

    url = href if href.startswith("http") else f"https://www.ft.com{href}"

    # Strip query strings that contain tracking tokens but keep the path clean
    url = url.split("?")[0]

    # --- date ---
    # Origami: time.o-date[datetime] or time[data-o-date-current]
    date_el = (
        card.select_one("time.o-date[datetime]")
        or card.select_one("time[datetime]")
        or card.select_one("[data-o-date-current]")
        or card.select_one("[class*='timestamp']")
    )
    pub_date = None
    if date_el:
        raw = (
            date_el.get("datetime")
            or date_el.get("data-o-date-current")
            or date_el.get_text(strip=True)
        )
        pub_date = parse_date(raw)

    # --- author ---
    author_el = (
        card.select_one('.o-teaser__author')
        or card.select_one('[class*="author"]')
        or card.select_one('[rel="author"]')
        or card.select_one('[class*="byline"]')
    )
    author = author_el.get_text(strip=True) if author_el else ""

    # --- summary / standfirst ---
    summary_el = (
        card.select_one('.o-teaser__standfirst')
        or card.select_one('[class*="standfirst"]')
        or card.select_one('[class*="summary"]')
        or card.select_one('[class*="description"]')
        or card.select_one('p')
    )
    summary = summary_el.get_text(strip=True) if summary_el else ""

    return {
        "title": title,
        "publication_date": pub_date,
        "author": author,
        "summary": summary,
        "url": url,
        "source": SOURCE,
    }


def scrape(max_pages: int = 3) -> list[dict]:
    articles: list[dict] = []
    seen: set[str] = set()

    for page in range(1, max_pages + 1):
        url = BASE_URL if page == 1 else f"{BASE_URL}?page={page}"
        logger.info(f"[{SOURCE}] Page {page}/{max_pages} → {url}")

        resp = safe_get(
            url,
            extra_headers={
                "Referer": "https://www.ft.com/",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        if resp is None:
            logger.warning(f"[{SOURCE}] Could not fetch page {page}; stopping")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Origami teaser components
        cards = (
            soup.select('.o-teaser')
            or soup.select('[data-trackable="article"]')
            or soup.select('li.js-stream-article')
            or soup.select('[class*="teaser"]')
            or soup.select('article')
        )

        if not cards:
            logger.warning(f"[{SOURCE}] No article cards on page {page}; stopping")
            break

        found = 0
        for card in cards:
            result = _parse_card(card)
            if result is None or result["url"] in seen:
                continue
            seen.add(result["url"])
            articles.append(result)
            found += 1

        logger.info(f"[{SOURCE}] Page {page}: +{found} articles (running total {len(articles)})")

        if found == 0:
            break

        time.sleep(1.5)

    logger.info(f"[{SOURCE}] Finished — {len(articles)} articles collected")
    return articles
