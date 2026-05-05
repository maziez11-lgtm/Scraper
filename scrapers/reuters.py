"""Reuters – Business/Energy section scraper.

Reuters renders its listing pages server-side with React hydration.
Article cards carry ``data-testid`` attributes; we try those first and
fall back through progressively looser selectors so the scraper stays
resilient to minor HTML changes.

Pagination: ``?start=N`` where N steps by 20 (0, 20, 40 …).
"""
import time
import logging

from bs4 import BeautifulSoup

from .base import safe_get, parse_date, extract_json_ld

logger = logging.getLogger(__name__)

SOURCE = "Reuters"
BASE_URL = "https://www.reuters.com/business/energy/"
PAGE_SIZE = 20


def _parse_card(card) -> dict | None:
    """Extract article fields from a single story-card element."""
    # --- title + URL ---
    title_el = (
        card.select_one('[data-testid="Heading"]')
        or card.select_one('a[data-testid*="heading"]')
        or card.select_one('[class*="heading__"] a')
        or card.select_one('h3 a')
        or card.select_one('h2 a')
        or card.select_one('a[href*="/article/"]')
        or card.select_one('a[href*="/world/"]')
        or card.select_one('a[href*="/business/"]')
    )
    if not title_el:
        return None

    title = title_el.get_text(strip=True)
    href = title_el.get("href", "")
    if not href or not title:
        return None

    url = href if href.startswith("http") else f"https://www.reuters.com{href}"

    # --- date ---
    date_el = card.select_one("time[datetime]")
    pub_date = parse_date(date_el["datetime"] if date_el else None)

    # --- author ---
    author_el = (
        card.select_one('a[href*="/authors/"]')
        or card.select_one('[class*="author"]')
        or card.select_one('[data-testid*="author"]')
    )
    author = author_el.get_text(strip=True) if author_el else ""

    # --- summary ---
    summary_el = (
        card.select_one('[data-testid="Body"]')
        or card.select_one('[class*="text__text"]')
        or card.select_one('[class*="teaser"]')
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

    for page in range(max_pages):
        offset = page * PAGE_SIZE
        url = BASE_URL if page == 0 else f"{BASE_URL}?start={offset}"
        logger.info(f"[{SOURCE}] Page {page + 1}/{max_pages} → {url}")

        resp = safe_get(url, extra_headers={"Referer": "https://www.reuters.com/"})
        if resp is None:
            logger.warning(f"[{SOURCE}] Could not fetch page {page + 1}; stopping")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Primary: data-testid story cards
        cards = (
            soup.select('[data-testid="MediaStoryCard"]')
            or soup.select('[data-testid="StoryCard"]')
            or soup.select('[data-testid*="story-card"]')
            # Fallback: class-based
            or soup.select('[class*="story-card"]')
            or soup.select('[class*="media-story-card"]')
            # Last resort
            or soup.select('article')
        )

        if not cards:
            logger.warning(f"[{SOURCE}] No article cards on page {page + 1}; stopping")
            break

        found = 0
        for card in cards:
            result = _parse_card(card)
            if result is None or result["url"] in seen:
                continue
            seen.add(result["url"])
            articles.append(result)
            found += 1

        logger.info(f"[{SOURCE}] Page {page + 1}: +{found} articles (running total {len(articles)})")

        if found == 0:
            break

        time.sleep(1.5)

    logger.info(f"[{SOURCE}] Finished — {len(articles)} articles collected")
    return articles
