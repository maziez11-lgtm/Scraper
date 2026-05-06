"""U.S. Energy Information Administration – Today in Energy scraper.

The EIA Today in Energy listing page shows recent briefs grouped by date.
Key facts confirmed from inspection:
  - Individual articles live at  /todayinenergy/detail.php?id=NNNNN
  - The archive is at             /todayinenergy/archive.php
  - Date text sits in a <p> or <strong> near each article link
  - Author field is always "EIA" (government publication, no byline on listing)

Strategy
  Page 1  → https://www.eia.gov/todayinenergy/
  Page 2+ → https://www.eia.gov/todayinenergy/archive.php?pageNum={N-1}
             (the archive paginates with pageNum=1,2,3…)

For each article link we walk the local DOM to extract:
  - Title   : link text
  - Date    : nearest preceding element whose text matches a date pattern
  - Summary : nearest following <p> with meaningful length
"""
import re
import time
import logging

from bs4 import BeautifulSoup, Tag

from .base import safe_get, parse_date

logger = logging.getLogger(__name__)

SOURCE = "EIA"
BASE_URL = "https://www.eia.gov/todayinenergy/"
ARCHIVE_URL = "https://www.eia.gov/todayinenergy/archive.php"
SITE_ROOT = "https://www.eia.gov"

_MONTH_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?"
    r"|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?"
    r"|Dec(?:ember)?)\b",
    re.IGNORECASE,
)


def _page_url(page: int) -> str:
    """Page 1 → main listing; Page 2+ → archive with 1-based pageNum."""
    if page == 1:
        return BASE_URL
    return f"{ARCHIVE_URL}?pageNum={page - 1}"


def _find_date_near(link: Tag) -> str:
    """
    Walk up two levels and scan for a text node that looks like a date.
    EIA groups articles under a <p> or <strong> that holds the date string.
    """
    parent = link.parent
    for _ in range(3):
        if parent is None:
            break
        # Check siblings that come BEFORE the link's parent
        for sib in parent.find_all_previous(["p", "strong", "b", "span", "h3", "h4"], limit=6):
            text = sib.get_text(strip=True)
            if _MONTH_RE.search(text) and len(text) < 80:
                return text
        parent = parent.parent
    return ""


def _find_summary_near(link: Tag) -> str:
    """Return the first descriptive <p> that follows the link."""
    for el in link.find_all_next(["p", "div"], limit=4):
        text = el.get_text(strip=True)
        if len(text) > 40 and not text.startswith("http"):
            return text[:400]
    return ""


def _extract_articles(soup: BeautifulSoup, seen: set[str]) -> list[dict]:
    """
    Find all detail-page links and build article dicts.
    Works on both the main listing page and the archive page.
    """
    results: list[dict] = []

    links = soup.select('a[href*="detail.php?id="]')
    if not links:
        # Broader fallback — any EIA todayinenergy link
        links = soup.select('a[href*="todayinenergy/detail"]')

    for link in links:
        href = link.get("href", "")
        if not href or "detail" not in href:
            continue

        title = link.get_text(strip=True)
        if not title or len(title) < 8:
            continue

        full_url = href if href.startswith("http") else f"{SITE_ROOT}{href}"
        if full_url in seen:
            continue
        seen.add(full_url)

        date_text = _find_date_near(link)
        pub_date = parse_date(date_text) if date_text else None

        summary = _find_summary_near(link)

        results.append(
            {
                "title": title,
                "publication_date": pub_date,
                "author": "EIA",
                "summary": summary,
                "url": full_url,
                "source": SOURCE,
            }
        )

    return results


def scrape(max_pages: int = 3) -> list[dict]:
    articles: list[dict] = []
    seen: set[str] = set()

    for page in range(1, max_pages + 1):
        url = _page_url(page)
        logger.info(f"[{SOURCE}] Page {page}/{max_pages} → {url}")

        resp = safe_get(url, extra_headers={"Referer": "https://www.eia.gov/"})
        if resp is None:
            logger.warning(f"[{SOURCE}] Could not fetch page {page}; stopping")
            break

        soup = BeautifulSoup(resp.text, "lxml")
        batch = _extract_articles(soup, seen)
        articles.extend(batch)

        logger.info(
            f"[{SOURCE}] Page {page}: +{len(batch)} articles "
            f"(running total {len(articles)})"
        )
        if not batch:
            break

        time.sleep(1.5)

    logger.info(f"[{SOURCE}] Finished — {len(articles)} articles collected")
    return articles
