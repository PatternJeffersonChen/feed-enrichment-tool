"""
Product Page Scraper
====================
Scrapes product URLs from the feed to extract richer content
than what's in the GMC export.

Clients often have more detailed descriptions, feature lists,
materials, and USPs on their product pages than in their feed.

Supports:
  - Shopify JSON endpoint (fastest, most reliable)
  - HTML parsing with BeautifulSoup (fallback)
  - Rate limiting to avoid getting blocked
  - Retry logic with exponential backoff

Usage:
    from lib.scraper import scrape_feed_urls
    scraped = scrape_feed_urls(feed_df, max_products=100)
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import time
import re
import logging
import os
from urllib.parse import urlparse, urljoin
from typing import Optional

logger = logging.getLogger(__name__)

# Default headers to look like a real browser
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json",
    "Accept-Language": "en-AU,en;q=0.9",
}


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def scrape_feed_urls(
    feed_df: pd.DataFrame,
    url_col: str = "link",
    id_col: str = "id",
    max_products: Optional[int] = None,
    delay: float = 1.0,
    timeout: int = 15,
    progress_callback=None,
) -> pd.DataFrame:
    """
    Scrape product pages for all URLs in the feed.

    Args:
        feed_df: Feed DataFrame with product URLs.
        url_col: Column containing the product URL.
        id_col: Column containing the SKU ID.
        max_products: Limit number of products to scrape (None = all).
        delay: Seconds between requests (rate limiting).
        timeout: Request timeout in seconds.
        progress_callback: Optional callable(current, total) for progress.

    Returns:
        DataFrame with columns:
            sku_id, page_title, page_description, features,
            materials, additional_info, scrape_status
    """
    results = []
    urls = feed_df[[id_col, url_col]].dropna(subset=[url_col])

    if max_products:
        urls = urls.head(max_products)

    total = len(urls)
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    # Detect platform from first URL
    first_url = urls[url_col].iloc[0] if len(urls) > 0 else ""
    platform = _detect_platform(first_url)
    logger.info(f"Detected platform: {platform}")

    for i, (_, row) in enumerate(urls.iterrows()):
        sku_id = str(row[id_col])
        raw_url = str(row[url_col])

        # Clean URL (remove UTM params for cleaner requests)
        clean_url = _clean_url(raw_url)

        if progress_callback:
            progress_callback(i + 1, total)

        try:
            if platform == "shopify":
                result = _scrape_shopify(session, clean_url, timeout)
            else:
                result = _scrape_generic(session, clean_url, timeout)

            result["sku_id"] = sku_id
            result["scrape_status"] = "ok"

        except requests.exceptions.Timeout:
            result = _empty_result(sku_id, "timeout")
        except requests.exceptions.ConnectionError:
            result = _empty_result(sku_id, "connection_error")
        except Exception as e:
            result = _empty_result(sku_id, f"error: {str(e)[:100]}")

        results.append(result)

        # Rate limiting
        if i < total - 1:
            time.sleep(delay)

    return pd.DataFrame(results)


# ============================================================
# RESUMABLE SCRAPING (checkpoint to disk)
# ============================================================

def scrape_feed_urls_resumable(
    feed_df: pd.DataFrame,
    url_col: str = "link",
    id_col: str = "id",
    max_products: Optional[int] = None,
    delay: float = 1.0,
    timeout: int = 15,
    checkpoint_path: str = "scrape_checkpoint.csv",
    checkpoint_every: int = 25,
    progress_callback=None,
) -> pd.DataFrame:
    """
    Resumable version of scrape_feed_urls. Saves progress to a checkpoint
    file every N products. On restart, skips already-scraped SKUs.

    Args:
        feed_df: Feed DataFrame with product URLs.
        url_col: Column containing the product URL.
        id_col: Column containing the SKU ID.
        max_products: Limit number of products to scrape (None = all).
        delay: Seconds between requests (rate limiting).
        timeout: Request timeout in seconds.
        checkpoint_path: Path for the checkpoint CSV file.
        checkpoint_every: Save checkpoint after this many new scrapes.
        progress_callback: Optional callable(current, total, resumed) for progress.

    Returns:
        DataFrame with all results (resumed + newly scraped).
    """
    # Load existing checkpoint if present
    existing_results = []
    already_scraped = set()

    if os.path.exists(checkpoint_path):
        try:
            checkpoint_df = pd.read_csv(checkpoint_path, low_memory=False)
            existing_results = checkpoint_df.to_dict("records")
            already_scraped = set(checkpoint_df["sku_id"].astype(str).tolist())
            logger.info(f"Resumed from checkpoint: {len(already_scraped)} products already scraped")
        except Exception as e:
            logger.warning(f"Could not load checkpoint: {e}")

    # Build URL list, excluding already-scraped
    urls = feed_df[[id_col, url_col]].dropna(subset=[url_col]).copy()
    urls[id_col] = urls[id_col].astype(str)

    if max_products:
        urls = urls.head(max_products)

    remaining = urls[~urls[id_col].isin(already_scraped)]
    total = len(urls)
    done_before = len(already_scraped & set(urls[id_col].tolist()))
    to_scrape = len(remaining)

    logger.info(f"Total: {total}, Already done: {done_before}, Remaining: {to_scrape}")

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    # Detect platform
    first_url = remaining[url_col].iloc[0] if len(remaining) > 0 else ""
    platform = _detect_platform(first_url) if first_url else "unknown"

    new_results = []

    for i, (_, row) in enumerate(remaining.iterrows()):
        sku_id = str(row[id_col])
        raw_url = str(row[url_col])
        clean_url = _clean_url(raw_url)

        current = done_before + i + 1
        if progress_callback:
            progress_callback(current, total, done_before)

        try:
            if platform == "shopify":
                result = _scrape_shopify(session, clean_url, timeout)
            else:
                result = _scrape_generic(session, clean_url, timeout)
            result["sku_id"] = sku_id
            result["scrape_status"] = "ok"
        except requests.exceptions.Timeout:
            result = _empty_result(sku_id, "timeout")
        except requests.exceptions.ConnectionError:
            result = _empty_result(sku_id, "connection_error")
        except Exception as e:
            result = _empty_result(sku_id, f"error: {str(e)[:100]}")

        new_results.append(result)

        # Checkpoint save
        if (i + 1) % checkpoint_every == 0:
            _save_checkpoint(existing_results + new_results, checkpoint_path)
            logger.info(f"Checkpoint saved at {current}/{total}")

        if i < to_scrape - 1:
            time.sleep(delay)

    # Final save
    all_results = existing_results + new_results
    _save_checkpoint(all_results, checkpoint_path)

    return pd.DataFrame(all_results)


def get_checkpoint_info(checkpoint_path: str = "scrape_checkpoint.csv") -> dict:
    """Check if a checkpoint file exists and return its stats."""
    if not os.path.exists(checkpoint_path):
        return {"exists": False, "count": 0, "path": checkpoint_path}

    try:
        df = pd.read_csv(checkpoint_path, low_memory=False)
        ok_count = (df["scrape_status"] == "ok").sum()
        return {
            "exists": True,
            "count": len(df),
            "ok_count": ok_count,
            "failed_count": len(df) - ok_count,
            "path": checkpoint_path,
        }
    except Exception:
        return {"exists": False, "count": 0, "path": checkpoint_path}


def _save_checkpoint(results: list, path: str):
    """Save results list to a checkpoint CSV."""
    try:
        pd.DataFrame(results).to_csv(path, index=False)
    except Exception as e:
        logger.error(f"Failed to save checkpoint: {e}")


# ============================================================
# SHOPIFY SCRAPER (primary - uses .json endpoint)
# ============================================================

def _scrape_shopify(
    session: requests.Session,
    url: str,
    timeout: int,
) -> dict:
    """
    Scrape a Shopify product page using the .json endpoint.
    Falls back to HTML parsing if .json is blocked.
    """
    # Try JSON endpoint first (append .json to the product URL)
    json_url = _shopify_json_url(url)

    if json_url:
        try:
            resp = session.get(json_url, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                product = data.get("product", {})
                return _parse_shopify_json(product)
        except (json.JSONDecodeError, KeyError):
            pass  # Fall through to HTML

    # Fallback: parse the HTML page
    return _scrape_generic(session, url, timeout)


def _shopify_json_url(url: str) -> Optional[str]:
    """Convert a Shopify product URL to its .json endpoint."""
    parsed = urlparse(url)
    path = parsed.path

    # Strip trailing slash
    path = path.rstrip("/")

    # Must be a /products/ URL
    if "/products/" not in path:
        return None

    # Remove any query params and add .json
    return f"{parsed.scheme}://{parsed.netloc}{path}.json"


def _parse_shopify_json(product: dict) -> dict:
    """Extract structured data from Shopify product JSON."""
    # Raw HTML description from Shopify
    body_html = product.get("body_html", "") or ""

    # Parse the HTML description to extract text and structure
    soup = BeautifulSoup(body_html, "lxml") if body_html else None

    # Extract plain text description
    description = ""
    if soup:
        description = soup.get_text(separator="\n", strip=True)

    # Extract bullet points / feature lists
    features = []
    if soup:
        for li in soup.find_all("li"):
            text = li.get_text(strip=True)
            if text and len(text) > 3:
                features.append(text)

    # Extract materials and other details from tags
    tags = product.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    # Look for material-related content in description
    materials = _extract_materials(description, features)

    # Compile additional info from Shopify product data
    additional = []
    vendor = product.get("vendor", "")
    product_type = product.get("product_type", "")
    if vendor:
        additional.append(f"Vendor: {vendor}")
    if product_type:
        additional.append(f"Product type: {product_type}")
    if tags:
        additional.append(f"Tags: {', '.join(tags[:10])}")

    # Variant info (sizes, colours available)
    variants = product.get("variants", [])
    if variants:
        options = set()
        for v in variants:
            for opt in ["option1", "option2", "option3"]:
                val = v.get(opt)
                if val and val != "Default Title":
                    options.add(val)
        if options:
            additional.append(f"Available options: {', '.join(sorted(options))}")

    return {
        "page_title": product.get("title", ""),
        "page_description": description,
        "features": " | ".join(features) if features else "",
        "materials": materials,
        "additional_info": " | ".join(additional) if additional else "",
    }


# ============================================================
# GENERIC HTML SCRAPER (fallback for non-Shopify sites)
# ============================================================

def _scrape_generic(
    session: requests.Session,
    url: str,
    timeout: int,
) -> dict:
    """
    Scrape any product page using standard HTML parsing.
    Looks for common ecommerce page structures.
    """
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")

    # --- Title ---
    title = ""
    # Try Open Graph title first (usually clean)
    og_title = soup.find("meta", property="og:title")
    if og_title:
        title = og_title.get("content", "")
    elif soup.title:
        title = soup.title.get_text(strip=True)

    # --- Description ---
    description = ""
    # Try JSON-LD structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            ld = json.loads(script.string)
            if isinstance(ld, dict) and ld.get("@type") == "Product":
                description = ld.get("description", "")
                if not title:
                    title = ld.get("name", "")
                break
            # Handle @graph arrays
            if isinstance(ld, dict) and "@graph" in ld:
                for item in ld["@graph"]:
                    if item.get("@type") == "Product":
                        description = item.get("description", "")
                        if not title:
                            title = item.get("name", "")
                        break
        except (json.JSONDecodeError, TypeError):
            continue

    # Fallback: look for common description containers
    if not description:
        desc_selectors = [
            ".product-description",
            ".product__description",
            "[data-product-description]",
            ".product-single__description",
            "#product-description",
            ".rte",
            "[itemprop='description']",
        ]
        for sel in desc_selectors:
            el = soup.select_one(sel)
            if el:
                description = el.get_text(separator="\n", strip=True)
                break

    # Fallback: meta description
    if not description:
        meta = soup.find("meta", attrs={"name": "description"})
        if meta:
            description = meta.get("content", "")

    # --- Features / bullet points ---
    features = []
    # Look for lists within product description containers
    for sel in [".product-description", ".product__description", ".rte"]:
        container = soup.select_one(sel)
        if container:
            for li in container.find_all("li"):
                text = li.get_text(strip=True)
                if text and len(text) > 3:
                    features.append(text)
            break

    # --- Materials ---
    materials = _extract_materials(description, features)

    return {
        "page_title": title,
        "page_description": description,
        "features": " | ".join(features) if features else "",
        "materials": materials,
        "additional_info": "",
    }


# ============================================================
# HELPERS
# ============================================================

def _detect_platform(url: str) -> str:
    """Detect the ecommerce platform from the URL structure."""
    if not url:
        return "unknown"

    # Shopify: /products/ in path, or known Shopify domains
    if "/products/" in url:
        return "shopify"

    # Could add BigCommerce, WooCommerce, Magento detection here
    return "generic"


def _clean_url(url: str) -> str:
    """Remove tracking parameters from URL for cleaner requests."""
    parsed = urlparse(url)
    # Keep just scheme + host + path (drop query params)
    clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return clean


def _extract_materials(description: str, features: list) -> str:
    """
    Extract material information from description text and features.
    Looks for common material keywords.
    """
    material_keywords = [
        "cotton", "polyester", "nylon", "wool", "acrylic", "spandex",
        "elastane", "leather", "suede", "canvas", "denim", "fleece",
        "mesh", "corduroy", "satin", "silk", "linen", "rayon",
        "polycotton", "twill", "jersey", "terry", "velvet",
    ]

    found = set()
    text_lower = (description + " " + " ".join(features)).lower()

    for kw in material_keywords:
        if kw in text_lower:
            found.add(kw)

    return ", ".join(sorted(found)) if found else ""


def _empty_result(sku_id: str, status: str) -> dict:
    """Return an empty result dict for failed scrapes."""
    return {
        "sku_id": sku_id,
        "page_title": "",
        "page_description": "",
        "features": "",
        "materials": "",
        "additional_info": "",
        "scrape_status": status,
    }


# ============================================================
# COMPARISON HELPER
# ============================================================

def compare_feed_vs_scraped(
    feed_df: pd.DataFrame,
    scraped_df: pd.DataFrame,
    id_col: str = "id",
) -> pd.DataFrame:
    """
    Compare feed data vs scraped page data to highlight
    what's missing from the feed.

    Returns a DataFrame showing:
      - Feed title vs page title
      - Feed description length vs page description length
      - Features found on page but not in feed
      - Materials found on page but not in feed
    """
    merged = feed_df.merge(
        scraped_df,
        left_on=id_col,
        right_on="sku_id",
        how="inner",
    )

    comparison = pd.DataFrame({
        "sku_id": merged["sku_id"],
        "feed_title": merged["title"],
        "page_title": merged["page_title"],
        "feed_desc_len": merged["description"].fillna("").str.len(),
        "page_desc_len": merged["page_description"].fillna("").str.len(),
        "desc_delta": (
            merged["page_description"].fillna("").str.len()
            - merged["description"].fillna("").str.len()
        ),
        "has_features": merged["features"].fillna("").str.len() > 0,
        "page_materials": merged["materials"],
        "feed_material": merged.get("material", pd.Series([""] * len(merged))),
    })

    return comparison
