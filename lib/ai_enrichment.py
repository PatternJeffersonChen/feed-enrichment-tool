"""
AI Enrichment & Validation via Bifrost
=======================================
Uses Pattern's Bifrost API gateway (OpenAI-compatible) to:
  1. Generate AI-interpreted product briefs from enrichment data
  2. Validate enrichment data against the original feed
  3. Validate optimised feed output against the original feed

Bifrost is an OpenAI-compatible proxy:
  base_url = "https://bifrost.pattern.com/openai"
  api_key  = "sk-bf-..."
"""

import json
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================
# CLIENT SETUP
# ============================================================

def get_client(api_key: str, base_url: str = "https://bifrost.pattern.com/openai"):
    """Create an OpenAI-compatible client for Bifrost."""
    from openai import OpenAI
    return OpenAI(base_url=base_url, api_key=api_key)


# ============================================================
# 1. AI PRODUCT BRIEF
# ============================================================

def generate_product_brief(
    client,
    model: str,
    product: dict,
    scraper_output: str = "",
    search_context: str = "",
) -> str:
    """
    Send product data + enrichment data to Claude via Bifrost.
    Returns a structured AI brief: key selling points, content gaps,
    themes to address, and missing information.

    Args:
        client: OpenAI-compatible client
        model: Model string (e.g. "anthropic/claude-sonnet-4-20250514")
        product: Dict with feed columns (title, id, description, color, material, etc.)
        scraper_output: Consolidated scraper text block
        search_context: Search intelligence text block

    Returns:
        Structured brief as text
    """
    # Build the product context
    product_lines = []
    for key in ["id", "title", "description", "brand", "product type", "color",
                 "material", "size", "gender", "age group", "price"]:
        val = product.get(key, "")
        if val and str(val).strip() and str(val).lower() != "nan":
            product_lines.append(f"  {key}: {str(val).strip()}")

    product_block = "\n".join(product_lines) if product_lines else "  (minimal feed data)"

    prompt = f"""You are a feed optimisation analyst at Pattern, an ecommerce agency.
Analyse this product's feed data alongside its scraped page content and search intelligence.

ORIGINAL FEED DATA:
{product_block}

{f"SCRAPED PAGE CONTENT:{chr(10)}{scraper_output}" if scraper_output else "SCRAPED PAGE CONTENT: Not available"}

{f"SEARCH INTELLIGENCE:{chr(10)}{search_context}" if search_context else "SEARCH INTELLIGENCE: Not available"}

Produce a brief with these sections:

KEY SELLING POINTS: 3-5 bullet points about what makes this product compelling, drawn from ALL available data sources.

CONTENT GAPS: What information is missing from the feed that exists on the product page or could be inferred from search data? (e.g. materials not in feed, features only on the page, sizing details)

SEARCH THEMES: What are shoppers actually looking for when they find this product? What language/concepts should the description address?

DESCRIPTION GUIDANCE: 2-3 sentences of specific guidance for writing this product's description. What to emphasise, what to include, what tone to strike.

Be specific to THIS product. No generic advice. If data is limited, say so rather than guessing."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=800,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Brief generation failed for {product.get('id', '?')}: {e}")
        return f"[AI brief generation failed: {str(e)[:100]}]"


# ============================================================
# 2. VALIDATE ENRICHMENT DATA vs ORIGINAL FEED
# ============================================================

def validate_enrichment(
    client,
    model: str,
    product: dict,
    scraper_output: str = "",
    search_context: str = "",
) -> dict:
    """
    Check enrichment data for consistency with the original feed.
    Flags potential issues before the data goes into optimisation.

    Returns:
        {
            "confidence_score": 0-100,
            "flags": ["list of issues found"],
            "summary": "one-line summary"
        }
    """
    product_lines = []
    for key in ["id", "title", "description", "brand", "product type", "color",
                 "material", "size", "gender", "age group"]:
        val = product.get(key, "")
        if val and str(val).strip() and str(val).lower() != "nan":
            product_lines.append(f"  {key}: {str(val).strip()}")

    product_block = "\n".join(product_lines)

    prompt = f"""You are a QA analyst validating enrichment data against a product feed.

