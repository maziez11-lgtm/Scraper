"""Natural Gas World (naturalgasworld.com) scraper.

Natural Gas World is a trade publication running on WordPress (or a
WordPress-derived CMS).  The homepage lists recent articles.

Expected structure (standard WordPress + common theme patterns):
  Container  : <article class="post …"> or <div class="post-item …">
  Title      : <h2 class="entry-title"> → <a href="…">
               fallback: any <h2 a> or <h3 a> inside the card
  Date       : <time class="entry-date" datetime="YYYY-MM-DDTHH:MM:SS">
               or <span class="post-date"> with text
  Author     : <span class="author vcard"> → <a class="url fn n">
               or any element whose class contains "author"
  Summary    : <div class="entry-summary"> → first <p>
               fallback: first <p> longer than 30 chars in the card

Pagination  : /page/{N}/ (standard WordPress archive pagination)
"""
import time
import logging

from bs4 import BeautifulSoup

from .base import safe_get, parse_date

logger = logging.getLogger(__name__)

SOURCE = "Natural Gas World"
BASE_URL = "https://www.naturalgasworld.com/"
SITE_ROOT = "https://www.naturalgasworld.com"


def _page_url(page: int) -> str:
    return BASE_URL if page == 1 else f"{BASE_URL}page/{page}/"


def _parse_card(card) -> dict | None:
    # ── title + URL ──────────────────────────────────────────────────────────
    title_el = (
        card.select_one(".entry-title a")
        or card.select_one("[class*='post-title'] a")
        or card.select_one("[class*='article-title'] a")
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
    date_el = (
        card.select_one("time.entry-date[datetime]")
        or card.select_one("time.updated[datetime]")
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
        or card.select_one("[class*='author'] a")
        or card.select_one("[rel='author']")
        or card.select_one("[class*='byline'] a")
        or card.select_one("[class*='author']")
    )
    author = author_el.get_text(strip=True) if author_el else ""

    # ── summary ──────────────────────────────────────────────────────────────
    summary_el = (
        card.select_one(".entry-summary")
        or card.select_one("[class*='excerpt']")
        or card.select_one("[class*='description']")
        or card.select_one("[class*='summary']")
    )
    if summary_el:
        summary = summary_el.get_text(strip=True)
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
            url, extra_headers={"Referer": "https://www.naturalgasworld.com/"}
        )
        if resp is None:
            logger.warning(f"[{SOURCE}] Could not fetch page {page}; stopping")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # WordPress article containers
        cards = (
            soup.select("article.post")
            or soup.select("article[class*='post-']")
            or soup.select("[class*='post-item']")
            or soup.select("[class*='article-card']")
            or soup.select("[class*='news-item']")
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
