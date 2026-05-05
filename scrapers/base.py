"""Shared utilities for all scrapers."""
import json
import time
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# User-agent rotation
# ---------------------------------------------------------------------------
_FALLBACK_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

try:
    from fake_useragent import UserAgent
    _ua = UserAgent(fallback=_FALLBACK_UA)

    def _random_ua() -> str:
        try:
            return _ua.random
        except Exception:
            return _FALLBACK_UA

except Exception:
    _ua = None

    def _random_ua() -> str:
        return _FALLBACK_UA


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def get_headers(extra: dict | None = None) -> dict:
    headers = {
        "User-Agent": _random_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "DNT": "1",
        "Cache-Control": "max-age=0",
    }
    if extra:
        headers.update(extra)
    return headers


def safe_get(
    url: str,
    session: requests.Session | None = None,
    retries: int = 3,
    timeout: int = 20,
    extra_headers: dict | None = None,
) -> requests.Response | None:
    """GET a URL with exponential-backoff retry. Returns Response or None."""
    requester = session if session else requests
    for attempt in range(retries):
        try:
            resp = requester.get(
                url,
                headers=get_headers(extra_headers),
                timeout=timeout,
                allow_redirects=True,
            )
            # Treat hard blocks as non-retryable
            if resp.status_code in (403, 404, 410, 451):
                logger.debug(f"HTTP {resp.status_code} for {url}")
                return None
            resp.raise_for_status()
            return resp
        except requests.exceptions.HTTPError:
            return None
        except requests.exceptions.RequestException as exc:
            if attempt < retries - 1:
                wait = 2 ** attempt
                logger.debug(f"Attempt {attempt + 1} failed for {url}: {exc}. Retrying in {wait}s…")
                time.sleep(wait)
            else:
                logger.debug(f"All retries exhausted for {url}: {exc}")
    return None


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def parse_date(date_str: str | None) -> datetime | None:
    """Parse a date string into a datetime object using multiple strategies."""
    if not date_str:
        return None
    date_str = str(date_str).strip()

    # Fast path: ISO 8601 variants
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            pass

    # Slow path: dateutil for natural-language dates
    try:
        from dateutil import parser as dparser
        return dparser.parse(date_str, ignoretz=True)
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Structured-data helpers
# ---------------------------------------------------------------------------

def extract_json_ld(soup) -> dict:
    """Return the first NewsArticle/Article schema from JSON-LD blocks."""
    TARGET_TYPES = {"NewsArticle", "Article", "ReportageNewsArticle", "Report"}
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            raw = script.string or ""
            data = json.loads(raw)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict) and item.get("@type") in TARGET_TYPES:
                    return item
                # Handle @graph arrays
                for node in item.get("@graph", []):
                    if isinstance(node, dict) and node.get("@type") in TARGET_TYPES:
                        return node
        except Exception:
            pass
    return {}


def og_meta(soup, prop: str) -> str:
    """Return content of an OpenGraph or standard meta tag."""
    el = (
        soup.find("meta", property=f"og:{prop}")
        or soup.find("meta", attrs={"name": f"og:{prop}"})
        or soup.find("meta", attrs={"name": prop})
    )
    return (el.get("content") or "").strip() if el else ""
