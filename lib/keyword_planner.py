"""
Google Ads Keyword Planner Integration
=======================================
Pulls search volume and competition data from Google Ads
Keyword Planner API. Uses the official google-ads Python library.

Two modes:
  1. Search Volume Lookup - enrich existing n-grams with monthly
     search volume, competition, and bid estimates.
  2. Keyword Ideas - generate related keyword suggestions for
     seed terms (product titles, categories).

Requirements:
  pip install google-ads>=24.0.0

Credentials needed:
  - Google Ads developer token (from API Center in Google Ads)
  - OAuth2 client ID + client secret (from Google Cloud Console)
  - OAuth2 refresh token (generated once via google-ads auth flow)
  - Customer ID (Google Ads account, 10-digit, no dashes)
  - Login customer ID (MCC account, if using manager account)

Pattern teams: ask your Google Ads manager for the developer
token and MCC customer ID. OAuth credentials come from the
Pattern Google Cloud project.
"""

import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GoogleAdsCredentials:
    """Credentials for Google Ads API access."""
    developer_token: str
    client_id: str
    client_secret: str
    refresh_token: str
    customer_id: str  # 10-digit, no dashes
    login_customer_id: str = ""  # MCC account ID (optional)

    def to_dict(self) -> dict:
        """Convert to google-ads client config dict."""
        config = {
            "developer_token": self.developer_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "use_proto_plus": True,
        }
        if self.login_customer_id:
            config["login_customer_id"] = self.login_customer_id.replace("-", "")
        return config


@dataclass
class KeywordMetrics:
    """Search volume and competition data for a keyword."""
    keyword: str
    avg_monthly_searches: int = 0
    competition: str = ""  # LOW, MEDIUM, HIGH
    competition_index: int = 0  # 0-100
    low_top_of_page_bid: float = 0.0  # micros -> dollars
    high_top_of_page_bid: float = 0.0
    monthly_search_volumes: list = field(default_factory=list)


# ============================================================
# CLIENT INITIALIZATION
# ============================================================

def get_google_ads_client(credentials: GoogleAdsCredentials):
    """
    Create a Google Ads API client from credentials.

    Returns:
        GoogleAdsClient instance, or None if library not installed.
    """
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError:
        logger.error(
            "google-ads library not installed. "
            "Run: pip install google-ads>=24.0.0"
        )
        return None

    try:
        client = GoogleAdsClient.load_from_dict(credentials.to_dict())
        return client
    except Exception as e:
        logger.error(f"Failed to create Google Ads client: {e}")
        return None


# ============================================================
# SEARCH VOLUME LOOKUP (batch)
# ============================================================

def get_search_volume(
    keywords: list[str],
    credentials: GoogleAdsCredentials,
    language_id: str = "1000",  # English
    geo_target_id: str = "2036",  # Australia
    batch_size: int = 200,
) -> dict[str, KeywordMetrics]:
    """
    Look up search volume for a list of keywords using the
    Keyword Planner's GenerateKeywordHistoricalMetrics endpoint.

    This is the batch volume lookup - you provide specific keywords
    and get back their monthly search volume, competition, and bids.

    Args:
        keywords: List of keyword strings to look up.
        credentials: Google Ads API credentials.
        language_id: Google Ads language constant ID.
            1000 = English, 1008 = Chinese, 1014 = French, etc.
        geo_target_id: Google Ads geo target constant ID.
            2036 = Australia, 2554 = New Zealand, 2840 = United States,
            2826 = United Kingdom.
        batch_size: Max keywords per API call (API limit ~10,000).

    Returns:
        Dict mapping keyword -> KeywordMetrics.
        Keywords not found in Keyword Planner are omitted.
    """
    client = get_google_ads_client(credentials)
    if not client:
        return {}

    customer_id = credentials.customer_id.replace("-", "")
    results = {}

    # Process in batches
    for i in range(0, len(keywords), batch_size):
        batch = keywords[i:i + batch_size]

        try:
            batch_results = _fetch_historical_metrics(
                client, customer_id, batch,
                language_id, geo_target_id,
            )
            results.update(batch_results)
        except Exception as e:
            logger.error(f"Keyword Planner batch {i}-{i+len(batch)} failed: {e}")
            continue

    return results


