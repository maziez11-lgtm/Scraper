"""S&P Global Commodity Insights – Latest News scraper.

The latest-news listing page renders article rows in a standard HTML list.
Each row typically contains a headline link, a publication date/time, and
an optional topic tag.  Author information is rarely surfaced on the listing
page itself.

Pagination: ``?page=N`` (1-indexed).  If the server uses a different scheme
(e.g. offset-based) we stop when no new articles are found.
"""
import time
import logging

from bs4 import BeautifulSoup

from .base import safe_get, parse_date

logger = logging.getLogger(__name__)

SOURCE = "S&P Global"
BASE_URL = "https://www.spglobal.com/commodityinsights/en/market-insights/latest-news"
SITE_ROOT = "https://www.spglobal.com"


def _parse_card(card) -> dict | None:
    # --- title + URL ---
    title_el = (
        card.select_one('a[class*="headline"]')
        or card.select_one('.article-title a')
        or card.select_one('[class*="title"] a')
        or card.select_one('h3 a')
        or card.select_one('h2 a')
        or card.select_one('h4 a')
        or card.select_one('a')
    )
    if not title_el:
        return None

    title = title_el.get_text(strip=True)
    href = title_el.get("href", "")
    if not title or not href:
        return None

    url = href if href.startswith("http") else f"{SITE_ROOT}{href}"

    # --- date ---
    date_el = (
        card.select_one("time[datetime]")
        or card.select_one("[class*='pub-date']")
        or card.select_one("[class*='date']")
        or card.select_one("[class*='time']")
        or card.select_one("span[class*='timestamp']")
    )
    pub_date = None
    if date_el:
        raw = date_el.get("datetime") or date_el.get_text(strip=True)
        pub_date = parse_date(raw)

    # --- author (often absent on listing pages) ---
    author_el = (
        card.select_one('[class*="author"]')
        or card.select_one('[rel="author"]')
        or card.select_one('[class*="byline"]')
    )
    author = author_el.get_text(strip=True) if author_el else ""

    # --- summary ---
    summary_el = (
        card.select_one('[class*="summary"]')
        or card.select_one('[class*="teaser"]')
        or card.select_one('[class*="excerpt"]')
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
            extra_headers={"Referer": "https://www.spglobal.com/"},
        )
        if resp is None:
            logger.warning(f"[{SOURCE}] Could not fetch page {page}; stopping")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # S&P Global CMS — try several container patterns
        cards = (
            soup.select('.article-list__item')
            or soup.select('[class*="news-item"]')
            or soup.select('[class*="article-card"]')
            or soup.select('[class*="news-card"]')
            or soup.select('[class*="story-item"]')
            or soup.select('[class*="latest-news"]')
            or soup.select('li[class*="item"]')
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
