"""Bloomberg Markets scraper – public content only.

Bloomberg is heavily JavaScript-rendered and places most article body text
behind a paywall.  This scraper extracts the publicly visible portions:

1. Article cards rendered in the static HTML (present on the markets page).
2. JSON-LD structured data embedded in <script> tags.
3. OpenGraph / meta-tag fallback when the page is a thin wrapper.

We never attempt to bypass the paywall; if a page returns a 403/paywall
redirect we log and move on.

Pagination: Bloomberg does not use traditional page parameters on /markets.
We instead scrape the main page plus two additional sub-sections to fulfil
the 3-page requirement.
"""
import time
import logging

from bs4 import BeautifulSoup

from .base import safe_get, parse_date, extract_json_ld, og_meta

logger = logging.getLogger(__name__)

SOURCE = "Bloomberg"

# Three distinct sections — treated as "pages" for article variety
SECTION_URLS = [
    "https://www.bloomberg.com/markets",
    "https://www.bloomberg.com/economics",
    "https://www.bloomberg.com/technology",
]


def _parse_card(card, base: str = "https://www.bloomberg.com") -> dict | None:
    # --- title + URL ---
    title_el = (
        card.select_one('[class*="headline"]')
        or card.select_one('[data-component*="headline"]')
        or card.select_one('h1 a')
        or card.select_one('h2 a')
        or card.select_one('h3 a')
        or card.select_one('a[href*="/news/articles"]')
        or card.select_one('a[href*="/articles/"]')
    )
    if not title_el:
        return None

    # headline element may be the anchor itself or contain one
    if title_el.name == "a":
        anchor = title_el
    else:
        anchor = title_el.find("a") or title_el

    title = title_el.get_text(strip=True)
    href = anchor.get("href", "") if hasattr(anchor, "get") else ""
    if not title or not href:
        return None

    url = href if href.startswith("http") else f"{base}{href}"

    # --- date ---
    date_el = (
        card.select_one("time[datetime]")
        or card.select_one("[data-updated-at]")
        or card.select_one("[class*='timestamp']")
    )
    pub_date = None
    if date_el:
        raw = date_el.get("datetime") or date_el.get("data-updated-at") or date_el.get_text(strip=True)
        pub_date = parse_date(raw)

    # --- author ---
    author_el = (
        card.select_one('[class*="author"]')
        or card.select_one('[rel="author"]')
        or card.select_one('[class*="byline"]')
    )
    author = author_el.get_text(strip=True) if author_el else ""

    # --- summary ---
    summary_el = (
        card.select_one('[class*="summary"]')
        or card.select_one('[class*="abstract"]')
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


def _extract_from_meta(soup) -> dict | None:
    """Last-resort extraction from OG tags when no article cards are found."""
    title = og_meta(soup, "title")
    url = og_meta(soup, "url")
    summary = og_meta(soup, "description")
    if not title or not url:
        return None
    jld = extract_json_ld(soup)
    pub_date = parse_date(jld.get("datePublished"))
    author_data = jld.get("author", {})
    author = author_data.get("name", "") if isinstance(author_data, dict) else ""
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
    urls = SECTION_URLS[:max_pages]

    for idx, url in enumerate(urls, 1):
        logger.info(f"[{SOURCE}] Section {idx}/{len(urls)} → {url}")

        resp = safe_get(
            url,
            extra_headers={
                "Referer": "https://www.bloomberg.com/",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        if resp is None:
            logger.warning(f"[{SOURCE}] Could not fetch {url} (likely paywall/bot-block); skipping")
            continue

        soup = BeautifulSoup(resp.text, "lxml")

        # Try article cards — Bloomberg uses data-component attributes
        cards = (
            soup.select('[data-component="story-list"] article')
            or soup.select('[data-type="article"]')
            or soup.select('article[data-id]')
            or soup.select('[class*="StoryList"] article')
            or soup.select('[class*="story-list-story"]')
            or soup.select('[class*="media-ui-HedAndDek"]')
            or soup.select('article')
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
            # Fallback: meta / JSON-LD only
            logger.warning(f"[{SOURCE}] No article cards found at {url}; trying meta fallback")
            result = _extract_from_meta(soup)
            if result and result["url"] not in seen:
                seen.add(result["url"])
                articles.append(result)
                found += 1

        logger.info(f"[{SOURCE}] Section {idx}: +{found} articles (running total {len(articles)})")
        time.sleep(1.5)

    logger.info(f"[{SOURCE}] Finished — {len(articles)} articles collected")
    return articles
