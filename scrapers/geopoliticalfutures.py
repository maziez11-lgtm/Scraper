"""Geopolitical Futures – Free Content scraper.

Geopolitical Futures runs on WordPress.  The /free-content/ archive page
lists publicly accessible articles without a paywall.

Confirmed WordPress structure:
  Container  : <article id="post-NNNNN" class="post type-post …">
  Title      : <h2 class="entry-title"> or <h3 class="entry-title">
               containing <a href="https://geopoliticalfutures.com/…/">
  Date       : <time class="entry-date published" datetime="YYYY-MM-DDTHH:MM:SS+00:00">
  Author     : <span class="author vcard"> → <a class="url fn n">
               or any element whose class contains "author"
  Summary    : <div class="entry-summary"> → first <p>
               fallback: <div class="entry-content"> → first <p>

Pagination  : /free-content/page/{N}/ (standard WordPress archive)
"""
import time
import logging

from bs4 import BeautifulSoup

from .base import safe_get, parse_date, extract_json_ld

logger = logging.getLogger(__name__)

SOURCE = "Geopolitical Futures"
BASE_URL = "https://geopoliticalfutures.com/free-content/"
SITE_ROOT = "https://geopoliticalfutures.com"


def _page_url(page: int) -> str:
    return BASE_URL if page == 1 else f"{BASE_URL}page/{page}/"


def _parse_card(card) -> dict | None:
    # ── title + URL ──────────────────────────────────────────────────────────
    title_el = (
        card.select_one(".entry-title a")
        or card.select_one("[class*='post-title'] a")
        or card.select_one("h2 a")
        or card.select_one("h3 a")
        or card.select_one("[class*='title'] a")
    )
    if not title_el:
        return None

    title = title_el.get_text(strip=True)
    href = title_el.get("href", "")
    if not title or not href:
        return None
    url = href if href.startswith("http") else f"{SITE_ROOT}{href}"

    # ── date ─────────────────────────────────────────────────────────────────
    # WordPress: <time class="entry-date published" datetime="…">
    date_el = (
        card.select_one("time.entry-date[datetime]")
        or card.select_one("time.published[datetime]")
        or card.select_one("time[datetime]")
        or card.select_one("[class*='post-date']")
        or card.select_one("[class*='date']")
    )
    pub_date = None
    if date_el:
        raw = date_el.get("datetime") or date_el.get_text(strip=True)
        pub_date = parse_date(raw)

    # ── author ───────────────────────────────────────────────────────────────
    author_el = (
        card.select_one(".author.vcard a")
        or card.select_one("[class*='author-name']")
        or card.select_one("[rel='author']")
        or card.select_one("[class*='author'] a")
        or card.select_one("[class*='byline'] a")
    )
    author = author_el.get_text(strip=True) if author_el else ""

    # ── summary ──────────────────────────────────────────────────────────────
    summary_el = (
        card.select_one(".entry-summary")
        or card.select_one("[class*='excerpt']")
        or card.select_one("[class*='summary']")
        or card.select_one("[class*='description']")
        or card.select_one(".entry-content")
    )
    if summary_el:
        # Grab first paragraph from the container
        first_p = summary_el.select_one("p")
        summary = (first_p or summary_el).get_text(strip=True)
    else:
        summary = ""
        for p in card.select("p"):
            text = p.get_text(strip=True)
            if len(text) > 30:
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

        resp = safe_get(
            url, extra_headers={"Referer": "https://geopoliticalfutures.com/"}
        )
        if resp is None:
            logger.warning(f"[{SOURCE}] Could not fetch page {page}; stopping")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Standard WordPress archive article containers
        cards = (
            soup.select("article.post")
            or soup.select("article.type-post")
            or soup.select("article[class*='post-']")
            or soup.select("[class*='post-card']")
            or soup.select("[class*='article-card']")
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
