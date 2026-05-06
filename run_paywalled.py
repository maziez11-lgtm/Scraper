"""News scraper entry point.

Calls all five site scrapers, merges the results, deduplicates by URL,
sorts by publication date (newest first), and writes news_output.csv.

Usage:
    python run.py
"""
import logging
import sys

import pandas as pd

from scrapers import bloomberg, foreignpolicy, ft, reuters, spglobal

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scraper registry
# ---------------------------------------------------------------------------
SCRAPERS = [
    ("Reuters",          reuters.scrape),
    ("Bloomberg",        bloomberg.scrape),
    ("Financial Times",  ft.scrape),
    ("S&P Global",       spglobal.scrape),
    ("Foreign Policy",   foreignpolicy.scrape),
]

OUTPUT_FILE = "news_output.csv"
MAX_PAGES   = 3

CSV_COLUMNS = ["title", "publication_date", "author", "summary", "url", "source"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    all_articles: list[dict] = []
    counts: dict[str, int] = {}

    for name, scrape_fn in SCRAPERS:
        divider = "─" * 60
        logger.info(divider)
        logger.info(f"  Scraping: {name}")
        logger.info(divider)
        try:
            articles = scrape_fn(max_pages=MAX_PAGES)
            counts[name] = len(articles)
            all_articles.extend(articles)
        except Exception as exc:
            logger.error(f"[{name}] Scraper raised an unexpected error: {exc}", exc_info=True)
            counts[name] = 0

    if not all_articles:
        logger.error("No articles collected from any source.  Check connectivity and selectors.")
        sys.exit(1)

    # ── Build DataFrame ──────────────────────────────────────────────────────
    df = pd.DataFrame(all_articles, columns=CSV_COLUMNS)

    # Deduplicate
    before = len(df)
    df = df.drop_duplicates(subset="url", keep="first").reset_index(drop=True)
    dupes = before - len(df)

    # Sort by date descending; rows without a date go to the bottom
    df["publication_date"] = pd.to_datetime(df["publication_date"], errors="coerce")
    df = df.sort_values("publication_date", ascending=False, na_position="last")

    # Normalise date format for the CSV
    df["publication_date"] = (
        df["publication_date"]
        .dt.strftime("%Y-%m-%d %H:%M:%S")
        .fillna("")
    )

    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    # ── Summary ──────────────────────────────────────────────────────────────
    width = 62
    print()
    print("=" * width)
    print(f"{'SCRAPE SUMMARY':^{width}}")
    print("=" * width)
    for source_name, count in counts.items():
        status = "✓" if count > 0 else "✗"
        print(f"  {status}  {source_name:<28}  {count:>4} articles")
    print("─" * width)
    total_scraped = sum(counts.values())
    print(f"     {'Total scraped':<28}  {total_scraped:>4} articles")
    if dupes:
        print(f"     {'Duplicates removed':<28}  {dupes:>4}")
    print(f"     {'Saved to CSV':<28}  {len(df):>4} articles")
    print("─" * width)
    print(f"  Output → {OUTPUT_FILE}")
    print("=" * width)
    print()


if __name__ == "__main__":
    main()
