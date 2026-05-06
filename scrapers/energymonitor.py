"""Energy Monitor (energymonitor.ai) scraper.

Energy Monitor is built on a headless CMS (Ghost-based or similar).
Article cards on the homepage / section pages follow modern CMS conventions:

  Container  : <article> or <div> with class containing "post-card" / "article-card"
  Title      : <h2> or <h3> inside the card, usually containing an <a>
  Date       : <time datetime="ISO-8601"> — Ghost CMS always emits this
  Author     : element with class containing "author" or "byline"
  Summary    : element with class containing "excerpt" / "description" / "standfirst",
               or the first <p> inside the card

Pagination  : /page/{N}/ (Ghost CMS default) or ?page={N}

We try the homepage first, then /page/2/, /page/3/ …
If the homepage redirects or returns a section index, we follow it.
"""
import time
import logging

from bs4 import BeautifulSoup

from .base import safe_get, parse_date, extract_json_ld, og_meta

logger = logging.getLogger(__name__)

SOURCE = "Energy Monitor"
BASE_URL = "https://energymonitor.ai/"
SITE_ROOT = "https://energymonitor.ai"


def _page_url(page: int) -> str:
    return BASE_URL if page == 1 else f"{BASE_URL}page/{page}/"


def _parse_card(card) -> dict | None:
    # ── title + URL ──────────────────────────────────────────────────────────
    title_el = (
        card.select_one("h2 a")
        or card.select_one("h3 a")
        or card.select_one("h1 a")
        or card.select_one("[class*='title'] a")
        or card.select_one("[class*='headline'] a")
        or card.select_one("a[href*='energymonitor']")
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
        card.select_one("time[datetime]")
        or card.select_one("[class*='date']")
        or card.select_one("[class*='time']")
        or card.select_one("[class*='published']")
    )
    pub_date = None
    if date_el:
        raw = date_el.get("datetime") or date_el.get_text(strip=True)
        pub_date = parse_date(raw)

    # ── author ───────────────────────────────────────────────────────────────
    author_el = (
        card.select_one("[class*='author'] a")
        or card.select_one("[class*='byline'] a")
        or card.select_one("[rel='author']")
        or card.select_one("[class*='author']")
    )
    author = author_el.get_text(strip=True) if author_el else ""

    # ── summary ──────────────────────────────────────────────────────────────
    summary_el = (
        card.select_one("[class*='excerpt']")
        or card.select_one("[class*='description']")
        or card.select_one("[class*='standfirst']")
        or card.select_one("[class*='summary']")
        or card.select_one("p")
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


def _from_json_ld(soup) -> list[dict]:
    """Extract articles embedded as JSON-LD ItemList on some CMS homepages."""
    items: list[dict] = []
    import json
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            obj = data if isinstance(data, dict) else {}
            # ItemList → ListItem → url/name
            for li in obj.get("itemListElement", []):
                if not isinstance(li, dict):
                    continue
                url = li.get("url") or li.get("item", {}).get("url", "")
                name = li.get("name") or li.get("item", {}).get("name", "")
                if url and name:
                    items.append(
                        {
                            "title": name,
                            "publication_date": None,
                            "author": "",
                            "summary": "",
                            "url": url,
                            "source": SOURCE,
                        }
                    )
        except Exception:
            pass
    return items


def scrape(max_pages: int = 3) -> list[dict]:
    articles: list[dict] = []
    seen: set[str] = set()

    for page in range(1, max_pages + 1):
        url = _page_url(page)
        logger.info(f"[{SOURCE}] Page {page}/{max_pages} → {url}")

        resp = safe_get(url, extra_headers={"Referer": "https://energymonitor.ai/"})
        if resp is None:
            logger.warning(f"[{SOURCE}] Could not fetch page {page}; stopping")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Try article cards first
        cards = (
            soup.select("[class*='post-card']")
            or soup.select("[class*='article-card']")
            or soup.select("[class*='story-card']")
            or soup.select("[class*='news-card']")
            or soup.select("article")
            or soup.select("[class*='post-item']")
        )

        found = 0
        if cards:
            for card in cards:
                result = _parse_card(card)
                if result is None or result["url"] in seen:
                    continue
                seen.add(result["url"])
                articles.append(result)
                found += 1
        else:
            # Fallback: JSON-LD ItemList
            for item in _from_json_ld(soup):
                if item["url"] not in seen:
                    seen.add(item["url"])
                    articles.append(item)
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