def _fetch_historical_metrics(
    client,
    customer_id: str,
    keywords: list[str],
    language_id: str,
    geo_target_id: str,
) -> dict[str, KeywordMetrics]:
    """Call GenerateKeywordHistoricalMetrics for a batch of keywords."""
    keyword_plan_idea_service = client.get_service("KeywordPlanIdeaService")

    request = client.get_type("GenerateKeywordHistoricalMetricsRequest")
    request.customer_id = customer_id
    request.keywords = keywords
    request.language = f"languageConstants/{language_id}"
    request.geo_target_constants = [f"geoTargetConstants/{geo_target_id}"]

    try:
        response = keyword_plan_idea_service.generate_keyword_historical_metrics(
            request=request
        )
    except Exception as e:
        logger.error(f"API call failed: {e}")
        raise

    results = {}
    for result in response.results:
        keyword = result.text
        metrics = result.keyword_metrics

        # Convert competition enum to string
        competition_str = ""
        if hasattr(metrics, "competition"):
            comp_val = metrics.competition
            comp_map = {0: "UNSPECIFIED", 1: "UNKNOWN", 2: "LOW", 3: "MEDIUM", 4: "HIGH"}
            competition_str = comp_map.get(comp_val, str(comp_val))

        # Convert micros to dollars for bid estimates
        low_bid = getattr(metrics, "low_top_of_page_bid_micros", 0) or 0
        high_bid = getattr(metrics, "high_top_of_page_bid_micros", 0) or 0

        # Monthly search volumes (last 12 months if available)
        monthly = []
        if hasattr(metrics, "monthly_search_volumes"):
            for m in metrics.monthly_search_volumes:
                monthly.append({
                    "year": m.year,
                    "month": m.month,
                    "searches": m.monthly_searches,
                })

        results[keyword] = KeywordMetrics(
            keyword=keyword,
            avg_monthly_searches=getattr(metrics, "avg_monthly_searches", 0) or 0,
            competition=competition_str,
            competition_index=getattr(metrics, "competition_index", 0) or 0,
            low_top_of_page_bid=low_bid / 1_000_000,
            high_top_of_page_bid=high_bid / 1_000_000,
            monthly_search_volumes=monthly,
        )

    return results


# ============================================================
# KEYWORD IDEAS (discover new keywords from seeds)
# ============================================================

def get_keyword_ideas(
    seed_keywords: list[str],
    credentials: GoogleAdsCredentials,
    language_id: str = "1000",
    geo_target_id: str = "2036",
    max_results: int = 50,
    include_adult: bool = False,
) -> list[KeywordMetrics]:
    """
    Generate keyword ideas from seed keywords using the
    Keyword Planner's GenerateKeywordIdeas endpoint.

    Useful for discovering related search terms that shoppers
    use but aren't in the current search term data.

    Args:
        seed_keywords: 1-20 seed keywords (product titles, categories).
        credentials: Google Ads API credentials.
        language_id: Language constant ID.
        geo_target_id: Geo target constant ID.
        max_results: Max keyword ideas to return.
        include_adult: Include adult keyword suggestions.

    Returns:
        List of KeywordMetrics sorted by avg_monthly_searches desc.
    """
    client = get_google_ads_client(credentials)
    if not client:
        return []

    customer_id = credentials.customer_id.replace("-", "")

    keyword_plan_idea_service = client.get_service("KeywordPlanIdeaService")

    request = client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = customer_id
    request.language = f"languageConstants/{language_id}"
    request.geo_target_constants = [f"geoTargetConstants/{geo_target_id}"]
    request.include_adult_keywords = include_adult

    # Use keyword seed
    request.keyword_seed.keywords.extend(seed_keywords[:20])

    try:
        response = keyword_plan_idea_service.generate_keyword_ideas(
            request=request
        )
    except Exception as e:
        logger.error(f"Keyword Ideas API call failed: {e}")
        return []

    ideas = []
    for result in response.results:
        metrics = result.keyword_idea_metrics

        competition_str = ""
        if hasattr(metrics, "competition"):
            comp_val = metrics.competition
            comp_map = {0: "UNSPECIFIED", 1: "UNKNOWN", 2: "LOW", 3: "MEDIUM", 4: "HIGH"}
            competition_str = comp_map.get(comp_val, str(comp_val))

        low_bid = getattr(metrics, "low_top_of_page_bid_micros", 0) or 0
        high_bid = getattr(metrics, "high_top_of_page_bid_micros", 0) or 0

        ideas.append(KeywordMetrics(
            keyword=result.text,
            avg_monthly_searches=getattr(metrics, "avg_monthly_searches", 0) or 0,
            competition=competition_str,
            competition_index=getattr(metrics, "competition_index", 0) or 0,
            low_top_of_page_bid=low_bid / 1_000_000,
            high_top_of_page_bid=high_bid / 1_000_000,
        ))

    # Sort by volume descending
    ideas.sort(key=lambda x: x.avg_monthly_searches, reverse=True)
    return ideas[:max_results]


# ============================================================
# SEARCH TERMS REPORT (pull directly from Google Ads)
# ============================================================

