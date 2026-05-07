"""
Product Page Scraper - Runner Script
=====================================
Run this locally to scrape product pages from a feed export.
Supports resumable scraping with checkpoint files.

Usage:
    python run_scraper.py <feed_file> [--max 100] [--delay 1.0] [--output scraped.csv]

    # Resume an interrupted scrape (auto-detects checkpoint)
    python run_scraper.py products.xlsx --resume

    # Scrape first 10 products (test run)
    python run_scraper.py products.tsv --max 10

    # Full scrape with resume support (saves every 25 products)
    python run_scraper.py products.xlsx --resume --checkpoint-every 25

    # Run in background (tmux/screen recommended for long jobs)
    nohup python run_scraper.py products.xlsx --resume > scrape.log 2>&1 &

The output CSV can be uploaded back into the Streamlit app's Page Scraper
tab to skip re-scraping and go straight to AI enrichment.
"""

import argparse
import pandas as pd
import sys
import os

# Add lib to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.scraper import (
    scrape_feed_urls,
    scrape_feed_urls_resumable,
    get_checkpoint_info,
    compare_feed_vs_scraped,
)


def build_scraper_output(row):
    """Consolidate scraped fields into a single text block (matches Streamlit format)."""
    parts = []
    desc = row.get("page_description", "")
    if desc and str(desc).strip() and str(desc).lower() != "nan":
        parts.append(f"PAGE DESCRIPTION:\n{str(desc).strip()}")

    features = row.get("features", "")
    if features and str(features).strip() and str(features).lower() != "nan":
        items = str(features).split(" | ")
        parts.append("FEATURES:\n" + "\n".join(f"- {f}" for f in items))

    materials = row.get("materials", "")
    if materials and str(materials).strip() and str(materials).lower() != "nan":
        parts.append(f"MATERIALS: {str(materials).strip()}")

    additional = row.get("additional_info", "")
    if additional and str(additional).strip() and str(additional).lower() != "nan":
        items = str(additional).split(" | ")
        parts.append("ADDITIONAL INFO:\n" + "\n".join(f"- {a}" for a in items))

    return "\n\n".join(parts) if parts else ""