ORIGINAL FEED DATA (source of truth for this product's attributes):
{product_block}

SCRAPED PAGE CONTENT:
{scraper_output if scraper_output else "(none)"}

SEARCH CONTEXT:
{search_context if search_context else "(none)"}

Check for:
1. ATTRIBUTE CONFLICTS: Does the scraper output contradict the feed? (e.g. different color, wrong material, mismatched brand, wrong gender/category)
2. WRONG PRODUCT MATCH: Does the search context seem to be about a different product or category?
3. DATA QUALITY: Is the scraper output garbled, truncated, or clearly from the wrong page?
4. RELEVANCE: Are the search terms actually relevant to this specific product?

Respond in this exact JSON format (no markdown, no code fences):
{{"confidence_score": <0-100>, "flags": ["issue 1", "issue 2"], "summary": "one line summary"}}

confidence_score:
- 90-100: Data looks clean, no issues
- 70-89: Minor concerns but usable
- 50-69: Notable issues, review recommended
- Below 50: Significant problems, do not use without manual review

If no issues found, return empty flags array and high confidence."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
        )
        text = response.choices[0].message.content.strip()
        # Parse JSON from response
        result = json.loads(text)
        # Ensure expected keys exist
        return {
            "confidence_score": int(result.get("confidence_score", 0)),
            "flags": result.get("flags", []),
            "summary": result.get("summary", ""),
        }
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Enrichment validation parse error for {product.get('id', '?')}: {e}")
        return {
            "confidence_score": 0,
            "flags": [f"Validation response could not be parsed: {str(e)[:80]}"],
            "summary": "Parse error",
        }
    except Exception as e:
        logger.error(f"Enrichment validation failed for {product.get('id', '?')}: {e}")
        return {
            "confidence_score": 0,
            "flags": [f"API error: {str(e)[:100]}"],
            "summary": "API error",
        }


# ============================================================
# 3. VALIDATE OPTIMISED OUTPUT vs ORIGINAL FEED
# ============================================================

