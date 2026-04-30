"""
Search Term Aggregation & Keyword Theme Engine
===============================================
Core module for the performance-driven feed optimisation pipeline.

Aggregates Google Ads search term data per SKU and extracts
recurring keyword themes from converting search terms.

Data flow:
  Supermetrics export (CSV/XLSX) -> relevance matching to feed SKUs
    -> per-SKU search term aggregation
    -> keyword theme extraction
    -> prompt enrichment context

Expected Supermetrics columns (auto-mapped):
  "Matched search term" | "Search term" | "Searchterm"
  "Impressions"
  "Clicks"
  "CTR"
  "Conversions"
  "Total conversion value" | "Conv. value" | "ConversionValue"
  "Cost"
"""

import pandas as pd
from collections import Counter
from typing import Optional


# ============================================================
# STOPWORDS - filtered from theme extraction
# ============================================================
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "is", "it", "this", "that",
    "are", "was", "be", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "can", "not", "no",
    "so", "if", "my", "your", "his", "her", "its", "our", "their",
    "buy", "online", "shop", "store", "best", "good", "new", "free",
    "au", "australia", "nz",
}


# ============================================================
# COLUMN MAPPING - handles Supermetrics naming variations
# ============================================================

_COLUMN_ALIASES = {
    "search_term": ["Matched search term", "Search term", "Searchterm", "search_term"],
    "impressions": ["Impressions", "impressions", "Impr."],
    "clicks": ["Clicks", "clicks"],
    "ctr": ["CTR", "Ctr", "ctr"],
    "conversions": ["Conversions", "conversions", "Conv."],
    "conv_value": ["Total conversion value", "Conv. value", "ConversionValue", "conv_value", "Revenue"],
    "cost": ["Cost", "cost", "Costs"],
}


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map Supermetrics column names to internal standard names."""
    rename_map = {}
    for standard_name, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in df.columns:
                rename_map[alias] = standard_name
                break
    return df.rename(columns=rename_map)


# ============================================================
# 1. SEARCH TERM <-> SKU MATCHING (relevance-based, no campaign join)
# ============================================================

def match_search_terms_to_skus(
    search_term_df: pd.DataFrame,
    feed_df: pd.DataFrame,
    min_impressions: int = 10,
    relevance_threshold: float = 0.3,
    feed_id_col: str = "id",
    feed_title_col: str = "title",
    feed_product_type_col: str = "product type",
) -> pd.DataFrame:
    """
    Match search terms to individual SKUs using keyword relevance
    scoring between search term text and product title/attributes.

    No campaign join required - works for any campaign structure
    (broad, PMax, segmented, etc.).

    Args:
        search_term_df: Supermetrics search term export.
            Accepts various column naming conventions (auto-mapped).
        feed_df: GMC product feed export.
        min_impressions: Drop search terms below this threshold.
        relevance_threshold: Minimum relevance score (0-1) to keep a match.
            Higher = stricter matching. 0.3 is a good default.
        feed_id_col: Column name for SKU ID in feed.
        feed_title_col: Column name for product title in feed.
        feed_product_type_col: Column name for product type in feed.

    Returns:
        DataFrame with columns:
            sku_id, search_term, relevance_score,
            impressions, clicks, ctr, conversions, conv_value, cost
    """
    # Normalise column names from Supermetrics export
    st = _normalise_columns(search_term_df.copy())

    # Filter low-volume noise
    st = st[st["impressions"] >= min_impressions]

    # Pre-compute SKU word sets for fast matching
    feed_lookup = {}
    for _, row in feed_df.iterrows():
        sku_id = str(row[feed_id_col])
        title_words = _tokenise(str(row.get(feed_title_col, "")))

        product_type = str(row.get(feed_product_type_col, "")).lower()
        category_words = set(
            w.strip() for w in product_type.replace(">", " ").split()
            if len(w.strip()) > 2 and w.strip() not in STOPWORDS
        )

        # Also pull in color, brand, material if available
        extra_words = set()
        for col in ["color", "material", "brand"]:
            val = str(row.get(col, "")).lower()
            if val and val != "nan":
                extra_words.update(
                    w.strip() for w in val.split()
                    if len(w.strip()) > 2 and w.strip() not in STOPWORDS
                )

        feed_lookup[sku_id] = {
            "title_words": title_words,
            "category_words": category_words,
            "extra_words": extra_words,
            "all_words": title_words | category_words | extra_words,
        }

    # --- Step 1: Extract n-grams from search term corpus ---
    ngram_stats = _extract_ngram_stats(st)

    # --- Step 2: Filter n-grams by quality ---
    # Must appear in 2+ search terms and have meaningful words
    quality_ngrams = {
        ng: stats for ng, stats in ngram_stats.items()
        if stats["term_count"] >= 2
    }

    # --- Step 3: Build inverted index for feed ---
    word_to_skus = {}
    for sku_id, sku_info in feed_lookup.items():
        for word in sku_info["all_words"]:
            if word not in word_to_skus:
                word_to_skus[word] = set()
            word_to_skus[word].add(sku_id)

    total_skus = len(feed_lookup)

    # --- Step 4: Match n-grams to SKUs ---
    matches = []
    for ngram, stats in quality_ngrams.items():
        ngram_words = set(ngram.split())

        # Find candidate SKUs via inverted index
        candidate_skus = None
        for word in ngram_words:
            word_skus = word_to_skus.get(word, set())
            if candidate_skus is None:
                candidate_skus = word_skus.copy()
            else:
                candidate_skus &= word_skus  # intersect: SKU must have ALL words

        if not candidate_skus:
            continue

        # Specificity filter: skip n-grams that match too many SKUs
        # (these are brand-generic and don't differentiate)
        match_pct = len(candidate_skus) / total_skus
        if match_pct > 0.3:  # matches >30% of catalogue = too generic
            continue

        for sku_id in candidate_skus:
            sku_info = feed_lookup[sku_id]
            # Check n-gram words appear in title (strongest signal)
            title_hits = len(ngram_words & sku_info["title_words"])
            all_hits = len(ngram_words & sku_info["all_words"])

            if all_hits < len(ngram_words):
                continue  # not all n-gram words present

            # Relevance: prefer title matches over category/extra
            relevance = (title_hits / len(ngram_words)) * 0.7 + 0.3

            matches.append({
                "sku_id": sku_id,
                "ngram": ngram,
                "relevance_score": round(relevance, 3),
                "impressions": stats["impressions"],
                "clicks": stats["clicks"],
                "conversions": stats["conversions"],
                "conv_value": stats["conv_value"],
                "cost": stats["cost"],
                "term_count": stats["term_count"],
                "specificity": round(1 - match_pct, 3),
            })

    result = pd.DataFrame(matches)

    # Rename for backward compatibility with downstream functions
    if not result.empty:
        result = result.rename(columns={"ngram": "search_term"})

    return result


def _extract_ngram_stats(
    search_term_df: pd.DataFrame,
    max_n: int = 3,
) -> dict:
    """
    Extract unigrams, bigrams, and trigrams from search terms,
    aggregating their performance metrics.

    Returns:
        {
            "dodgers": {"impressions": ..., "clicks": ..., "conversions": ...,
                        "conv_value": ..., "cost": ..., "term_count": ...},
            "white sox": {...},
            "varsity jacket": {...},
            ...
        }
    """
    ngram_stats = {}

    for _, row in search_term_df.iterrows():
        text = str(row["search_term"]).lower()
        words = [w.strip(".,;:!?\"'()-/") for w in text.split()]
        words = [w for w in words if len(w) > 2 and w not in STOPWORDS]

        if not words:
            continue

        metrics = {
            "impressions": row.get("impressions", 0),
            "clicks": row.get("clicks", 0),
            "conversions": row.get("conversions", 0),
            "conv_value": row.get("conv_value", 0),
            "cost": row.get("cost", 0),
        }

        # Generate n-grams of size 1..max_n
        seen_in_this_term = set()
        for n in range(1, min(max_n + 1, len(words) + 1)):
            for i in range(len(words) - n + 1):
                ngram = " ".join(words[i:i+n])

                if ngram in seen_in_this_term:
                    continue
                seen_in_this_term.add(ngram)

                if ngram not in ngram_stats:
                    ngram_stats[ngram] = {
                        "impressions": 0,
                        "clicks": 0,
                        "conversions": 0,
                        "conv_value": 0,
                        "cost": 0,
                        "term_count": 0,
                    }

                stats = ngram_stats[ngram]
                for k, v in metrics.items():
                    stats[k] += v
                stats["term_count"] += 1

    return ngram_stats


# ============================================================
# 2. PER-SKU AGGREGATION
# ============================================================

def aggregate_for_sku(
    sku_id: str,
    matched_terms_df: pd.DataFrame,
    max_converting: int = 10,
    max_zero_conv: int = 5,
) -> dict:
    """
    Aggregate matched search terms for a single SKU into a
    prompt-ready context block.

    Returns:
        {
            "top_converting_terms": [...],
            "zero_conversion_terms": [...],
            "keyword_themes": [...],
            "total_matched_terms": int,
            "total_search_impressions": int,
            "total_search_conversions": int,
        }
    """
    sku_terms = matched_terms_df[matched_terms_df["sku_id"] == sku_id]

    if sku_terms.empty:
        return {
            "top_converting_terms": [],
            "zero_conversion_terms": [],
            "keyword_themes": [],
            "total_matched_terms": 0,
            "total_search_impressions": 0,
            "total_search_conversions": 0,
        }

    # Split into converting and non-converting
    converting = (
        sku_terms[sku_terms["conversions"] > 0]
        .sort_values("conv_value", ascending=False)
        .head(max_converting)
    )
    zero_conv = (
        sku_terms[(sku_terms["conversions"] == 0) & (sku_terms["impressions"] >= 20)]
        .sort_values("impressions", ascending=False)
        .head(max_zero_conv)
    )

    # Extract keyword themes from converting terms
    themes = extract_keyword_themes(converting.to_dict("records"))

    # Select available columns for output
    conv_cols = ["search_term", "impressions", "clicks", "conversions", "conv_value"]
    conv_cols = [c for c in conv_cols if c in converting.columns]
    if "ctr" in converting.columns:
        conv_cols.insert(3, "ctr")

    zero_cols = ["search_term", "impressions", "clicks"]
    zero_cols = [c for c in zero_cols if c in zero_conv.columns]

    return {
        "top_converting_terms": converting[conv_cols].to_dict("records"),
        "zero_conversion_terms": zero_conv[zero_cols].to_dict("records"),
        "keyword_themes": themes,
        "total_matched_terms": len(sku_terms),
        "total_search_impressions": int(sku_terms["impressions"].sum()),
        "total_search_conversions": int(sku_terms["conversions"].sum()),
    }


# ============================================================
# 3. KEYWORD THEME EXTRACTION
# ============================================================

def extract_keyword_themes(
    converting_terms: list[dict],
    max_themes: int = 8,
) -> list[dict]:
    """
    Identify recurring keyword patterns across converting search
    terms, weighted by conversion value.

    A "theme" is a word or bigram that appears across multiple
    converting search terms - it represents a concept shoppers
    use when they buy.

    Returns:
        [
            {
                "keyword": "wetsuit",
                "appears_in": 7,
                "pct_of_terms": 0.70,
                "total_conv_value": 1240.50,
                "avg_ctr": 0.032,
            },
            ...
        ]
    """
    if not converting_terms:
        return []

    n_terms = len(converting_terms)

    # Count unigrams weighted by conv_value
    word_stats = {}
    for term in converting_terms:
        words = _tokenise(term["search_term"])
        conv_val = term.get("conv_value", 0)
        ctr = term.get("ctr", 0)
        impressions = term.get("impressions", 0)

        for word in words:
            if word not in word_stats:
                word_stats[word] = {
                    "count": 0,
                    "total_conv_value": 0,
                    "total_impressions": 0,
                    "total_clicks": 0,
                }
            word_stats[word]["count"] += 1
            word_stats[word]["total_conv_value"] += conv_val
            word_stats[word]["total_impressions"] += impressions
            word_stats[word]["total_clicks"] += term.get("clicks", 0)

    # Also extract bigrams (two-word phrases)
    for term in converting_terms:
        words = term["search_term"].lower().split()
        conv_val = term.get("conv_value", 0)
        impressions = term.get("impressions", 0)

        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            if words[i] in STOPWORDS or words[i+1] in STOPWORDS:
                continue
            if len(words[i]) < 3 or len(words[i+1]) < 3:
                continue

            if bigram not in word_stats:
                word_stats[bigram] = {
                    "count": 0,
                    "total_conv_value": 0,
                    "total_impressions": 0,
                    "total_clicks": 0,
                }
            word_stats[bigram]["count"] += 1
            word_stats[bigram]["total_conv_value"] += conv_val
            word_stats[bigram]["total_impressions"] += impressions
            word_stats[bigram]["total_clicks"] += term.get("clicks", 0)

    # Score themes: frequency * conv_value
    themes = []
    for keyword, stats in word_stats.items():
        if stats["count"] < 2:  # must appear in 2+ terms
            continue
        avg_ctr = (
            stats["total_clicks"] / max(stats["total_impressions"], 1)
        )
        themes.append({
            "keyword": keyword,
            "appears_in": stats["count"],
            "pct_of_terms": round(stats["count"] / n_terms, 2),
            "total_conv_value": round(stats["total_conv_value"], 2),
            "avg_ctr": round(avg_ctr, 4),
        })

    # Sort by (frequency * conv_value) - want themes that are both
    # common and high-converting
    themes.sort(
        key=lambda t: t["appears_in"] * t["total_conv_value"],
        reverse=True,
    )

    # Deduplicate: if a bigram contains a unigram, keep the bigram
    # (more specific) and drop the unigram
    final = []
    seen_words = set()
    for theme in themes:
        words_in_theme = set(theme["keyword"].split())
        # Skip if this is a unigram that's already covered by a bigram
        if len(words_in_theme) == 1 and words_in_theme & seen_words:
            continue
        final.append(theme)
        seen_words.update(words_in_theme)
        if len(final) >= max_themes:
            break

    return final


# ============================================================
# 4. PROMPT CONTEXT BUILDER
# ============================================================

def build_prompt_context(
    sku_data: dict,
    search_context: dict,
) -> str:
    """
    Build the search intelligence block injected into the
    DESCRIPTION prompt for a specific SKU.

    Search data is used for descriptions only (backend, algorithm-facing).
    Titles remain brand-controlled and don't use search term injection.

    Args:
        sku_data: Product data dict (title, id, brand, etc.)
        search_context: Output from aggregate_for_sku()

    Returns:
        Formatted string to inject into the description prompt.
    """
    lines = []

    converting = search_context.get("top_converting_terms", [])
    zero_conv = search_context.get("zero_conversion_terms", [])
    themes = search_context.get("keyword_themes", [])

    if not converting and not themes:
        lines.append("SEARCH DATA: No search term data available for this product.")
        lines.append("Write the description using product attributes and best practices only.")
        return "\n".join(lines)

    # --- What shoppers search for when they buy this type of product ---
    if converting:
        lines.append("SEARCH INTELLIGENCE (from Google Ads - what real shoppers search):")
        lines.append("Top converting search keywords for this product:")
        for i, t in enumerate(converting[:7], 1):
            parts = [f"\"{t['search_term']}\""]
            parts.append(f"{int(t['impressions'])} impressions")
            if "clicks" in t:
                parts.append(f"{int(t['clicks'])} clicks")
            parts.append(f"{int(t['conversions'])} conversions")
            parts.append(f"${t['conv_value']:.0f} revenue")
            lines.append(f"  {i}. {', '.join(parts)}")

    # --- Themes to naturally weave into the description ---
    if themes:
        lines.append("")
        lines.append("KEY THEMES TO ADDRESS IN DESCRIPTION (by conversion data):")
        lines.append("Naturally weave these concepts into the description text.")
        lines.append("Do NOT keyword-stuff. Use them as topic guidance.")
        for i, theme in enumerate(themes[:5], 1):
            pct = f"{theme['pct_of_terms'] * 100:.0f}%"
            lines.append(
                f"  {i}. \"{theme['keyword']}\" - "
                f"appears in {pct} of converting searches, "
                f"${theme['total_conv_value']:.0f} total revenue"
            )

    # --- Terms to avoid (waste ad spend without converting) ---
    if zero_conv:
        lines.append("")
        lines.append("TERMS TO DE-EMPHASISE (high traffic, zero conversions):")
        lines.append("Avoid making these the focus of the description.")
        for t in zero_conv[:3]:
            lines.append(
                f"  - \"{t['search_term']}\" "
                f"({int(t['impressions'])} impressions, 0 conversions)"
            )

    return "\n".join(lines)


# ============================================================
# 5. FEED-LEVEL SUMMARY
# ============================================================

def summarise_search_coverage(
    feed_df: pd.DataFrame,
    matched_terms_df: pd.DataFrame,
) -> dict:
    """
    Summarise search term coverage across the entire feed.
    Used for the analysis dashboard and reporting.
    """
    total_skus = len(feed_df)
    skus_with_terms = matched_terms_df["sku_id"].nunique()
    total_terms = matched_terms_df["search_term"].nunique()
    converting_terms = matched_terms_df[
        matched_terms_df["conversions"] > 0
    ]["search_term"].nunique()

    return {
        "total_skus": total_skus,
        "skus_with_search_data": skus_with_terms,
        "coverage_pct": round(skus_with_terms / max(total_skus, 1) * 100, 1),
        "total_unique_terms": total_terms,
        "converting_terms": converting_terms,
        "total_search_impressions": int(matched_terms_df["impressions"].sum()),
        "total_search_conversions": int(matched_terms_df["conversions"].sum()),
        "total_search_revenue": round(matched_terms_df["conv_value"].sum(), 2),
    }


# ============================================================
# HELPERS
# ============================================================

def _tokenise(text: str) -> set[str]:
    """Tokenise text into meaningful words, removing stopwords."""
    words = set()
    for word in text.lower().split():
        # Strip common punctuation
        word = word.strip(".,;:!?\"'()-/")
        if len(word) > 2 and word not in STOPWORDS:
            words.add(word)
    return words
