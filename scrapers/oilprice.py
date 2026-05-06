"""OilPrice.com – Latest Energy News / World News scraper.

Page structure (stable across redesigns):
  Article container : <div class="categoryArticle"> (sometimes "genomeArticle")
  Title link        : first <a> inside an <h2>, <h3>, <h4>, or <h5>
  Date              : <span> inside the .categoryArticle__meta div, or
                      any element whose class contains "date" / "time"
  Author            : element whose class contains "author", or <a rel="author">
  Summary           : first <p> longer than 30 chars after the meta block

Pagination: /latest-energy-news/world-news/Page-{N}.html  (N ≥ 2)
"""
import re
import time
import logging

from bs4 import BeautifulSoup

from .base import safe_get, parse_date

logger = logging.getLogger(__name__)

SOURCE = "OilPrice.com"
BASE_URL = "https://oilprice.com/latest-energy-news/world-news/"
SITE_ROOT = "https://oilprice.com"

_DATE_RE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}",
    re.IGNORECASE,
)


def _page_url(page: int) -> str:
    return BASE_URL if page == 1 else f"{BASE_URL}Page-{page}.html"


def _parse_card(card) -> dict | None:
    # ── title + URL ─────────────────────────────────────────────────────────
    title_el = (
        card.select_one("h2 a")
        or card.select_one("h3 a")
        or card.select_one("h4 a")
        or card.select_one("h5 a")
        or card.select_one("[class*='title'] a")
        or card.select_one("[class*='headline'] a")
    )
    if not title_el:
        return None

    title = title_el.get_text(strip=True)
    href = title_el.get("href", "")
    if not title or not href:
        return None
    url = href if href.startswith("http") else f"{SITE_ROOT}{href}"

    # ── date ─────────────────────────────────────────────────────────────────
    # OilPrice embeds date text inside .categoryArticle__meta or similar spans
    date_el = (
        card.select_one("[class*='date']")
        or card.select_one("[class*='meta'] span")
        or card.select_one("time[datetime]")
        or card.select_one("[class*='time']")
    )
    pub_date = None
    if date_el:
        raw = date_el.get("datetime") or date_el.get_text(strip=True)
        pub_date = parse_date(raw)

    # Fallback: scan all text in the card for a date pattern
    if pub_date is None:
        m = _DATE_RE.search(card.get_text())
        if m:
            pub_date = parse_date(m.group(0))

    # ── author ───────────────────────────────────────────────────────────────
    author_el = (
        card.select_one("[class*='author'] a")
        or card.select_one("[class*='author']")
        or card.select_one("[rel='author']")
        or card.select_one("[class*='byline'] a")
    )
    author = author_el.get_text(strip=True) if author_el else ""

    # ── summary ──────────────────────────────────────────────────────────────
    summary = ""
    for p in card.select("p"):
        text = p.get_text(strip=True)
        if len(text) > 30 and not _DATE_RE.search(text):
            summary = text
            break

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
        url = _page_url(page)
        logger.info(f"[{SOURCE}] Page {page}/{max_pages} → {url}")

        resp = safe_get(url, extra_headers={"Referer": "https://oilprice.com/"})
        if resp is None:
            logger.warning(f"[{SOURCE}] Could not fetch page {page}; stopping")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        cards = (
            soup.select("div.categoryArticle")
            or soup.select("[class*='categoryArticle']")
            or soup.select("[class*='genomeArticle']")
            or soup.select("[class*='article-item']")
            or soup.select("[class*='news-item']")
            or soup.select("[class*='story-item']")
            or soup.select("article")
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

        logger.info(
            f"[{SOURCE}] Page {page}: +{found} articles "
            f"(running total {len(articles)})"
        )
        if found == 0:
            break

        time.sleep(1.5)

    logger.info(f"[{SOURCE}] Finished — {len(articles)} articles collected")
    return articles
