"""
Pattern Feed Optimisation Tool
================================
Streamlit app for enriching product feeds with Google Ads
search intelligence. Built for Pattern's feed optimisation team.

Future pages (when expanding beyond enrichment):
  - Feed Enrichment (current)
  - Scraper
  - QA Dashboard
  - Prompt Builder
"""

import streamlit as st
import pandas as pd
import time
import io
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.search_terms import (
    match_search_terms_to_skus,
    aggregate_for_sku,
    build_prompt_context,
    summarise_search_coverage,
)


# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="Feed Optimisation | Pattern",
    page_icon="data:image/svg+xml,<svg viewBox='0 0 40 40' xmlns='http://www.w3.org/2000/svg'><path d='M8 28L18 18L28 28L18 38Z' fill='%23009bff'/><path d='M18 18L28 8L38 18L28 28Z' fill='%23009bff'/></svg>",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# PATTERN BRAND CSS
# ============================================================

PATTERN_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Wix+Madefor+Display:wght@400;500;600;700;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=STIX+Two+Text:ital,wght@0,400;0,700;1,400;1,700&display=swap');

:root {
    --pattern-blue: #009bff;
    --violet: #770bff;
    --sea: #4cc3ae;
    --dark: #090A0F;
    --deep-navy: #00084d;
    --light: #fcfcfc;
    --surface: #12131a;
    --surface-hover: #1a1b24;
    --border: rgba(255,255,255,0.08);
    --border-strong: rgba(255,255,255,0.15);
    --text-secondary: rgba(252,252,252,0.6);
    --text-tertiary: rgba(252,252,252,0.4);
}

/* Global font override */
html, body, [class*="css"] {
    font-family: 'Wix Madefor Display', system-ui, -apple-system, sans-serif !important;
}

/* Header area */
header[data-testid="stHeader"] {
    background: var(--dark) !important;
    border-bottom: 1px solid var(--border) !important;
}

/* Sidebar styling */
section[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
}

section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
    font-family: 'Wix Madefor Display', sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
}

/* Main content */
.main .block-container {
    padding-top: 2rem !important;
    max-width: 1200px !important;
}

/* Accent text (serif italic) */
.accent {
    font-family: 'STIX Two Text', Georgia, serif !important;
    font-style: italic;
    font-weight: 400;
}

/* Gradient spectrum bar */
.gradient-bar {
    height: 3px;
    background: linear-gradient(90deg, #009bff 0%, #770bff 60%, #4cc3ae 100%);
    border-radius: 2px;
    margin: 0.5rem 0 1.5rem 0;
}

/* Metric cards */
div[data-testid="stMetric"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    padding: 1rem 1.25rem !important;
}

div[data-testid="stMetric"] label {
    color: var(--text-secondary) !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
}

div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: var(--pattern-blue) !important;
    font-weight: 700 !important;
}

/* Tab styling */
button[data-baseweb="tab"] {
    font-family: 'Wix Madefor Display', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
}

/* File uploader */
section[data-testid="stFileUploader"] {
    border: 1px dashed var(--border-strong) !important;
    border-radius: 12px !important;
}

/* Expander */
details {
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    background: var(--surface) !important;
}

/* Code blocks */
code {
    background: var(--deep-navy) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
}

/* Download buttons */
.stDownloadButton > button {
    background: var(--pattern-blue) !important;
    color: white !important;
    font-weight: 600 !important;
    border: none !important;
    border-radius: 8px !important;
    transition: all 200ms ease !important;
}

.stDownloadButton > button:hover {
    background: #0090eb !important;
}

/* Primary button */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #009bff 0%, #770bff 100%) !important;
    color: white !important;
    font-weight: 600 !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.75rem 2rem !important;
    transition: all 200ms ease !important;
}

/* Status widget */
[data-testid="stStatusWidget"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
}

/* Logo container */
.logo-container {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 1rem;
}

.logo-container svg {
    width: 32px;
    height: 32px;
}

.logo-container .wordmark {
    font-family: 'Wix Madefor Display', sans-serif;
    font-weight: 700;
    font-size: 20px;
    letter-spacing: -0.02em;
    color: var(--light);
}

/* Hero section */
.hero {
    padding: 2rem 0;
}