def pull_search_terms_report(
    credentials: GoogleAdsCredentials,
    date_range: str = "LAST_30_DAYS",
    campaign_ids: Optional[list[str]] = None,
    min_impressions: int = 1,
) -> list[dict]:
    """
    Pull search terms report directly from Google Ads API.
    Alternative to Supermetrics CSV export.

    Args:
        credentials: Google Ads API credentials.
        date_range: Predefined date range (LAST_7_DAYS, LAST_30_DAYS,
            LAST_90_DAYS, THIS_MONTH, LAST_MONTH, etc.)
        campaign_ids: Optional list of campaign IDs to filter.
        min_impressions: Filter out low-impression terms.

    Returns:
        List of dicts with: search_term, impressions, clicks, ctr,
        conversions, conv_value, cost, campaign_name.
    """
    client = get_google_ads_client(credentials)
    if not client:
        return []

    customer_id = credentials.customer_id.replace("-", "")
    ga_service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            search_term_view.search_term,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.conversions,
            metrics.conversions_value,
            metrics.cost_micros,
            campaign.name,
            campaign.id
        FROM search_term_view
        WHERE segments.date DURING {date_range}
            AND metrics.impressions >= {min_impressions}
    """

    if campaign_ids:
        ids_str = ", ".join(f"'{c}'" for c in campaign_ids)
        query += f" AND campaign.id IN ({ids_str})"

    query += " ORDER BY metrics.impressions DESC LIMIT 10000"

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
    except Exception as e:
        logger.error(f"Search Terms Report query failed: {e}")
        return []

    results = []
    for row in response:
        results.append({
            "search_term": row.search_term_view.search_term,
            "impressions": row.metrics.impressions,
            "clicks": row.metrics.clicks,
            "ctr": round(row.metrics.ctr, 4),
            "conversions": round(row.metrics.conversions, 1),
            "conv_value": round(row.metrics.conversions_value, 2),
            "cost": round(row.metrics.cost_micros / 1_000_000, 2),
            "campaign_name": row.campaign.name,
            "campaign_id": str(row.campaign.id),
        })

    return results


# ============================================================
# GEO TARGETS - common regions for Pattern clients
# ============================================================

GEO_TARGETS = {
    "Australia": "2036",
    "New Zealand": "2554",
    "United States": "2840",
    "United Kingdom": "2826",
    "Canada": "2124",
    "Germany": "2276",
    "France": "2250",
    "Japan": "2392",
}

LANGUAGES = {
    "English": "1000",
    "French": "1002",
    "German": "1001",
    "Japanese": "1005",
    "Chinese (Simplified)": "1017",
    "Spanish": "1003",
}


# ============================================================
# ENRICHMENT HELPER - merge volume into matched n-grams
# ============================================================

def enrich_matched_terms_with_volume(
    matched_df,
    credentials: GoogleAdsCredentials,
    language_id: str = "1000",
    geo_target_id: str = "2036",
    progress_callback=None,
) -> tuple:
    """
    Take the matched n-grams DataFrame from search_terms.py and
    enrich it with Keyword Planner search volume data.

    Adds columns: avg_monthly_searches, competition, competition_index,
    top_of_page_bid_low, top_of_page_bid_high.

    Args:
        matched_df: Output from match_search_terms_to_skus().
        credentials: Google Ads API credentials.
        language_id: Language constant ID.
        geo_target_id: Geo target constant ID.
        progress_callback: Optional callable(status_text).

    Returns:
        (enriched_df, stats_dict) - enriched DataFrame and summary stats.
    """
    import pandas as pd

    if matched_df.empty:
        return matched_df, {"keywords_looked_up": 0, "keywords_with_volume": 0}

    # Get unique n-grams to look up
    unique_keywords = matched_df["search_term"].unique().tolist()

    if progress_callback:
        progress_callback(f"Looking up search volume for {len(unique_keywords):,} keywords...")

    # Fetch search volume
    volume_data = get_search_volume(
        unique_keywords,
        credentials,
        language_id=language_id,
        geo_target_id=geo_target_id,
    )

    if progress_callback:
        progress_callback(f"Got volume data for {len(volume_data):,}/{len(unique_keywords):,} keywords")

    # Build lookup dict
    volume_lookup = {}
    for kw, metrics in volume_data.items():
        volume_lookup[kw] = {
            "avg_monthly_searches": metrics.avg_monthly_searches,
            "competition": metrics.competition,
            "competition_index": metrics.competition_index,
            "top_of_page_bid_low": round(metrics.low_top_of_page_bid, 2),
            "top_of_page_bid_high": round(metrics.high_top_of_page_bid, 2),
        }

    # Merge into matched_df
    enriched = matched_df.copy()
    for col in ["avg_monthly_searches", "competition", "competition_index",
                 "top_of_page_bid_low", "top_of_page_bid_high"]:
        enriched[col] = enriched["search_term"].map(
            lambda kw, c=col: volume_lookup.get(kw, {}).get(c, 0 if c != "competition" else "")
        )

    stats = {
        "keywords_looked_up": len(unique_keywords),
        "keywords_with_volume": len(volume_data),
        "total_monthly_searches": sum(m.avg_monthly_searches for m in volume_data.values()),
        "avg_monthly_searches": (
            round(sum(m.avg_monthly_searches for m in volume_data.values()) / max(len(volume_data), 1))
            if volume_data else 0
        ),
    }

    return enriched, stats
