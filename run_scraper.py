"""
Product Page Scraper - Runner Script
=====================================
Run this locally to scrape product pages from a feed export.

Usage:
    python run_scraper.py <feed_file> [--max 100] [--delay 1.0] [--output scraped.csv]

Examples:
    # Scrape first 10 products (test run)
    python run_scraper.py products.tsv --max 10

    # Scrape all products with 1.5s delay
    python run_scraper.py products.tsv --delay 1.5

    # Specify output file
    python run_scraper.py products.tsv --output new_era_scraped.csv
"""

import argparse
import pandas as pd
import sys
import os

# Add lib to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.scraper import scrape_feed_urls, compare_feed_vs_scraped


def main():
    parser = argparse.ArgumentParser(description="Scrape product pages from feed URLs")
    parser.add_argument("feed_file", help="Path to feed file (CSV, TSV, or XLSX)")
    parser.add_argument("--max", type=int, default=None, help="Max products to scrape (default: all)")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds (default: 1.0)")
    parser.add_argument("--output", type=str, default=None, help="Output CSV path (default: <feed>_scraped.csv)")
    parser.add_argument("--url-col", type=str, default="link", help="Column name for product URL (default: link)")
    parser.add_argument("--id-col", type=str, default="id", help="Column name for SKU ID (default: id)")
    args = parser.parse_args()

    # Load feed
    feed_path = args.feed_file
    print(f"Loading feed: {feed_path}")

    if feed_path.endswith(".xlsx") or feed_path.endswith(".xls"):
        feed = pd.read_excel(feed_path)
    elif feed_path.endswith(".tsv"):
        feed = pd.read_csv(feed_path, sep="\t", low_memory=False)
    else:
        feed = pd.read_csv(feed_path, low_memory=False)

    print(f"Feed loaded: {len(feed)} products")

    # Count URLs available
    url_count = feed[args.url_col].notna().sum()
    scrape_count = min(url_count, args.max) if args.max else url_count
    print(f"URLs available: {url_count}")
    print(f"Will scrape: {scrape_count} products")
    print(f"Estimated time: ~{scrape_count * args.delay:.0f}s ({scrape_count * args.delay / 60:.1f} min)")
    print()

    # Progress callback
    def progress(current, total):
        pct = current / total * 100
        bar = "=" * int(pct / 2) + "-" * (50 - int(pct / 2))
        print(f"\r  [{bar}] {current}/{total} ({pct:.0f}%)", end="", flush=True)

    # Scrape
    scraped = scrape_feed_urls(
        feed,
        url_col=args.url_col,
        id_col=args.id_col,
        max_products=args.max,
        delay=args.delay,
        progress_callback=progress,
    )

    print()  # newline after progress bar
    print()

    # Stats
    ok_count = (scraped["scrape_status"] == "ok").sum()
    fail_count = len(scraped) - ok_count
    has_desc = (scraped["page_description"].fillna("").str.len() > 0).sum()
    has_features = (scraped["features"].fillna("").str.len() > 0).sum()
    has_materials = (scraped["materials"].fillna("").str.len() > 0).sum()

    print("=== SCRAPE RESULTS ===")
    print(f"  Successful: {ok_count}/{len(scraped)}")
    if fail_count > 0:
        print(f"  Failed: {fail_count}")
        for status, count in scraped["scrape_status"].value_counts().items():
            if status != "ok":
                print(f"    - {status}: {count}")
    print(f"  With description: {has_desc}")
    print(f"  With features: {has_features}")
    print(f"  With materials: {has_materials}")

    # Compare with feed
    print()
    print("=== FEED vs PAGE COMPARISON ===")
    comparison = compare_feed_vs_scraped(feed, scraped, id_col=args.id_col)
    if len(comparison) > 0:
        avg_feed_desc = comparison["feed_desc_len"].mean()
        avg_page_desc = comparison["page_desc_len"].mean()
        richer_page = (comparison["desc_delta"] > 50).sum()
        print(f"  Avg feed description length: {avg_feed_desc:.0f} chars")
        print(f"  Avg page description length: {avg_page_desc:.0f} chars")
        print(f"  Products with richer page descriptions: {richer_page}/{len(comparison)}")
        print(f"  Products with features on page: {comparison['has_features'].sum()}")

    # Save output
    output_path = args.output
    if not output_path:
        base = os.path.splitext(os.path.basename(feed_path))[0]
        output_path = f"{base}_scraped.csv"

    scraped.to_csv(output_path, index=False)
    print(f"\nSaved to: {output_path}")

    # Show sample
    print()
    print("=== SAMPLE SCRAPED DATA (first 3) ===")
    for _, row in scraped.head(3).iterrows():
        print(f"  SKU: {row['sku_id'][:50]}...")
        print(f"  Page title: {row['page_title'][:80]}")
        desc = row["page_description"][:150] if row["page_description"] else "(empty)"
        print(f"  Description: {desc}")
        if row["features"]:
            print(f"  Features: {row['features'][:100]}")
        if row["materials"]:
            print(f"  Materials: {row['materials']}")
        print()


if __name__ == "__main__":
    main()