.hero h1 {
    font-size: 40px !important;
    font-weight: 800 !important;
    letter-spacing: -0.03em !important;
    line-height: 1.1 !important;
    margin-bottom: 0.5rem !important;
}

/* Overline label */
.overline {
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--pattern-blue);
    margin-bottom: 0.25rem;
}

/* Empty state */
.empty-state {
    text-align: center;
    padding: 3rem 2rem;
    color: var(--text-tertiary);
}

.empty-state svg {
    margin-bottom: 1rem;
    opacity: 0.4;
}
</style>
"""

st.markdown(PATTERN_CSS, unsafe_allow_html=True)


# ============================================================
# PATTERN LOGO
# ============================================================

PATTERN_LOGO_SVG = """
<div class="logo-container">
    <svg viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">
        <path d="M8 28L18 18L28 28L18 38Z" fill="#009bff"/>
        <path d="M18 18L28 8L38 18L28 28Z" fill="#009bff"/>
    </svg>
    <span class="wordmark">pattern</span>
</div>
"""


# ============================================================
# HELPERS
# ============================================================

def load_file(uploaded_file):
    """Load an uploaded file into a DataFrame."""
    name = uploaded_file.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(uploaded_file)
    elif name.endswith(".tsv"):
        return pd.read_csv(uploaded_file, sep="\t", low_memory=False)
    else:
        return pd.read_csv(uploaded_file, low_memory=False)


def to_csv_bytes(df):
    buffer = io.BytesIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue()


def to_xlsx_bytes(df):
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown(PATTERN_LOGO_SVG, unsafe_allow_html=True)
    st.markdown('<div class="gradient-bar"></div>', unsafe_allow_html=True)

    st.markdown('<p class="overline">Data inputs</p>', unsafe_allow_html=True)

    feed_file = st.file_uploader(
        "GMC feed export",
        type=["csv", "tsv", "xlsx", "xls"],
        help="Product feed from Google Merchant Centre",
    )

    search_file = st.file_uploader(
        "Search terms export",
        type=["csv", "xlsx", "xls"],
        help="Supermetrics search term data from Google Ads",
    )

    st.markdown("---")
    st.markdown('<p class="overline">Settings</p>', unsafe_allow_html=True)

    with st.expander("Matching parameters", expanded=False):
        min_impressions = st.number_input(
            "Min impressions",
            min_value=1,
            max_value=1000,
            value=10,
            help="Filter search terms below this threshold",
        )

        relevance_threshold = st.slider(
            "Relevance threshold",
            min_value=0.1,
            max_value=0.8,
            value=0.3,
            step=0.05,
            help="Higher = stricter matching (0.3 recommended)",
        )

    with st.expander("Column mapping", expanded=False):
        id_col = st.text_input("SKU ID column", value="id")
        title_col = st.text_input("Title column", value="title")
        product_type_col = st.text_input("Product type column", value="product type")

    # Version info at bottom
    st.markdown("---")
    st.caption("Feed Optimisation Tool v1.0")
    st.caption("Built by Pattern's feed team")


# ============================================================
# MAIN - LANDING STATE
# ============================================================

if not feed_file or not search_file:
    st.markdown('<div class="hero">', unsafe_allow_html=True)
    st.markdown(
        "# Feed <span class='accent'>Enrichment</span>",
        unsafe_allow_html=True,
    )
    st.markdown('<div class="gradient-bar"></div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        "Enrich product feeds with real Google Ads search intelligence. "
        "Upload a GMC feed and Supermetrics search terms to get started."
    )

    st.markdown("")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown('<p class="overline">01 _____ Upload</p>', unsafe_allow_html=True)
        st.markdown(
            "Drop your GMC feed export and Supermetrics "
            "search terms file in the sidebar."
        )

    with col2:
        st.markdown('<p class="overline">02 _____ Enrich</p>', unsafe_allow_html=True)
        st.markdown(
            "The tool extracts n-grams from search data and "
            "matches them to products by relevance."
        )

    with col3:
        st.markdown('<p class="overline">03 _____ Download</p>', unsafe_allow_html=True)
        st.markdown(
            "Get an enriched feed with search context "
            "ready for your V3 template description prompts."
        )

    st.markdown("---")

    st.markdown(
        "**How it works** - "
        "N-grams (keyword phrases) are extracted from converting search terms, "
        "matched to products by title and attribute relevance, and formatted as "
        "a search intelligence block. This goes into description prompts so Claude "
        "writes descriptions grounded in actual search behaviour."
    )

    st.stop()


# ============================================================
# MAIN - DATA LOADED
# ============================================================

with st.spinner("Loading files..."):
    feed = load_file(feed_file)
    search_terms = load_file(search_file)

# Validate columns
missing_cols = [c for c in [id_col, title_col] if c not in feed.columns]
if missing_cols:
    st.error(
        f"Feed is missing columns: **{', '.join(missing_cols)}**. "
        f"Available: {', '.join(feed.columns[:10])}... "
        f"Update column mapping in the sidebar."
    )
    st.stop()

# Header
st.markdown(
    "# Feed <span class='accent'>Enrichment</span>",
    unsafe_allow_html=True,
)
st.markdown('<div class="gradient-bar"></div>', unsafe_allow_html=True)

# Quick stats
s1, s2, s3, s4 = st.columns(4)
s1.metric("Feed products", f"{len(feed):,}")
s2.metric("Search terms", f"{len(search_terms):,}")

# Try to find conversions column for stats
conv_col = next((c for c in ["Conversions", "conversions", "Conv."] if c in search_terms.columns), None)
if conv_col:
    converting = (search_terms[conv_col] > 0).sum()
    s3.metric("Converting terms", f"{converting:,}")
    s4.metric("Zero-conversion", f"{len(search_terms) - converting:,}")

st.markdown("")

# Tabs
tab_enrich, tab_preview, tab_explore = st.tabs(["Enrich", "Data preview", "Explore matches"])


# ============================================================
# TAB: ENRICH
# ============================================================

with tab_enrich:
    if st.button("Enrich feed with search intelligence", type="primary", use_container_width=True):
        with st.status("Running enrichment...", expanded=True) as status:
            st.write("Extracting n-grams from search terms...")
            t0 = time.time()

            matched = match_search_terms_to_skus(
                search_terms,
                feed,
                min_impressions=min_impressions,
                relevance_threshold=relevance_threshold,
                feed_id_col=id_col,
                feed_title_col=title_col,
                feed_product_type_col=product_type_col,
            )

            elapsed = time.time() - t0
            st.write(
                f"Matched **{matched['search_term'].nunique():,}** n-grams "
                f"to **{matched['sku_id'].nunique():,}** SKUs in {elapsed:.1f}s"
            )

            coverage = summarise_search_coverage(feed, matched)
            st.write(f"Coverage: **{coverage['coverage_pct']}%** of products have search data")

            st.write("Building search context per product...")
            search_contexts = {}
            keyword_themes_compact = {}
            sku_ids = feed[id_col].astype(str).unique()

            progress = st.progress(0)
            for i, sku_id in enumerate(sku_ids):
                ctx = aggregate_for_sku(sku_id, matched)
                search_contexts[sku_id] = build_prompt_context({"id": sku_id}, ctx)

                themes = ctx.get("keyword_themes", [])
                keyword_themes_compact[sku_id] = (
                    ", ".join(t["keyword"] for t in themes[:5]) if themes else ""
                )

                if (i + 1) % 100 == 0 or i == len(sku_ids) - 1:
                    progress.progress((i + 1) / len(sku_ids))

            enriched = feed.copy()
            enriched["search_context"] = enriched[id_col].astype(str).map(search_contexts).fillna("")
            enriched["keyword_themes"] = enriched[id_col].astype(str).map(keyword_themes_compact).fillna("")

            st.session_state["enriched"] = enriched
            st.session_state["matched"] = matched
            st.session_state["coverage"] = coverage

            status.update(label="Enrichment complete", state="complete")

    # Results
    if "enriched" in st.session_state:
        enriched = st.session_state["enriched"]
        coverage = st.session_state["coverage"]

        st.markdown("---")
        st.markdown('<p class="overline">Results</p>', unsafe_allow_html=True)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("SKUs enriched", f"{coverage['skus_with_search_data']:,}")
        m2.metric("Coverage", f"{coverage['coverage_pct']}%")
        m3.metric("N-grams matched", f"{coverage['total_unique_terms']:,}")
        m4.metric("Converting n-grams", f"{coverage['converting_terms']:,}")

        st.markdown("")
        st.markdown('<p class="overline">Sample output</p>', unsafe_allow_html=True)

        samples = enriched[enriched["keyword_themes"].str.len() > 0]
        if len(samples) > 5:
            samples = samples.sample(5, random_state=42)
        elif len(samples) == 0:
            samples = enriched.head(5)

        for _, row in samples.iterrows():
            title = str(row.get(title_col, ""))[:80]
            with st.expander(title):
                kw = row["keyword_themes"]
                if kw:
                    st.markdown(f"**Keyword themes:** {kw}")
                st.code(row["search_context"], language=None)

        # Downloads
        st.markdown("---")
        st.markdown('<p class="overline">Download</p>', unsafe_allow_html=True)

        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "Download enriched feed (CSV)",
                data=to_csv_bytes(enriched),
                file_name=f"{feed_file.name.rsplit('.', 1)[0]}_enriched.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with dl2:
            try:
                st.download_button(
                    "Download enriched feed (XLSX)",
                    data=to_xlsx_bytes(enriched),
                    file_name=f"{feed_file.name.rsplit('.', 1)[0]}_enriched.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            except Exception:
                st.caption("XLSX export requires openpyxl")


# ============================================================
# TAB: DATA PREVIEW
# ============================================================

with tab_preview:
    st.markdown('<p class="overline">Feed data</p>', unsafe_allow_html=True)
    preview_cols = [c for c in [id_col, title_col, "brand", "description", product_type_col, "color", "material"] if c in feed.columns]
    st.dataframe(feed[preview_cols].head(50), use_container_width=True, height=400)

    st.markdown("")
    st.markdown('<p class="overline">Search term data</p>', unsafe_allow_html=True)
    st.dataframe(search_terms.head(50), use_container_width=True, height=400)


# ============================================================
# TAB: EXPLORE MATCHES
# ============================================================

with tab_explore:
    if "matched" not in st.session_state:
        st.info("Run the enrichment first to explore matches.")
    else:
        matched = st.session_state["matched"]
        enriched = st.session_state["enriched"]

        st.markdown('<p class="overline">Top n-grams by conversion value</p>', unsafe_allow_html=True)

        ng_agg = (
            matched.groupby("search_term")
            .agg(
                Revenue=("conv_value", "first"),
                Conversions=("conversions", "first"),
                Impressions=("impressions", "first"),
                Sources=("term_count", "first"),
                SKUs=("sku_id", "nunique"),
                Specificity=("specificity", "first"),
            )
            .sort_values("Revenue", ascending=False)
            .head(30)
        )
        ng_agg["Revenue"] = ng_agg["Revenue"].apply(lambda x: f"${x:,.0f}")
        ng_agg["Specificity"] = (ng_agg["Specificity"] * 100).round(0).astype(int).astype(str) + "%"
        st.dataframe(ng_agg, use_container_width=True, height=500)

        st.markdown("---")
        st.markdown('<p class="overline">Product lookup</p>', unsafe_allow_html=True)

        product_options = enriched[enriched["keyword_themes"].str.len() > 0][title_col].tolist()
        if product_options:
            selected = st.selectbox(
                "Search for a product",
                options=[""] + product_options[:500],
                format_func=lambda x: x[:80] if x else "Select a product...",
            )
            if selected:
                row = enriched[enriched[title_col] == selected].iloc[0]
                st.markdown(f"**Keyword themes:** {row['keyword_themes']}")
                st.code(row["search_context"], language=None)

                sku_id = str(row[id_col])
                sku_matches = matched[matched["sku_id"] == sku_id].sort_values("conv_value", ascending=False)
                if len(sku_matches) > 0:
                    st.markdown(f"**Matched n-grams** ({len(sku_matches)})")
                    display_cols = [c for c in ["search_term", "relevance_score", "impressions", "clicks", "conversions", "conv_value", "specificity"] if c in sku_matches.columns]
                    st.dataframe(sku_matches[display_cols], use_container_width=True, height=300)
