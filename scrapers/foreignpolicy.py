"""Foreign Policy – homepage / archive scraper.

Foreign Policy runs on WordPress.  Article cards on the homepage and
archive pages follow standard WordPress markup (``article.post``, ``h2``,
``time[datetime]``, ``.byline``, ``.dek``).

Pagination: ``/page/N/`` (N starts at 1; page 1 is the bare root URL).
"""
import time
import logging

from bs4 import BeautifulSoup

from .base import safe_get, parse_date, extract_json_ld

logger = logging.getLogger(__name__)

SOURCE = "Foreign Policy"
BASE_URL = "https://foreignpolicy.com"


def _parse_card(card) -> dict | None:
    # --- title + URL ---
    title_el = (
        card.select_one('.article-header__title a')
        or card.select_one('.post-title a')
        or card.select_one('.entry-title a')
        or card.select_one('h2 a')
        or card.select_one('h3 a')
        or card.select_one('[class*="headline"] a')
    )
    if not title_el:
        return None

    title = title_el.get_text(strip=True)
    href = title_el.get("href", "")
    if not title or not href:
        return None

    url = href if href.startswith("http") else f"{BASE_URL}{href}"

    # --- date ---
    # WordPress standard: <time class="entry-date" datetime="…">
    date_el = (
        card.select_one('time.entry-date[datetime]')
        or card.select_one('time.updated[datetime]')
        or card.select_one('time[datetime]')
        or card.select_one('[class*="date"]')
        or card.select_one('[class*="time"]')
    )
    pub_date = None
    if date_el:
        raw = date_el.get("datetime") or date_el.get_text(strip=True)
        pub_date = parse_date(raw)

    # --- author ---
    author_el = (
        card.select_one('.byline a')
        or card.select_one('.author a')
        or card.select_one('[rel="author"]')
        or card.select_one('[class*="author-name"]')
        or card.select_one('[class*="byline"]')
    )
    author = author_el.get_text(strip=True) if author_el else ""

    # --- summary / dek ---
    summary_el = (
        card.select_one('.article-header__dek')
        or card.select_one('.dek')
        or card.select_one('.entry-summary')
        or card.select_one('[class*="excerpt"]')
        or card.select_one('[class*="description"]')
        or card.select_one('[class*="standfirst"]')
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
        url = BASE_URL if page == 1 else f"{BASE_URL}/page/{page}/"
        logger.info(f"[{SOURCE}] Page {page}/{max_pages} → {url}")

        resp = safe_get(url, extra_headers={"Referer": "https://foreignpolicy.com/"})
        if resp is None:
            logger.warning(f"[{SOURCE}] Could not fetch page {page}; stopping")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # WordPress article containers
        cards = (
            soup.select('article.post')
            or soup.select('article[class*="post-"]')
            or soup.select('[class*="article-card"]')
            or soup.select('[class*="post-card"]')
            or soup.select('[class*="story-card"]')
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
