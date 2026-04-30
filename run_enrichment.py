"""
Feed Enrichment - Runner Script
================================
Enriches a GMC feed export with search term intelligence
for use in the V3 template description prompts.

Usage:
    python run_enrichment.py <feed_file> <search_terms_file> [--output enriched.csv]

Examples:
    python run_enrichment.py products.tsv search_terms.xlsx
    python run_enrichment.py products.tsv search_terms.xlsx --output new_era_enriched.csv
    python run_enrichment.py products.csv search_terms.csv --min-impressions 20
"""

import argparse
import pandas as pd
import sys
import os
import time

# Add lib to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.search_terms import (
    match_search_terms_to_skus,
    aggregate_for_sku,
    build_prompt_context,
    summarise_search_coverage,
)


def load_file(path):
    """Load a CSV, TSV, or XLSX file into a DataFrame."""
    if path.endswith(".xlsx") or path.endswith(".xls"):
        return pd.read_excel(path)
    elif path.endswith(".tsv"):
        return pd.read_csv(path, sep="\t", low_memory=False)
    else:
        return pd.read_csv(path, low_memory=False)


def main():
    parser = argparse.ArgumentParser(
        description="Enrich a product feed with Google Ads search term intelligence"
    )
    parser.add_argument("feed_file", help="Path to GMC feed export (CSV, TSV, or XLSX)")
    parser.add_argument("search_terms_file", help="Path to Supermetrics search terms export (CSV or XLSX)")
    parser.add_argument("--output", type=str, default=None, help="Output file path (default: <feed>_enriched.csv)")
    parser.add_argument("--min-impressions", type=int, default=10, help="Min impressions filter for search terms (default: 10)")
    parser.add_argument("--relevance-threshold", type=float, default=0.3, help="Min relevance score for n-gram matching (default: 0.3)")
    parser.add_argument("--id-col", type=str, default="id", help="Feed column for SKU ID (default: id)")
    parser.add_argument("--title-col", type=str, default="title", help="Feed column for product title (default: title)")
    args = parser.parse_args()

    print("=" * 60)
    print("  FEED ENRICHMENT - Search Term Intelligence")
    print("=" * 60)
    print()

    # --- Load files ---
    print(f"Loading feed: {args.feed_file}")
    feed = load_file(args.feed_file)
    print(f"  {len(feed)} products loaded")

    print(f"Loading search terms: {args.search_terms_file}")
    search_terms = load_file(args.search_terms_file)
    print(f"  {len(search_terms)} search terms loaded")
    print()

    # --- Match n-grams to SKUs ---
    print("Matching search term n-grams to products...")
    t0 = time.time()
    matched = match_search_terms_to_skus(
        search_terms,
        feed,
        min_impressions=args.min_impressions,
        relevance_threshold=args.relevance_threshold,
        feed_id_col=args.id_col,
        feed_title_col=args.title_col,
    )
    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s")
    print(f"  {matched['search_term'].nunique()} unique n-grams matched to {matched['sku_id'].nunique()} SKUs")
    print()

    # --- Coverage summary ---
    coverage = summarise_search_coverage(feed, matched)
    print("COVERAGE SUMMARY:")
    print(f"  Total SKUs in feed:        {coverage['total_skus']}")
    print(f"  SKUs with search data:     {coverage['skus_with_search_data']}")
    print(f"  Coverage:                  {coverage['coverage_pct']}%")
    print(f"  Unique n-grams matched:    {coverage['total_unique_terms']}")
    print(f"  Converting n-grams:        {coverage['converting_terms']}")
    print()

    # --- Build search context for each SKU ---
    print("Building search intelligence for each product...")
    search_contexts = {}
    keyword_themes_compact = {}
    sku_ids = feed[args.id_col].astype(str).unique()

    for i, sku_id in enumerate(sku_ids):
        if (i + 1) % 500 == 0 or i == 0:
            print(f"  Processing {i + 1}/{len(sku_ids)}...")

        ctx = aggregate_for_sku(sku_id, matched)
        prompt_block = build_prompt_context({"id": sku_id}, ctx)
        search_contexts[sku_id] = prompt_block

        # Compact theme list for the keyword_themes column
        themes = ctx.get("keyword_themes", [])
        if themes:
            compact = ", ".join(t["keyword"] for t in themes[:5])
            keyword_themes_compact[sku_id] = compact
        else:
            keyword_themes_compact[sku_id] = ""

    print(f"  Done - {len(search_contexts)} products processed")
    print()

    # --- Add columns to feed ---
    enriched = feed.copy()
    enriched["search_context"] = enriched[args.id_col].astype(str).map(search_contexts).fillna("")
    enriched["keyword_themes"] = enriched[args.id_col].astype(str).map(keyword_themes_compact).fillna("")

    # Stats on enrichment
    has_context = (enriched["search_context"].str.len() > 50).sum()
    has_themes = (enriched["keyword_themes"].str.len() > 0).sum()
    print("ENRICHMENT RESULTS:")
    print(f"  Products with search context: {has_context}/{len(enriched)}")
    print(f"  Products with keyword themes: {has_themes}/{len(enriched)}")
    print()

    # --- Save output ---
    output_path = args.output
    if not output_path:
        base = os.path.splitext(os.path.basename(args.feed_file))[0]
        output_path = f"{base}_enriched.csv"

    enriched.to_csv(output_path, index=False)
    print(f"Saved enriched feed to: {output_path}")
    print(f"  New columns added: 'search_context', 'keyword_themes'")
    print()

    # --- Show examples ---
    print("=" * 60)
    print("  SAMPLE OUTPUT (3 products)")
    print("=" * 60)

    # Pick products with the richest search context
    samples = enriched[enriched["keyword_themes"].str.len() > 0].head(3)
    if len(samples) == 0:
        samples = enriched.head(3)

    for _, row in samples.iterrows():
        title = str(row.get(args.title_col, ""))[:70]
        themes = row["keyword_themes"]
        print(f"\n  Title: {title}")
        print(f"  Keyword themes: {themes}")
        # Show first 3 lines of search context
        ctx_lines = row["search_context"].split("\n")[:4]
        for line in ctx_lines:
            print(f"    {line}")
        if len(row["search_context"].split("\n")) > 4:
            print(f"    ... ({len(row['search_context'])} chars total)")

    print()
    print("Done! Load the enriched CSV into your V3 template.")
    print("The 'search_context' column goes into the description prompt.")


if __name__ == "__main__":
    main()