def main():
    parser = argparse.ArgumentParser(
        description="Scrape product pages from feed URLs (with resume support)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_scraper.py products.xlsx --max 10           # Test run
  python run_scraper.py products.xlsx --resume           # Full run with resume
  python run_scraper.py products.xlsx --resume --max 500 # Scrape 500 with resume
  python run_scraper.py products.xlsx --enrichment-output # Output 5-col format
        """,
    )
    parser.add_argument("feed_file", help="Path to feed file (CSV, TSV, or XLSX)")
    parser.add_argument("--max", type=int, default=None, help="Max products to scrape (default: all)")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds (default: 1.0)")
    parser.add_argument("--output", type=str, default=None, help="Output CSV path (default: <feed>_scraped.csv)")
    parser.add_argument("--url-col", type=str, default="link", help="Column name for product URL (default: link)")
    parser.add_argument("--id-col", type=str, default="id", help="Column name for SKU ID (default: id)")
    parser.add_argument("--title-col", type=str, default="title", help="Column name for title (default: title)")
    parser.add_argument("--resume", action="store_true", help="Enable resumable scraping with checkpoint file")
    parser.add_argument("--checkpoint", type=str, default=None, help="Checkpoint file path (default: <feed>_checkpoint.csv)")
    parser.add_argument("--checkpoint-every", type=int, default=25, help="Save checkpoint every N products (default: 25)")
    parser.add_argument("--enrichment-output", action="store_true", help="Also output 5-column enrichment format for Streamlit")
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

    # Checkpoint path
    base = os.path.splitext(os.path.basename(feed_path))[0]
    checkpoint_path = args.checkpoint or f"{base}_checkpoint.csv"

    # Check for existing checkpoint
    if args.resume:
        info = get_checkpoint_info(checkpoint_path)
        if info["exists"]:
            print(f"\nFound checkpoint: {info['count']} products already scraped")
            print(f"  Successful: {info['ok_count']}")
            print(f"  Failed: {info['failed_count']}")
            remaining = scrape_count - info["count"]
            if remaining <= 0:
                print(f"\nAll {scrape_count} products already scraped. Nothing to do.")
                print(f"Delete {checkpoint_path} to start fresh.")
                # Still produce output from checkpoint
                scraped = pd.read_csv(checkpoint_path, low_memory=False)
                _save_outputs(scraped, feed, args, base)
                return
            print(f"  Remaining: ~{remaining}")
            print(f"  Estimated time: ~{remaining * args.delay / 60:.1f} min")
        else:
            print(f"\nNo checkpoint found. Starting fresh.")
            print(f"Will scrape: {scrape_count} products")
            print(f"Estimated time: ~{scrape_count * args.delay:.0f}s ({scrape_count * args.delay / 60:.1f} min)")
            print(f"Checkpoint saves every {args.checkpoint_every} products to: {checkpoint_path}")
    else:
        print(f"URLs available: {url_count}")
        print(f"Will scrape: {scrape_count} products")
        print(f"Estimated time: ~{scrape_count * args.delay:.0f}s ({scrape_count * args.delay / 60:.1f} min)")

    print()

    # Progress callback
    if args.resume:
        def progress(current, total, resumed):
            pct = current / total * 100
            bar = "=" * int(pct / 2) + "-" * (50 - int(pct / 2))
            label = f" (resumed {resumed})" if resumed else ""
            print(f"\r  [{bar}] {current}/{total} ({pct:.0f}%){label}", end="", flush=True)

        scraped = scrape_feed_urls_resumable(
            feed,
            url_col=args.url_col,
            id_col=args.id_col,
            max_products=args.max,
            delay=args.delay,
            checkpoint_path=checkpoint_path,
            checkpoint_every=args.checkpoint_every,
            progress_callback=progress,
        )
    else:
        def progress(current, total):
            pct = current / total * 100
            bar = "=" * int(pct / 2) + "-" * (50 - int(pct / 2))
            print(f"\r  [{bar}] {current}/{total} ({pct:.0f}%)", end="", flush=True)

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

    _save_outputs(scraped, feed, args, base)

    # Clean up checkpoint on successful completion
    if args.resume and os.path.exists(checkpoint_path):
        print(f"\nScrape complete. Checkpoint file kept at: {checkpoint_path}")
        print(f"  (Delete it to start fresh next time)")


def _save_outputs(scraped, feed, args, base):
    """Print stats and save output files."""
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
    try:
        comparison = compare_feed_vs_scraped(feed, scraped, id_col=args.id_col)
        if len(comparison) > 0:
            avg_feed_desc = comparison["feed_desc_len"].mean()
            avg_page_desc = comparison["page_desc_len"].mean()
            richer_page = (comparison["desc_delta"] > 50).sum()
            print(f"  Avg feed description length: {avg_feed_desc:.0f} chars")
            print(f"  Avg page description length: {avg_page_desc:.0f} chars")
            print(f"  Products with richer page descriptions: {richer_page}/{len(comparison)}")
            print(f"  Products with features on page: {comparison['has_features'].sum()}")
    except Exception as e:
        print(f"  Could not compare: {e}")

    # Save raw scraped output
    output_path = args.output or f"{base}_scraped.csv"
    scraped.to_csv(output_path, index=False)
    print(f"\nSaved raw scrape to: {output_path}")

    # Save enrichment-format output (matches Streamlit 5-column structure)
    if args.enrichment_output:
        scraped["scraper_output"] = scraped.apply(build_scraper_output, axis=1)

        enrichment = feed[[args.id_col, args.title_col]].copy()
        enrichment.columns = ["id", "title"]
        enrichment["id"] = enrichment["id"].astype(str)

        scraper_map = scraped.set_index("sku_id")["scraper_output"].to_dict()
        enrichment["scraper_output"] = enrichment["id"].map(scraper_map).fillna("")
        enrichment["search_context"] = ""
        enrichment["ai_brief"] = ""

        enrichment_path = f"{base}_enrichment.csv"
        enrichment.to_csv(enrichment_path, index=False)
        print(f"Saved enrichment format to: {enrichment_path}")
        print(f"  (Upload this to the Streamlit app's Output tab)")

    # Show sample
    print()
    print("=== SAMPLE SCRAPED DATA (first 3) ===")
    for _, row in scraped.head(3).iterrows():
        sku_str = str(row["sku_id"])
        print(f"  SKU: {sku_str[:50]}...")
        page_title = str(row["page_title"]) if row["page_title"] else ""
        print(f"  Page title: {page_title[:80]}")
        desc = str(row["page_description"])[:150] if row["page_description"] else "(empty)"
        print(f"  Description: {desc}")
        features = row.get("features", "")
        if features and str(features).strip():
            print(f"  Features: {str(features)[:100]}")
        materials = row.get("materials", "")
        if materials and str(materials).strip():
            print(f"  Materials: {materials}")
        print()


if __name__ == "__main__":
    main()