def validate_optimised_output(
    client,
    model: str,
    original_product: dict,
    new_title: str = "",
    new_description: str = "",
) -> dict:
    """
    Validate optimised titles/descriptions against the original feed.
    Catches hallucinated attributes, factual errors, and brand misalignment.

    Args:
        client: OpenAI-compatible client
        model: Model string
        original_product: Dict with original feed columns
        new_title: The AI-generated optimised title
        new_description: The AI-generated optimised description

    Returns:
        {
            "confidence_score": 0-100,
            "flags": [{"field": "color", "issue": "...", "severity": "high|medium|low"}],
            "summary": "one-line summary",
            "title_ok": True/False,
            "description_ok": True/False,
        }
    """
    product_lines = []
    for key in ["id", "title", "description", "brand", "product type", "color",
                 "material", "size", "gender", "age group", "price"]:
        val = original_product.get(key, "")
        if val and str(val).strip() and str(val).lower() != "nan":
            product_lines.append(f"  {key}: {str(val).strip()}")

    product_block = "\n".join(product_lines)

    prompt = f"""You are a senior QA analyst at Pattern, an ecommerce agency. Your job is to catch errors in AI-generated product content before it goes to the client.

ORIGINAL FEED DATA (absolute source of truth):
{product_block}

{f"NEW TITLE:{chr(10)}  {new_title}" if new_title else "NEW TITLE: (not provided)"}

{f"NEW DESCRIPTION:{chr(10)}  {new_description}" if new_description else "NEW DESCRIPTION: (not provided)"}

Carefully verify the new content against the original feed. Check for:

1. HALLUCINATED ATTRIBUTES: Does the new content mention colors, materials, sizes, or features NOT in the original feed?
   Example: Feed says "black" but new description says "brown leather" - this is a critical error.

2. BRAND/PRODUCT MISIDENTIFICATION: Does the title/description describe the wrong product, wrong brand, or wrong category?

3. FABRICATED CLAIMS: Does the content make performance claims, certifications, or specifications not supported by the feed data?

4. FACTUAL ACCURACY: Are dimensions, weights, materials, and other factual details correct?

5. MISSING KEY ATTRIBUTES: Does the new content fail to mention important attributes from the feed (brand, color, key material)?

Respond in this exact JSON format (no markdown, no code fences):
{{"confidence_score": <0-100>, "flags": [{{"field": "color", "issue": "Feed says black, description says brown", "severity": "high"}}], "summary": "one line", "title_ok": true, "description_ok": true}}

Severity levels:
- high: Factually wrong (wrong color, wrong material, wrong brand) - would mislead customers
- medium: Potentially inaccurate claim or missing important detail
- low: Minor style issue or could be improved

confidence_score:
- 90-100: Content is accurate and faithful to the feed
- 70-89: Minor issues, safe to publish with small edits
- 50-69: Notable problems, needs human review
- Below 50: Significant errors, do not publish"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )
        text = response.choices[0].message.content.strip()
        result = json.loads(text)
        return {
            "confidence_score": int(result.get("confidence_score", 0)),
            "flags": result.get("flags", []),
            "summary": result.get("summary", ""),
            "title_ok": result.get("title_ok", True),
            "description_ok": result.get("description_ok", True),
        }
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Output validation parse error for {original_product.get('id', '?')}: {e}")
        return {
            "confidence_score": 0,
            "flags": [{"field": "parse", "issue": f"Response parse error: {str(e)[:80]}", "severity": "high"}],
            "summary": "Parse error",
            "title_ok": False,
            "description_ok": False,
        }
    except Exception as e:
        logger.error(f"Output validation failed for {original_product.get('id', '?')}: {e}")
        return {
            "confidence_score": 0,
            "flags": [{"field": "api", "issue": f"API error: {str(e)[:100]}", "severity": "high"}],
            "summary": "API error",
            "title_ok": False,
            "description_ok": False,
        }


# ============================================================
# BATCH HELPERS
# ============================================================

def batch_generate_briefs(
    client,
    model: str,
    products: list[dict],
    scraper_map: dict = None,
    search_context_map: dict = None,
    delay: float = 0.5,
    progress_callback=None,
) -> dict:
    """
    Generate AI briefs for a list of products.

    Args:
        products: List of product dicts with at least 'id' and 'title'
        scraper_map: {sku_id: scraper_output_text}
        search_context_map: {sku_id: search_context_text}
        delay: Seconds between API calls (rate limiting)
        progress_callback: callable(current, total)

    Returns:
        {sku_id: brief_text}
    """
    scraper_map = scraper_map or {}
    search_context_map = search_context_map or {}
    briefs = {}
    total = len(products)

    for i, product in enumerate(products):
        sku_id = str(product.get("id", ""))
        brief = generate_product_brief(
            client, model, product,
            scraper_output=scraper_map.get(sku_id, ""),
            search_context=search_context_map.get(sku_id, ""),
        )
        briefs[sku_id] = brief

        if progress_callback:
            progress_callback(i + 1, total)

        if i < total - 1:
            time.sleep(delay)

    return briefs


def batch_validate_enrichment(
    client,
    model: str,
    products: list[dict],
    scraper_map: dict = None,
    search_context_map: dict = None,
    delay: float = 0.3,
    progress_callback=None,
) -> dict:
    """
    Validate enrichment data for a list of products.

    Returns:
        {sku_id: {"confidence_score": int, "flags": list, "summary": str}}
    """
    scraper_map = scraper_map or {}
    search_context_map = search_context_map or {}
    results = {}
    total = len(products)

    for i, product in enumerate(products):
        sku_id = str(product.get("id", ""))
        result = validate_enrichment(
            client, model, product,
            scraper_output=scraper_map.get(sku_id, ""),
            search_context=search_context_map.get(sku_id, ""),
        )
        results[sku_id] = result

        if progress_callback:
            progress_callback(i + 1, total)

        if i < total - 1:
            time.sleep(delay)

    return results


def batch_validate_optimised(
    client,
    model: str,
    original_products: list[dict],
    new_titles: dict = None,
    new_descriptions: dict = None,
    delay: float = 0.3,
    progress_callback=None,
) -> dict:
    """
    Validate optimised output for a list of products.

    Args:
        original_products: List of original feed product dicts
        new_titles: {sku_id: new_title}
        new_descriptions: {sku_id: new_description}

    Returns:
        {sku_id: {"confidence_score": int, "flags": list, "summary": str, "title_ok": bool, "description_ok": bool}}
    """
    new_titles = new_titles or {}
    new_descriptions = new_descriptions or {}
    results = {}
    total = len(original_products)

    for i, product in enumerate(original_products):
        sku_id = str(product.get("id", ""))
        result = validate_optimised_output(
            client, model, product,
            new_title=new_titles.get(sku_id, ""),
            new_description=new_descriptions.get(sku_id, ""),
        )
        results[sku_id] = result

        if progress_callback:
            progress_callback(i + 1, total)

        if i < total - 1:
            time.sleep(delay)

    return results
