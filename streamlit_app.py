"""
Pattern Feed Enrichment Tool
================================
Streamlit app for enriching product feeds with:
  1. Google Ads search intelligence (n-gram matching)
  2. Product page scraping (Shopify JSON + HTML fallback)

Output: 4-column enrichment file (id, title, scraper_output, search_context)
that feeds into the feed optimisation tool (Sheets + Claude).

Future pages (when expanding to full pipeline):
  - QA Dashboard
  - Prompt Builder
  - Title/Description Generator
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
from lib.scraper import scrape_feed_urls, compare_feed_vs_scraped
from lib.ai_enrichment import (
    get_client,
    batch_generate_briefs,
    batch_validate_enrichment,
    batch_validate_optimised,
)


# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="Feed Enrichment | Pattern",
    page_icon="data:image/svg+xml,<svg viewBox='0 0 64 64' xmlns='http://www.w3.org/2000/svg'><rect width='64' height='64' rx='14' fill='%23292929'/><g transform='translate(12,12) scale(0.95)'><path d='M23.1 0.3L0.3 22.8C-0.04 23.2-0.04 23.8 0.3 24.2L5.95 29.7C6.3 30.1 6.9 30.1 7.3 29.7L30.1 7.2C30.5 6.8 30.5 6.2 30.1 5.8L24.5 0.3C24.1-0.1 23.5-0.1 23.1 0.3Z' fill='%23009BFF'/><path d='M32.5 9.6L19.1 22.8C18.7 23.2 18.7 23.8 19.1 24.2L24.7 29.7C25.1 30.1 25.7 30.1 26.1 29.7L39.5 16.5C39.9 16.1 39.9 15.5 39.5 15.1L33.9 9.6C33.5 9.2 32.9 9.2 32.5 9.6Z' fill='%23009BFF'/></g></svg>",
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

/* ============================================================
   DESIGN TOKENS
   ============================================================ */
:root {
    --pattern-blue: #009bff;
    --pattern-blue-glow: rgba(0, 155, 255, 0.25);
    --violet: #770bff;
    --violet-glow: rgba(119, 11, 255, 0.2);
    --sea: #4cc3ae;
    --dark: #090A0F;
    --deep-navy: #00084d;
    --light: #fcfcfc;
    --surface: #12131a;
    --surface-hover: #1a1b24;
    --surface-active: #22232e;
    --border: rgba(255,255,255,0.08);
    --border-strong: rgba(255,255,255,0.15);
    --border-glow: rgba(0, 155, 255, 0.3);
    --text-secondary: rgba(252,252,252,0.6);
    --text-tertiary: rgba(252,252,252,0.4);
    --skeleton-base: #1a1b24;
    --skeleton-shine: #2a2b36;
    --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
    --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
    --ease-smooth: cubic-bezier(0.25, 0.1, 0.25, 1);
}

/* ============================================================
   KEYFRAME ANIMATIONS (compositor-only: transform, opacity, filter)
   ============================================================ */

/* Entrance: fade up from below */
@keyframes fade-in-up {
    from { opacity: 0; transform: translateY(24px); }
    to   { opacity: 1; transform: translateY(0); }
}

/* Entrance: fade in from left */
@keyframes fade-in-left {
    from { opacity: 0; transform: translateX(-20px); }
    to   { opacity: 1; transform: translateX(0); }
}

/* Entrance: scale up from center */
@keyframes scale-in {
    from { opacity: 0; transform: scale(0.92); }
    to   { opacity: 1; transform: scale(1); }
}

/* Gradient bar shimmer - the brand signature */
@keyframes gradient-shift {
    0%   { background-position: 0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}

/* Skeleton loading shimmer */
@keyframes shimmer {
    from { background-position: 200% 0; }
    to   { background-position: -200% 0; }
}

/* Subtle pulse for status indicators */
@keyframes pulse-glow {
    0%, 100% { opacity: 1; }
    50%      { opacity: 0.7; }
}

/* Logo entrance */
@keyframes logo-entrance {
    from { opacity: 0; transform: translateY(-8px); }
    to   { opacity: 1; transform: translateY(0); }
}

/* Hero title entrance - staggered word reveal */
@keyframes hero-reveal {
    from { opacity: 0; transform: translateY(32px); filter: blur(4px); }
    to   { opacity: 1; transform: translateY(0); filter: blur(0); }
}

/* Metric counter entrance - pop in with overshoot */
@keyframes metric-pop {
    0%   { opacity: 0; transform: scale(0.8) translateY(12px); }
    70%  { transform: scale(1.04) translateY(-2px); }
    100% { opacity: 1; transform: scale(1) translateY(0); }
}

/* Button gradient animation on hover */
@keyframes gradient-rotate {
    0%   { background-position: 0% 50%; }
    100% { background-position: 200% 50%; }
}

/* ============================================================
   REDUCED MOTION GATE - non-negotiable accessibility baseline
   ============================================================ */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
    }
}

/* ============================================================
   BASE TYPOGRAPHY
   ============================================================ */
html, body, [class*="css"] {
    font-family: 'Wix Madefor Display', system-ui, -apple-system, sans-serif !important;
}

/* ============================================================
   LAYOUT STRUCTURE
   ============================================================ */
header[data-testid="stHeader"] {
    background: var(--dark) !important;
    border-bottom: 1px solid var(--border) !important;
    backdrop-filter: blur(12px);
}

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

.main .block-container {
    padding-top: 2rem !important;
    max-width: 1200px !important;
}

/* ============================================================
   BRAND ELEMENTS
   ============================================================ */
.accent {
    font-family: 'STIX Two Text', Georgia, serif !important;
    font-style: italic;
    font-weight: 400;
}

/* Animated gradient bar - the signature */
.gradient-bar {
    height: 3px;
    background: linear-gradient(90deg, #009bff, #770bff, #4cc3ae, #009bff);
    background-size: 300% 100%;
    border-radius: 2px;
    margin: 0.5rem 0 1.5rem 0;
    animation: gradient-shift 6s ease infinite;
}

/* Logo entrance animation */
.sidebar-logo {
    animation: logo-entrance 600ms var(--ease-out-expo) both;
}

/* ============================================================
   METRIC CARDS - hover lift + glow
   ============================================================ */
div[data-testid="stMetric"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    padding: 1rem 1.25rem !important;
    transition: transform 300ms var(--ease-spring),
                box-shadow 300ms var(--ease-smooth),
                border-color 300ms var(--ease-smooth) !important;
    animation: metric-pop 500ms var(--ease-out-expo) both;
}

div[data-testid="stMetric"]:hover {
    transform: translateY(-3px) !important;
    box-shadow: 0 8px 24px rgba(0, 155, 255, 0.08),
                0 2px 8px rgba(0, 0, 0, 0.2) !important;
    border-color: var(--border-glow) !important;
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

/* Stagger metric card entrances (nth-child cascade) */
div[data-testid="stMetric"]:nth-child(1) { animation-delay: 0ms; }
div[data-testid="stMetric"]:nth-child(2) { animation-delay: 80ms; }
div[data-testid="stMetric"]:nth-child(3) { animation-delay: 160ms; }
div[data-testid="stMetric"]:nth-child(4) { animation-delay: 240ms; }
div[data-testid="stMetric"]:nth-child(5) { animation-delay: 320ms; }

/* ============================================================
   TABS - smooth underline transition
   ============================================================ */
button[data-baseweb="tab"] {
    font-family: 'Wix Madefor Display', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
    transition: color 200ms var(--ease-smooth),
                opacity 200ms var(--ease-smooth) !important;
}

button[data-baseweb="tab"]:hover {
    opacity: 0.85 !important;
}

/* Tab panel content entrance */
div[data-baseweb="tab-panel"] {
    animation: fade-in-up 400ms var(--ease-out-expo) both;
}

/* ============================================================
   FILE UPLOADERS - border glow on hover
   ============================================================ */
section[data-testid="stFileUploader"] {
    border: 1px dashed var(--border-strong) !important;
    border-radius: 12px !important;
    transition: border-color 300ms var(--ease-smooth),
                box-shadow 300ms var(--ease-smooth) !important;
}

section[data-testid="stFileUploader"]:hover {
    border-color: var(--border-glow) !important;
    box-shadow: 0 0 20px rgba(0, 155, 255, 0.06) !important;
}

/* ============================================================
   EXPANDERS - smooth expand + hover
   ============================================================ */
details {
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    background: var(--surface) !important;
    transition: border-color 250ms var(--ease-smooth),
                box-shadow 250ms var(--ease-smooth) !important;
}

details:hover {
    border-color: var(--border-strong) !important;
}

details[open] {
    border-color: var(--border-glow) !important;
    box-shadow: 0 4px 16px rgba(0, 155, 255, 0.05) !important;
}

details[open] > summary ~ * {
    animation: fade-in-up 300ms var(--ease-out-expo) both;
}

/* ============================================================
   CODE BLOCKS
   ============================================================ */
code {
    background: var(--deep-navy) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}

/* ============================================================
   DATA FRAMES - subtle entrance
   ============================================================ */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    animation: scale-in 400ms var(--ease-out-expo) both;
}

/* ============================================================
   BUTTONS - spring feedback + gradient animation
   ============================================================ */

/* Download button */
.stDownloadButton > button {
    background: var(--pattern-blue) !important;
    color: white !important;
    font-weight: 600 !important;
    border: none !important;
    border-radius: 8px !important;
    transition: transform 150ms var(--ease-spring),
                box-shadow 200ms var(--ease-smooth),
                filter 200ms var(--ease-smooth) !important;
}

.stDownloadButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px var(--pattern-blue-glow) !important;
    filter: brightness(1.1) !important;
}

.stDownloadButton > button:active {
    transform: scale(0.97) translateY(0) !important;
    box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.15) !important;
}

/* Primary action button - animated gradient */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #009bff 0%, #770bff 50%, #009bff 100%) !important;
    background-size: 200% 200% !important;
    color: white !important;
    font-weight: 600 !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.75rem 2rem !important;
    transition: transform 150ms var(--ease-spring),
                box-shadow 250ms var(--ease-smooth),
                filter 200ms var(--ease-smooth) !important;
}

.stButton > button[kind="primary"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 28px var(--violet-glow),
                0 4px 12px var(--pattern-blue-glow) !important;
    animation: gradient-rotate 3s linear infinite !important;
    filter: brightness(1.08) !important;
}

.stButton > button[kind="primary"]:active {
    transform: scale(0.96) !important;
    box-shadow: inset 0 2px 6px rgba(0, 0, 0, 0.2) !important;
    filter: brightness(0.95) !important;
}

/* ============================================================
   STATUS WIDGETS & ALERTS
   ============================================================ */
[data-testid="stStatusWidget"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    animation: fade-in-up 400ms var(--ease-out-expo) both;
}

/* Success/info/warning/error alerts - entrance animation */
div[data-testid="stAlert"] {
    animation: fade-in-left 350ms var(--ease-out-expo) both;
    border-radius: 12px !important;
}

/* ============================================================
   HERO & LANDING
   ============================================================ */
.hero {
    padding: 2rem 0;
}

.hero h1 {
    font-size: 40px !important;
    font-weight: 800 !important;
    letter-spacing: -0.03em !important;
    line-height: 1.1 !important;
    margin-bottom: 0.5rem !important;
    animation: hero-reveal 700ms var(--ease-out-expo) both;
}

.overline {
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--pattern-blue);
    margin-bottom: 0.25rem;
    animation: fade-in-left 400ms var(--ease-out-expo) both;
}

.empty-state {
    text-align: center;
    padding: 3rem 2rem;
    color: var(--text-tertiary);
}

/* ============================================================
   SKELETON LOADING - shimmer effect for processing states
   ============================================================ */
.skeleton {
    background: linear-gradient(
        90deg,
        var(--skeleton-base) 25%,
        var(--skeleton-shine) 50%,
        var(--skeleton-base) 75%
    );
    background-size: 200% 100%;
    animation: shimmer 1.5s ease-in-out infinite;
    border-radius: 8px;
}

/* ============================================================
   PROGRESS BAR - gradient glow
   ============================================================ */
div[data-testid="stProgress"] > div > div > div {
    background: linear-gradient(90deg, #009bff, #770bff) !important;
    border-radius: 4px !important;
    box-shadow: 0 0 12px var(--pattern-blue-glow) !important;
    transition: width 300ms var(--ease-out-expo) !important;
}

/* ============================================================
   SELECTBOX & INPUTS - focus glow
   ============================================================ */
div[data-baseweb="select"] > div {
    transition: border-color 200ms var(--ease-smooth),
                box-shadow 200ms var(--ease-smooth) !important;
}

div[data-baseweb="select"] > div:focus-within {
    border-color: var(--pattern-blue) !important;
    box-shadow: 0 0 0 3px var(--pattern-blue-glow) !important;
}

input[type="text"]:focus,
input[type="password"]:focus,
input[type="number"]:focus {
    border-color: var(--pattern-blue) !important;
    box-shadow: 0 0 0 3px var(--pattern-blue-glow) !important;
}

/* ============================================================
   TOOLTIP / HOVER INFO
   ============================================================ */
[data-testid="stTooltipIcon"] {
    transition: opacity 200ms var(--ease-smooth) !important;
}

[data-testid="stTooltipIcon"]:hover {
    opacity: 0.7 !important;
}

/* ============================================================
   SIDEBAR DIVIDERS - subtle fade
   ============================================================ */
section[data-testid="stSidebar"] hr {
    border-color: var(--border) !important;
    opacity: 0.5;
}

/* ============================================================
   RADIO BUTTONS (validation mode toggle)
   ============================================================ */
div[data-testid="stRadio"] label {
    transition: opacity 200ms var(--ease-smooth) !important;
}

div[data-testid="stRadio"] label:hover {
    opacity: 0.85 !important;
}
</style>
"""

st.markdown(PATTERN_CSS, unsafe_allow_html=True)


# ============================================================
# PATTERN LOGO (official wordmark, white text for dark bg)
# ============================================================

PATTERN_LOGO_SVG = """
<div class="sidebar-logo" style="margin-bottom: 1rem;">
    <svg xmlns="http://www.w3.org/2000/svg" width="160" height="32" viewBox="0 0 191 38" fill="none"><g clip-path="url(#clip0)"><path d="M23.1323 0.277129L0.336866 22.8367C-0.0379489 23.2076 -0.0379491 23.809 0.336866 24.1799L5.95075 29.7357C6.32557 30.1067 6.93326 30.1067 7.30808 29.7357L30.1035 7.1762C30.4783 6.80526 30.4783 6.20385 30.1035 5.83292L24.4896 0.277128C24.1148 -0.0938081 23.5071 -0.0938066 23.1323 0.277129Z" fill="#009BFF"/><path d="M32.5193 9.56975L19.1171 22.8332C18.7423 23.2042 18.7423 23.8056 19.1171 24.1765L24.731 29.7323C25.1058 30.1032 25.7135 30.1032 26.0884 29.7323L39.4905 16.4688C39.8654 16.0979 39.8654 15.4965 39.4905 15.1255L33.8767 9.56975C33.5018 9.19881 32.8942 9.19881 32.5193 9.56975Z" fill="#009BFF"/><path d="M72.0318 17.9793C72.0318 24.7983 66.8064 30.0154 60.5177 30.0154C56.9126 30.0154 54.1845 28.5504 52.4273 26.1703V37.4408C52.4273 37.5892 52.3677 37.7314 52.2618 37.8363C52.1558 37.9411 52.0121 38 51.8622 38H47.9977C47.8478 38 47.7041 37.9411 47.5981 37.8363C47.4921 37.7314 47.4326 37.5892 47.4326 37.4408V7.09944C47.4326 6.95113 47.4921 6.8089 47.5981 6.70403C47.7041 6.59916 47.8478 6.54025 47.9977 6.54025H51.8622C52.0121 6.54025 52.1558 6.59916 52.2618 6.70403C52.3677 6.8089 52.4273 6.95113 52.4273 7.09944V9.83398C54.1781 7.40976 56.9126 5.94482 60.5177 5.94482C66.8064 5.94482 72.0318 11.2075 72.0318 17.9793ZM67.0388 17.9793C67.0388 13.7263 63.8936 10.6578 59.733 10.6578C55.5724 10.6578 52.4273 13.7247 52.4273 17.9793C52.4273 22.2339 55.5708 25.3008 59.733 25.3008C63.8952 25.3008 67.0388 22.2355 67.0388 17.9793Z" fill="#fcfcfc"/><path d="M98.4814 7.09944V28.8608C98.4814 29.0091 98.4219 29.1513 98.3159 29.2562C98.2099 29.361 98.0662 29.42 97.9164 29.42H94.0534C93.9035 29.42 93.7598 29.361 93.6538 29.2562C93.5479 29.1513 93.4883 29.0091 93.4883 28.8608V26.1246C91.7375 28.5504 89.003 30.0154 85.3963 30.0154C79.1076 30.0154 73.8838 24.7527 73.8838 17.9793C73.8838 11.1619 79.1076 5.94482 85.3963 5.94482C89.003 5.94482 91.7311 7.40976 93.4883 9.7883V7.09944C93.4883 6.95113 93.5479 6.8089 93.6538 6.70403C93.7598 6.59916 93.9035 6.54025 94.0534 6.54025H97.9164C98.0662 6.54025 98.2099 6.59916 98.3159 6.70403C98.4219 6.8089 98.4814 6.95113 98.4814 7.09944V7.09944ZM93.4883 17.9793C93.4883 13.7263 90.3432 10.6578 86.1826 10.6578C82.022 10.6578 78.8768 13.7247 78.8768 17.9793C78.8768 22.2339 82.022 25.3008 86.1826 25.3008C90.3432 25.3008 93.4883 22.2355 93.4883 17.9793V17.9793Z" fill="#fcfcfc"/><path d="M139.785 25.4851C142.343 25.4851 144.31 24.4345 145.472 23.0168C145.557 22.9161 145.675 22.8489 145.806 22.8272C145.937 22.8055 146.071 22.8309 146.185 22.8986L149.33 24.718C149.398 24.7567 149.458 24.8092 149.504 24.8721C149.551 24.9351 149.584 25.007 149.6 25.0833C149.617 25.1596 149.617 25.2384 149.6 25.3147C149.584 25.391 149.551 25.463 149.505 25.5261C147.356 28.3378 144.023 30.0154 139.74 30.0154C132.11 30.0154 127.166 24.844 127.166 17.9793C127.166 11.206 132.113 5.94482 139.373 5.94482C146.263 5.94482 150.979 11.436 150.979 18.025C150.965 18.7152 150.904 19.4036 150.794 20.0853H132.387C133.173 23.6547 136.087 25.4851 139.785 25.4851ZM145.935 16.0576C145.241 12.1196 142.328 10.4294 139.323 10.4294C135.578 10.4294 133.034 12.6252 132.342 16.0576H145.935Z" fill="#fcfcfc"/><path d="M191.055 15.3712V28.8612C191.055 29.0095 190.996 29.1517 190.89 29.2566C190.784 29.3615 190.64 29.4204 190.49 29.4204H186.627C186.477 29.4204 186.334 29.3615 186.228 29.2566C186.122 29.1517 186.062 29.0095 186.062 28.8612V15.8753C186.062 12.3973 184.026 10.5669 180.883 10.5669C177.599 10.5669 175.011 12.4886 175.011 17.1559V28.8612C175.011 28.9348 174.997 29.0076 174.968 29.0756C174.94 29.1435 174.898 29.2052 174.845 29.2572C174.793 29.3091 174.73 29.3503 174.661 29.3783C174.593 29.4063 174.519 29.4206 174.445 29.4204H170.582C170.432 29.4204 170.288 29.3615 170.182 29.2566C170.076 29.1517 170.017 29.0095 170.017 28.8612V7.09988C170.017 6.95158 170.076 6.80934 170.182 6.70447C170.288 6.5996 170.432 6.54069 170.582 6.54069H174.446C174.521 6.54048 174.594 6.55479 174.663 6.5828C174.732 6.61081 174.794 6.65197 174.847 6.70392C174.899 6.75586 174.941 6.81758 174.97 6.88552C174.998 6.95347 175.013 7.02632 175.013 7.09988V9.46267C176.538 7.08256 179.035 5.93896 182.175 5.93896C187.356 5.94527 191.055 9.4233 191.055 15.3712Z" fill="#fcfcfc"/><path d="M165.186 6.12744C162.274 6.12744 159.456 7.27261 158.065 10.3805V7.09934C158.065 6.95103 158.006 6.8088 157.9 6.70393C157.794 6.59906 157.65 6.54014 157.5 6.54014H153.637C153.487 6.54014 153.344 6.59906 153.238 6.70393C153.132 6.8088 153.072 6.95103 153.072 7.09934V28.8607C153.072 29.009 153.132 29.1512 153.238 29.2561C153.344 29.3609 153.487 29.4198 153.637 29.4198H157.5C157.65 29.4198 157.794 29.3609 157.9 29.2561C158.006 29.1512 158.065 29.009 158.065 28.8607V17.8878C158.065 12.7637 161.823 11.4815 165.186 11.4815H166.926C167.076 11.4815 167.22 11.4226 167.326 11.3177C167.432 11.2129 167.491 11.0706 167.491 10.9223V6.68821C167.491 6.61464 167.477 6.54176 167.449 6.47373C167.42 6.40571 167.379 6.34387 167.326 6.29178C167.274 6.23969 167.211 6.19836 167.143 6.17016C167.074 6.14196 167 6.12744 166.926 6.12744H165.186Z" fill="#fcfcfc"/><path d="M112.505 11.2989C112.579 11.2991 112.653 11.2848 112.721 11.2568C112.79 11.2287 112.853 11.1876 112.905 11.1356C112.958 11.0837 113 11.022 113.028 10.954C113.057 10.8861 113.071 10.8132 113.071 10.7397V7.0994C113.071 7.02584 113.057 6.95299 113.028 6.88504C113 6.8171 112.958 6.75538 112.905 6.70343C112.853 6.65149 112.79 6.61033 112.721 6.58232C112.653 6.55431 112.579 6.54 112.505 6.54021H106.561V0.554469C106.56 0.408335 106.501 0.268486 106.397 0.164857C106.293 0.0612278 106.152 0.00205319 106.004 0H102.133C101.984 0 101.84 0.0589149 101.734 0.163784C101.628 0.268653 101.568 0.410887 101.568 0.559194V22.6718C101.568 27.369 103.857 29.6247 108.634 29.6247H112.506C112.656 29.6243 112.799 29.5652 112.905 29.4604C113.011 29.3557 113.071 29.2137 113.071 29.0655V25.6001C113.071 25.5265 113.057 25.4537 113.028 25.3857C113 25.3178 112.958 25.256 112.905 25.2041C112.853 25.1521 112.79 25.111 112.721 25.083C112.653 25.055 112.579 25.0407 112.505 25.0409H109.533C107.255 25.0409 106.561 24.4549 106.561 22.2827V11.2989H112.505Z" fill="#fcfcfc"/><path d="M126.061 11.2989C126.211 11.2989 126.354 11.24 126.46 11.1351C126.566 11.0302 126.626 10.888 126.626 10.7397V7.0994C126.626 6.9511 126.566 6.80886 126.46 6.70399C126.354 6.59912 126.211 6.54021 126.061 6.54021H120.124V0.554469C120.123 0.406981 120.063 0.265959 119.957 0.16211C119.851 0.0582605 119.708 -5.26628e-06 119.559 3.57006e-10H115.696C115.546 3.57006e-10 115.402 0.0589149 115.296 0.163784C115.19 0.268653 115.131 0.410887 115.131 0.559194V22.6718C115.131 27.369 117.418 29.6247 122.196 29.6247H126.069C126.218 29.6239 126.361 29.5646 126.467 29.4599C126.572 29.3552 126.632 29.2134 126.632 29.0655V25.6001C126.632 25.5264 126.617 25.4536 126.588 25.3858C126.559 25.318 126.516 25.2565 126.463 25.205C126.41 25.1535 126.347 25.1128 126.278 25.0855C126.209 25.0581 126.135 25.0446 126.061 25.0456H123.089C120.812 25.0456 120.118 24.4596 120.118 22.2874V11.2989H126.061Z" fill="#fcfcfc"/></g><defs><clipPath id="clip0"><rect width="191" height="38" fill="white"/></clipPath></defs></svg>
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


def build_scraper_output(row):
    """Consolidate scraped fields into a single text block for the output."""
    parts = []
    desc = row.get("page_description", "")
    if desc and str(desc).strip():
        parts.append(f"PAGE DESCRIPTION:\n{str(desc).strip()}")

    features = row.get("features", "")
    if features and str(features).strip():
        items = str(features).split(" | ")
        parts.append("FEATURES:\n" + "\n".join(f"- {f}" for f in items))

    materials = row.get("materials", "")
    if materials and str(materials).strip():
        parts.append(f"MATERIALS: {str(materials).strip()}")

    additional = row.get("additional_info", "")
    if additional and str(additional).strip():
        items = str(additional).split(" | ")
        parts.append("ADDITIONAL INFO:\n" + "\n".join(f"- {a}" for a in items))

    return "\n\n".join(parts) if parts else ""


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown(PATTERN_LOGO_SVG, unsafe_allow_html=True)
    st.markdown('<div class="gradient-bar"></div>', unsafe_allow_html=True)

    # --- Shared: Feed upload ---
    st.markdown('<p class="overline">Product feed</p>', unsafe_allow_html=True)

    feed_file = st.file_uploader(
        "GMC feed export",
        type=["csv", "tsv", "xlsx", "xls"],
        help="Product feed from Google Merchant Centre",
    )

    st.markdown("---")

    # --- Column mapping ---
    st.markdown('<p class="overline">Column mapping</p>', unsafe_allow_html=True)

    with st.expander("Feed columns", expanded=False):
        id_col = st.text_input("SKU ID column", value="id")
        title_col = st.text_input("Title column", value="title")
        product_type_col = st.text_input("Product type column", value="product type")
        url_col = st.text_input("Product URL column", value="link")

    st.markdown("---")

    # --- Bifrost AI config ---
    st.markdown('<p class="overline">AI enrichment (Bifrost)</p>', unsafe_allow_html=True)

    bifrost_key = st.text_input(
        "Bifrost API key",
        type="password",
        placeholder="sk-bf-...",
        help="Your Bifrost virtual key for Claude access",
    )

    bifrost_model = st.selectbox(
        "Model",
        options=[
            "anthropic/claude-sonnet-4-20250514",
            "anthropic/claude-4-opus-20250514",
            "anthropic/claude-haiku-4-5-20251001",
            "anthropic/claude-opus-4-1-20250805",
            "anthropic/claude-opus-4-5-20251101",
            "anthropic/claude-opus-4-7-20260416",
            "anthropic/claude-sonnet-4-5-20250929",
            "openai/gpt-5.4-nano",
        ],
        index=0,
        help="Model to use via Bifrost. Sonnet recommended for cost/quality balance.",
    )

    st.markdown("---")
    st.caption("Feed Enrichment Tool v1.2")
    st.caption("Built by Pattern's feed team")


# ============================================================
# LANDING STATE (no feed uploaded)
# ============================================================

if not feed_file:
    st.markdown('<div class="hero">', unsafe_allow_html=True)
    st.markdown(
        "# Feed <span class='accent'>Enrichment</span>",
        unsafe_allow_html=True,
    )
    st.markdown('<div class="gradient-bar"></div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        "Gather additional product information to feed into the optimisation tool. "
        "Upload a GMC feed in the sidebar to get started."
    )

    st.markdown("")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown('<p class="overline">01 _____ Search intelligence</p>', unsafe_allow_html=True)
        st.markdown(
            "Match Google Ads search term n-grams to products. "
            "Outputs keyword themes and search context for description prompts."
        )

    with col2:
        st.markdown('<p class="overline">02 _____ Page scraper</p>', unsafe_allow_html=True)
        st.markdown(
            "Scrape product pages to extract descriptions, features, "
            "and materials that aren't in the feed."
        )

    with col3:
        st.markdown('<p class="overline">03 _____ AI enrichment</p>', unsafe_allow_html=True)
        st.markdown(
            "Send product data + scraper + search context to Claude via Bifrost. "
            "Gets back an AI brief per product with selling points and content gaps."
        )

    col4, col5, _ = st.columns(3)

    with col4:
        st.markdown('<p class="overline">04 _____ Validation</p>', unsafe_allow_html=True)
        st.markdown(
            "AI-powered QA that validates enrichment data and optimised output "
            "against the original feed. Catches hallucinated attributes."
        )

    with col5:
        st.markdown('<p class="overline">05 _____ Download</p>', unsafe_allow_html=True)
        st.markdown(
            "Get a 5-column enrichment file (id, title, scraper output, "
            "search context, AI brief) ready for the feed optimisation tool."
        )

    st.markdown("---")

    st.markdown(
        "**How it works** - "
        "This tool gathers additional information about each product from three sources: "
        "Google Ads search data (what shoppers actually search), product page content "
        "(descriptions, features, materials not in the feed), and AI-generated briefs "
        "(selling points, content gaps, description guidance via Bifrost/Claude). "
        "The output is a 5-column enrichment file that feeds into the feed optimisation tool. "
        "A built-in validation step catches hallucinated attributes before anything goes to the client."
    )

    st.stop()


# ============================================================
# FEED LOADED - PARSE AND VALIDATE
# ============================================================

with st.spinner("Loading feed..."):
    feed = load_file(feed_file)

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

# Feed stats
s1, s2, s3 = st.columns(3)
s1.metric("Products in feed", f"{len(feed):,}")

url_count = feed[url_col].notna().sum() if url_col in feed.columns else 0
s2.metric("With URLs", f"{url_count:,}")

desc_count = feed["description"].notna().sum() if "description" in feed.columns else 0
s3.metric("With descriptions", f"{desc_count:,}")

st.markdown("")

# Tabs
tab_search, tab_scraper, tab_ai, tab_validate, tab_output, tab_explore = st.tabs([
    "Search intelligence",
    "Page scraper",
    "AI enrichment",
    "Validation",
    "Output",
    "Explore matches",
])


# ============================================================
# TAB: SEARCH INTELLIGENCE
# ============================================================

with tab_search:
    st.markdown(
        "Match Google Ads search term n-grams to products by title and attribute relevance. "
        "Produces a search context block for each product."
    )

    st.markdown("")
    st.markdown('<p class="overline">Search terms data</p>', unsafe_allow_html=True)

    search_file = st.file_uploader(
        "Supermetrics search terms export",
        type=["csv", "xlsx", "xls"],
        help="Google Ads search term data from Supermetrics",
        key="search_terms_uploader",
    )

    if search_file:
        search_terms = load_file(search_file)

        qs1, qs2, qs3 = st.columns(3)
        qs1.metric("Search terms loaded", f"{len(search_terms):,}")

        conv_col = next(
            (c for c in ["Conversions", "conversions", "Conv."] if c in search_terms.columns),
            None,
        )
        if conv_col:
            converting_count = (search_terms[conv_col] > 0).sum()
            qs2.metric("Converting", f"{converting_count:,}")
            qs3.metric("Zero-conversion", f"{len(search_terms) - converting_count:,}")

        st.markdown("")

        with st.expander("Matching parameters", expanded=False):
            p1, p2 = st.columns(2)
            with p1:
                min_impressions = st.number_input(
                    "Min impressions", min_value=1, max_value=1000, value=10,
                    help="Filter search terms below this threshold",
                )
            with p2:
                relevance_threshold = st.slider(
                    "Relevance threshold", min_value=0.1, max_value=0.8, value=0.3, step=0.05,
                    help="Higher = stricter matching (0.3 recommended)",
                )

        st.markdown("")

        if st.button("Run search intelligence", type="primary", use_container_width=True):
            with st.status("Running enrichment...", expanded=True) as status:
                st.write("Extracting n-grams from search terms...")
                t0 = time.time()

                matched = match_search_terms_to_skus(
                    search_terms, feed,
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

                st.session_state["search_contexts"] = search_contexts
                st.session_state["keyword_themes"] = keyword_themes_compact
                st.session_state["matched"] = matched
                st.session_state["coverage"] = coverage

                status.update(label="Search intelligence complete", state="complete")

        # Results preview
        if "coverage" in st.session_state:
            coverage = st.session_state["coverage"]

            st.markdown("---")
            st.markdown('<p class="overline">Results</p>', unsafe_allow_html=True)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("SKUs with data", f"{coverage['skus_with_search_data']:,}")
            m2.metric("Coverage", f"{coverage['coverage_pct']}%")
            m3.metric("N-grams matched", f"{coverage['total_unique_terms']:,}")
            m4.metric("Converting n-grams", f"{coverage['converting_terms']:,}")

            st.markdown("")
            st.markdown('<p class="overline">Sample search context</p>', unsafe_allow_html=True)

            search_contexts = st.session_state["search_contexts"]
            keyword_themes = st.session_state["keyword_themes"]

            # Find products with rich context
            sample_ids = [
                sid for sid, ctx in search_contexts.items()
                if len(ctx) > 50
            ][:5]

            for sku_id in sample_ids:
                # Find title for this SKU
                sku_row = feed[feed[id_col].astype(str) == sku_id]
                if len(sku_row) > 0:
                    title = str(sku_row.iloc[0].get(title_col, ""))[:80]
                else:
                    title = sku_id
                with st.expander(title):
                    kw = keyword_themes.get(sku_id, "")
                    if kw:
                        st.markdown(f"**Keyword themes:** {kw}")
                    st.code(search_contexts[sku_id], language=None)

            st.success("Search intelligence ready. Go to the **Output** tab to download.")

    else:
        st.info("Upload a Supermetrics search terms export above to use search intelligence.")


# ============================================================
# TAB: PAGE SCRAPER
# ============================================================

with tab_scraper:
    st.markdown(
        "Scrape product pages to extract descriptions, features, and materials "
        "not in the GMC feed. Supports Shopify (JSON endpoint) and generic HTML."
    )

    st.markdown("")

    if url_col not in feed.columns:
        st.warning(
            f"Feed doesn't have a `{url_col}` column. "
            f"Update the URL column name in sidebar Column mapping."
        )
    else:
        url_count_valid = feed[url_col].notna().sum()
        st.markdown(f"**{url_count_valid:,}** products have URLs available for scraping.")

        st.markdown("")
        st.markdown('<p class="overline">Scraper settings</p>', unsafe_allow_html=True)

        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            max_products = st.number_input(
                "Max products to scrape",
                min_value=1, max_value=url_count_valid,
                value=min(50, url_count_valid),
                help="Start small to test, then increase.",
            )
        with sc2:
            delay = st.number_input(
                "Delay between requests (s)",
                min_value=0.5, max_value=5.0, value=1.0, step=0.5,
                help="Rate limiting to avoid getting blocked.",
            )
        with sc3:
            est_time = max_products * delay
            est_min = est_time / 60
            if est_min < 1:
                st.metric("Estimated time", f"{est_time:.0f}s")
            else:
                st.metric("Estimated time", f"{est_min:.1f} min")

        st.markdown("")

        if st.button("Scrape product pages", type="primary", use_container_width=True):
            scrape_progress = st.progress(0, text="Starting scraper...")

            def update_scrape_progress(current, total):
                pct = current / total
                scrape_progress.progress(pct, text=f"Scraping {current}/{total} products...")

            t0 = time.time()
            scraped = scrape_feed_urls(
                feed,
                url_col=url_col,
                id_col=id_col,
                max_products=max_products,
                delay=delay,
                progress_callback=update_scrape_progress,
            )
            elapsed = time.time() - t0

            scrape_progress.progress(1.0, text="Scraping complete")

            # Build consolidated scraper_output column
            scraped["scraper_output"] = scraped.apply(build_scraper_output, axis=1)

            st.session_state["scraped"] = scraped
            st.session_state["scrape_elapsed"] = elapsed

        # Scrape results
        if "scraped" in st.session_state:
            scraped = st.session_state["scraped"]
            elapsed = st.session_state.get("scrape_elapsed", 0)

            st.markdown("---")
            st.markdown('<p class="overline">Scrape results</p>', unsafe_allow_html=True)

            ok_count = (scraped["scrape_status"] == "ok").sum()
            has_desc = (scraped["page_description"].fillna("").str.len() > 0).sum()
            has_features = (scraped["features"].fillna("").str.len() > 0).sum()
            has_materials = (scraped["materials"].fillna("").str.len() > 0).sum()

            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Scraped successfully", f"{ok_count}/{len(scraped)}")
            r2.metric("With descriptions", f"{has_desc:,}")
            r3.metric("With features", f"{has_features:,}")
            r4.metric("With materials", f"{has_materials:,}")

            if elapsed > 0:
                st.caption(f"Completed in {elapsed:.1f}s")

            # Show failures
            failed = scraped[scraped["scrape_status"] != "ok"]
            if len(failed) > 0:
                with st.expander(f"Failed scrapes ({len(failed)})", expanded=False):
                    st.dataframe(failed[["sku_id", "scrape_status"]], use_container_width=True, height=200)

            # Feed vs page comparison
            try:
                comparison = compare_feed_vs_scraped(feed, scraped, id_col=id_col)
                if len(comparison) > 0:
                    st.markdown("")
                    st.markdown('<p class="overline">Feed vs page comparison</p>', unsafe_allow_html=True)
                    avg_feed = comparison["feed_desc_len"].mean()
                    avg_page = comparison["page_desc_len"].mean()
                    richer = (comparison["desc_delta"] > 50).sum()

                    c1, c2, c3 = st.columns(3)
                    c1.metric("Avg feed description", f"{avg_feed:.0f} chars")
                    c2.metric("Avg page description", f"{avg_page:.0f} chars")
                    c3.metric("Richer on page", f"{richer}/{len(comparison)}")
            except Exception:
                pass

            # Sample scraped data
            st.markdown("")
            st.markdown('<p class="overline">Sample scraper output</p>', unsafe_allow_html=True)

            ok_scraped = scraped[(scraped["scrape_status"] == "ok") & (scraped["scraper_output"].str.len() > 0)]
            for _, row in ok_scraped.head(5).iterrows():
                label = str(row.get("page_title", row["sku_id"]))[:80]
                with st.expander(label):
                    st.code(row["scraper_output"], language=None)

            st.success("Scraper data ready. Go to the **Output** tab to download.")


# ============================================================
# TAB: AI ENRICHMENT (Bifrost/Claude briefs)
# ============================================================

with tab_ai:
    st.markdown(
        "Send product data alongside scraper output and search context to Claude via Bifrost. "
        "Returns an AI brief per product with key selling points, content gaps, and description guidance."
    )

    st.markdown('<div class="gradient-bar"></div>', unsafe_allow_html=True)

    if not bifrost_key:
        st.warning("Enter your Bifrost API key in the sidebar to use AI enrichment.")
    else:
        has_search_ai = "search_contexts" in st.session_state
        has_scraper_ai = "scraped" in st.session_state

        # Status
        ai_s1, ai_s2 = st.columns(2)
        with ai_s1:
            if has_scraper_ai:
                ok = (st.session_state["scraped"]["scrape_status"] == "ok").sum()
                st.success(f"Scraper data available: {ok:,} products")
            else:
                st.info("No scraper data yet - run Page scraper first (optional)")
        with ai_s2:
            if has_search_ai:
                st.success(f"Search data available: {st.session_state['coverage']['skus_with_search_data']:,} SKUs")
            else:
                st.info("No search data yet - run Search intelligence first (optional)")

        st.markdown("")

        # Config
        st.markdown('<p class="overline">AI brief settings</p>', unsafe_allow_html=True)

        ai_c1, ai_c2 = st.columns(2)
        with ai_c1:
            max_briefs = st.number_input(
                "Max products to process",
                min_value=1, max_value=len(feed),
                value=min(50, len(feed)),
                help="Start with a small batch to test quality before running the full feed.",
                key="max_briefs",
            )
        with ai_c2:
            ai_delay = st.number_input(
                "Delay between API calls (s)",
                min_value=0.2, max_value=5.0, value=0.5, step=0.1,
                help="Rate limiting for Bifrost API.",
                key="ai_delay",
            )

        est_time_ai = max_briefs * ai_delay
        st.caption(f"Estimated time: ~{est_time_ai / 60:.1f} min for {max_briefs} products")

        st.markdown("")

        if st.button("Generate AI briefs", type="primary", use_container_width=True, key="run_ai_briefs"):
            # Build maps from session state
            scraper_map = {}
            if has_scraper_ai:
                scraped = st.session_state["scraped"]
                scraper_map = scraped.set_index("sku_id")["scraper_output"].to_dict()

            search_context_map = {}
            if has_search_ai:
                search_context_map = st.session_state["search_contexts"]

            # Prepare product list
            products = []
            for _, row in feed.head(max_briefs).iterrows():
                product = {}
                for col in feed.columns:
                    val = row.get(col, "")
                    if pd.notna(val):
                        product[col] = str(val)
                products.append(product)

            # Run
            brief_progress = st.progress(0, text="Generating AI briefs...")

            def update_brief_progress(current, total):
                pct = current / total
                brief_progress.progress(pct, text=f"Processing {current}/{total} products...")

            try:
                client = get_client(bifrost_key)
                t0 = time.time()
                briefs = batch_generate_briefs(
                    client, bifrost_model, products,
                    scraper_map=scraper_map,
                    search_context_map=search_context_map,
                    delay=ai_delay,
                    progress_callback=update_brief_progress,
                )
                elapsed = time.time() - t0

                brief_progress.progress(1.0, text="AI briefs complete")

                st.session_state["ai_briefs"] = briefs
                st.session_state["ai_briefs_elapsed"] = elapsed
                st.session_state["ai_briefs_count"] = len(briefs)

            except Exception as e:
                st.error(f"Bifrost API error: {str(e)[:200]}")

        # Results
        if "ai_briefs" in st.session_state:
            briefs = st.session_state["ai_briefs"]
            elapsed = st.session_state.get("ai_briefs_elapsed", 0)

            st.markdown("---")
            st.markdown('<p class="overline">AI brief results</p>', unsafe_allow_html=True)

            brief_count = len(briefs)
            non_empty = sum(1 for b in briefs.values() if b and not b.startswith("[AI brief"))
            failed = brief_count - non_empty

            b1, b2, b3 = st.columns(3)
            b1.metric("Briefs generated", f"{non_empty:,}")
            b2.metric("Failed", f"{failed:,}")
            if elapsed > 0:
                b3.metric("Time", f"{elapsed:.1f}s")

            # Sample briefs
            st.markdown("")
            st.markdown('<p class="overline">Sample AI briefs</p>', unsafe_allow_html=True)

            sample_briefs = [
                (sku_id, brief) for sku_id, brief in briefs.items()
                if brief and not brief.startswith("[AI brief")
            ][:5]

            for sku_id, brief in sample_briefs:
                sku_row = feed[feed[id_col].astype(str) == sku_id]
                if len(sku_row) > 0:
                    label = str(sku_row.iloc[0].get(title_col, ""))[:80]
                else:
                    label = sku_id
                with st.expander(label):
                    st.markdown(brief)

            st.success("AI briefs ready. Go to the **Output** tab to download.")


# ============================================================
# TAB: VALIDATION (AI-powered QA)
# ============================================================

with tab_validate:
    st.markdown(
        "AI-powered validation that checks enrichment data and optimised output "
        "against the original feed. Catches hallucinated attributes, wrong colours, "
        "fabricated claims, and factual errors."
    )

    st.markdown('<div class="gradient-bar"></div>', unsafe_allow_html=True)

    if not bifrost_key:
        st.warning("Enter your Bifrost API key in the sidebar to use validation.")
    else:
        val_mode = st.radio(
            "Validation mode",
            options=["Validate enrichment data", "Validate optimised output"],
            help="Stage 1: check scraper/search data before optimisation. Stage 2: check AI-generated titles/descriptions after optimisation.",
            horizontal=True,
            key="val_mode",
        )

        st.markdown("")

        # ---- MODE 1: Validate enrichment data ----
        if val_mode == "Validate enrichment data":
            st.markdown(
                "Checks scraped page content and search context against the original feed "
                "for conflicts, wrong product matches, and data quality issues."
            )

            has_scraper_val = "scraped" in st.session_state
            has_search_val = "search_contexts" in st.session_state

            if not has_scraper_val and not has_search_val:
                st.info("Run the Page scraper or Search intelligence first to have data to validate.")
            else:
                val_c1, val_c2 = st.columns(2)
                with val_c1:
                    max_validate = st.number_input(
                        "Max products to validate",
                        min_value=1, max_value=len(feed),
                        value=min(50, len(feed)),
                        key="max_validate_enrich",
                    )
                with val_c2:
                    val_delay = st.number_input(
                        "Delay (s)", min_value=0.1, max_value=3.0, value=0.3, step=0.1,
                        key="val_delay_enrich",
                    )

                st.markdown("")

                if st.button("Validate enrichment data", type="primary", use_container_width=True, key="run_val_enrich"):
                    scraper_map = {}
                    if has_scraper_val:
                        scraper_map = st.session_state["scraped"].set_index("sku_id")["scraper_output"].to_dict()

                    search_context_map = {}
                    if has_search_val:
                        search_context_map = st.session_state["search_contexts"]

                    products = []
                    for _, row in feed.head(max_validate).iterrows():
                        product = {}
                        for col in feed.columns:
                            val = row.get(col, "")
                            if pd.notna(val):
                                product[col] = str(val)
                        products.append(product)

                    val_progress = st.progress(0, text="Validating enrichment data...")

                    def update_val_progress(current, total):
                        val_progress.progress(current / total, text=f"Validating {current}/{total}...")

                    try:
                        client = get_client(bifrost_key)
                        results = batch_validate_enrichment(
                            client, bifrost_model, products,
                            scraper_map=scraper_map,
                            search_context_map=search_context_map,
                            delay=val_delay,
                            progress_callback=update_val_progress,
                        )
                        val_progress.progress(1.0, text="Validation complete")
                        st.session_state["enrichment_validation"] = results

                    except Exception as e:
                        st.error(f"Validation error: {str(e)[:200]}")

                # Show enrichment validation results
                if "enrichment_validation" in st.session_state:
                    results = st.session_state["enrichment_validation"]

                    st.markdown("---")
                    st.markdown('<p class="overline">Enrichment validation results</p>', unsafe_allow_html=True)

                    scores = [r["confidence_score"] for r in results.values()]
                    avg_score = sum(scores) / len(scores) if scores else 0
                    high_conf = sum(1 for s in scores if s >= 90)
                    medium_conf = sum(1 for s in scores if 70 <= s < 90)
                    low_conf = sum(1 for s in scores if 50 <= s < 70)
                    critical = sum(1 for s in scores if s < 50)

                    v1, v2, v3, v4, v5 = st.columns(5)
                    v1.metric("Avg confidence", f"{avg_score:.0f}/100")
                    v2.metric("Clean (90+)", f"{high_conf:,}")
                    v3.metric("Minor (70-89)", f"{medium_conf:,}")
                    v4.metric("Review (50-69)", f"{low_conf:,}")
                    v5.metric("Critical (<50)", f"{critical:,}")

                    # Show flagged products
                    flagged = {
                        sku_id: r for sku_id, r in results.items()
                        if r["confidence_score"] < 90 and r["flags"]
                    }

                    if flagged:
                        st.markdown("")
                        st.markdown('<p class="overline">Flagged products</p>', unsafe_allow_html=True)

                        for sku_id, r in sorted(flagged.items(), key=lambda x: x[1]["confidence_score"]):
                            sku_row = feed[feed[id_col].astype(str) == sku_id]
                            title = str(sku_row.iloc[0].get(title_col, ""))[:60] if len(sku_row) > 0 else sku_id
                            score = r["confidence_score"]

                            if score < 50:
                                icon = "🔴"
                            elif score < 70:
                                icon = "🟡"
                            else:
                                icon = "🟢"

                            with st.expander(f"{icon} [{score}] {title}"):
                                st.markdown(f"**Summary:** {r['summary']}")
                                for flag in r["flags"]:
                                    st.markdown(f"- {flag}")
                    else:
                        st.success("All products passed validation with high confidence.")

        # ---- MODE 2: Validate optimised output ----
        else:
            st.markdown(
                "Upload your optimised feed (with new titles/descriptions) and validate "
                "against the original feed. Catches hallucinated colours, materials, "
                "wrong brands, and fabricated claims."
            )

            st.markdown("")
            st.markdown('<p class="overline">Optimised feed</p>', unsafe_allow_html=True)

            opt_file = st.file_uploader(
                "Upload optimised feed",
                type=["csv", "tsv", "xlsx", "xls"],
                help="Feed with AI-generated titles and/or descriptions to validate",
                key="opt_feed_upload",
            )

            if opt_file:
                opt_feed = load_file(opt_file)
                st.markdown(f"Loaded **{len(opt_feed):,}** products from optimised feed.")

                with st.expander("Column mapping for optimised feed", expanded=True):
                    opt_cols = list(opt_feed.columns)
                    oc1, oc2, oc3 = st.columns(3)
                    with oc1:
                        opt_id_col = st.selectbox("ID column", options=opt_cols, index=opt_cols.index("id") if "id" in opt_cols else 0, key="opt_id")
                    with oc2:
                        title_idx = next((i for i, c in enumerate(opt_cols) if "title" in c.lower() and "old" not in c.lower()), 0)
                        opt_title_col = st.selectbox("New title column", options=["(none)"] + opt_cols, index=title_idx + 1 if title_idx else 0, key="opt_title")
                    with oc3:
                        desc_idx = next((i for i, c in enumerate(opt_cols) if "description" in c.lower() and "old" not in c.lower()), 0)
                        opt_desc_col = st.selectbox("New description column", options=["(none)"] + opt_cols, index=desc_idx + 1 if desc_idx else 0, key="opt_desc")

                st.markdown("")

                ov_c1, ov_c2 = st.columns(2)
                with ov_c1:
                    max_validate_opt = st.number_input(
                        "Max products to validate",
                        min_value=1, max_value=len(opt_feed),
                        value=min(50, len(opt_feed)),
                        key="max_validate_opt",
                    )
                with ov_c2:
                    val_delay_opt = st.number_input(
                        "Delay (s)", min_value=0.1, max_value=3.0, value=0.3, step=0.1,
                        key="val_delay_opt",
                    )

                if st.button("Validate optimised output", type="primary", use_container_width=True, key="run_val_opt"):
                    # Build title and description maps from optimised feed
                    new_titles = {}
                    new_descriptions = {}

                    for _, row in opt_feed.head(max_validate_opt).iterrows():
                        sku_id = str(row[opt_id_col])
                        if opt_title_col and opt_title_col != "(none)":
                            val = row.get(opt_title_col, "")
                            if pd.notna(val):
                                new_titles[sku_id] = str(val)
                        if opt_desc_col and opt_desc_col != "(none)":
                            val = row.get(opt_desc_col, "")
                            if pd.notna(val):
                                new_descriptions[sku_id] = str(val)

                    # Match original products by ID
                    original_products = []
                    opt_ids = set(new_titles.keys()) | set(new_descriptions.keys())
                    for sku_id in opt_ids:
                        orig_row = feed[feed[id_col].astype(str) == sku_id]
                        if len(orig_row) > 0:
                            product = {}
                            for col in feed.columns:
                                val = orig_row.iloc[0].get(col, "")
                                if pd.notna(val):
                                    product[col] = str(val)
                            original_products.append(product)

                    if not original_products:
                        st.error("No matching products found between optimised feed and original feed. Check ID columns.")
                    else:
                        opt_progress = st.progress(0, text="Validating optimised output...")

                        def update_opt_progress(current, total):
                            opt_progress.progress(current / total, text=f"Validating {current}/{total}...")

                        try:
                            client = get_client(bifrost_key)
                            results = batch_validate_optimised(
                                client, bifrost_model, original_products,
                                new_titles=new_titles,
                                new_descriptions=new_descriptions,
                                delay=val_delay_opt,
                                progress_callback=update_opt_progress,
                            )
                            opt_progress.progress(1.0, text="Validation complete")
                            st.session_state["output_validation"] = results

                        except Exception as e:
                            st.error(f"Validation error: {str(e)[:200]}")

                # Show output validation results
                if "output_validation" in st.session_state:
                    results = st.session_state["output_validation"]

                    st.markdown("---")
                    st.markdown('<p class="overline">Output validation results</p>', unsafe_allow_html=True)

                    scores = [r["confidence_score"] for r in results.values()]
                    avg_score = sum(scores) / len(scores) if scores else 0
                    titles_ok = sum(1 for r in results.values() if r.get("title_ok", True))
                    descs_ok = sum(1 for r in results.values() if r.get("description_ok", True))
                    total_r = len(results)

                    high_sev = sum(
                        1 for r in results.values()
                        for f in r.get("flags", [])
                        if isinstance(f, dict) and f.get("severity") == "high"
                    )

                    ov1, ov2, ov3, ov4, ov5 = st.columns(5)
                    ov1.metric("Avg confidence", f"{avg_score:.0f}/100")
                    ov2.metric("Titles OK", f"{titles_ok}/{total_r}")
                    ov3.metric("Descriptions OK", f"{descs_ok}/{total_r}")
                    ov4.metric("High severity flags", f"{high_sev:,}")
                    ov5.metric("Products checked", f"{total_r:,}")

                    # Flagged products
                    flagged = {
                        sku_id: r for sku_id, r in results.items()
                        if r["confidence_score"] < 90 or any(
                            isinstance(f, dict) and f.get("severity") == "high"
                            for f in r.get("flags", [])
                        )
                    }

                    if flagged:
                        st.markdown("")
                        st.markdown('<p class="overline">Products needing review</p>', unsafe_allow_html=True)

                        for sku_id, r in sorted(flagged.items(), key=lambda x: x[1]["confidence_score"]):
                            sku_row = feed[feed[id_col].astype(str) == sku_id]
                            title = str(sku_row.iloc[0].get(title_col, ""))[:60] if len(sku_row) > 0 else sku_id
                            score = r["confidence_score"]

                            if score < 50:
                                icon = "🔴"
                            elif score < 70:
                                icon = "🟡"
                            else:
                                icon = "🟢"

                            title_status = "OK" if r.get("title_ok", True) else "ISSUE"
                            desc_status = "OK" if r.get("description_ok", True) else "ISSUE"

                            with st.expander(f"{icon} [{score}] {title}"):
                                st.markdown(f"**Summary:** {r['summary']}")
                                st.markdown(f"**Title:** {title_status} | **Description:** {desc_status}")

                                for flag in r.get("flags", []):
                                    if isinstance(flag, dict):
                                        sev = flag.get("severity", "?")
                                        field = flag.get("field", "?")
                                        issue = flag.get("issue", "")
                                        sev_color = {"high": "red", "medium": "orange", "low": "blue"}.get(sev, "gray")
                                        st.markdown(f"- :{sev_color}[**{sev.upper()}**] `{field}`: {issue}")
                                    else:
                                        st.markdown(f"- {flag}")

                        # Download validation report
                        st.markdown("")
                        val_rows = []
                        for sku_id, r in results.items():
                            row_data = {
                                "id": sku_id,
                                "confidence_score": r["confidence_score"],
                                "title_ok": r.get("title_ok", True),
                                "description_ok": r.get("description_ok", True),
                                "summary": r["summary"],
                                "flags": "; ".join(
                                    f.get("issue", str(f)) if isinstance(f, dict) else str(f)
                                    for f in r.get("flags", [])
                                ),
                            }
                            val_rows.append(row_data)

                        val_df = pd.DataFrame(val_rows)
                        st.download_button(
                            "Download validation report (CSV)",
                            data=to_csv_bytes(val_df),
                            file_name="validation_report.csv",
                            mime="text/csv",
                            use_container_width=True,
                        )
                    else:
                        st.success("All products passed validation with high confidence. No issues found.")


# ============================================================
# TAB: OUTPUT (combined 5-column enrichment file)
# ============================================================

with tab_output:
    st.markdown(
        "Combined enrichment output for the feed optimisation tool. "
        "Five columns: **id**, **title**, **scraper_output**, **search_context**, **ai_brief**."
    )

    st.markdown('<div class="gradient-bar"></div>', unsafe_allow_html=True)

    has_search = "search_contexts" in st.session_state
    has_scraper = "scraped" in st.session_state
    has_briefs = "ai_briefs" in st.session_state

    # Status indicators
    st1, st2, st3 = st.columns(3)
    with st1:
        if has_search:
            coverage = st.session_state["coverage"]
            st.success(f"Search: {coverage['skus_with_search_data']:,} SKUs")
        else:
            st.info("Search intelligence: not run")
    with st2:
        if has_scraper:
            scraped = st.session_state["scraped"]
            ok = (scraped["scrape_status"] == "ok").sum()
            st.success(f"Scraper: {ok:,} products")
        else:
            st.info("Page scraper: not run")
    with st3:
        if has_briefs:
            brief_count = st.session_state.get("ai_briefs_count", len(st.session_state["ai_briefs"]))
            st.success(f"AI briefs: {brief_count:,} products")
        else:
            st.info("AI enrichment: not run")

    if not has_search and not has_scraper and not has_briefs:
        st.markdown("")
        st.markdown(
            "Run at least one enrichment method (Search intelligence, Page scraper, or AI enrichment) "
            "to generate the output file."
        )
    else:
        # Build the 5-column output
        output = feed[[id_col, title_col]].copy()
        output.columns = ["id", "title"]
        output["id"] = output["id"].astype(str)

        # Scraper output column
        if has_scraper:
            scraped = st.session_state["scraped"]
            scraper_map = scraped.set_index("sku_id")["scraper_output"].to_dict()
            output["scraper_output"] = output["id"].map(scraper_map).fillna("")
        else:
            output["scraper_output"] = ""

        # Search context column
        if has_search:
            search_contexts = st.session_state["search_contexts"]
            output["search_context"] = output["id"].map(search_contexts).fillna("")
        else:
            output["search_context"] = ""

        # AI brief column
        if has_briefs:
            ai_briefs = st.session_state["ai_briefs"]
            output["ai_brief"] = output["id"].map(ai_briefs).fillna("")
        else:
            output["ai_brief"] = ""

        # Stats
        st.markdown("")
        st.markdown('<p class="overline">Output summary</p>', unsafe_allow_html=True)

        total = len(output)
        has_scraper_data = (output["scraper_output"].str.len() > 0).sum()
        has_search_data = (output["search_context"].str.len() > 50).sum()
        has_brief_data = (output["ai_brief"].str.len() > 0).sum()
        has_all = (
            (output["scraper_output"].str.len() > 0)
            & (output["search_context"].str.len() > 50)
            & (output["ai_brief"].str.len() > 0)
        ).sum()

        o1, o2, o3, o4, o5 = st.columns(5)
        o1.metric("Total products", f"{total:,}")
        o2.metric("With scraper", f"{has_scraper_data:,}")
        o3.metric("With search", f"{has_search_data:,}")
        o4.metric("With AI brief", f"{has_brief_data:,}")
        o5.metric("All three", f"{has_all:,}")

        # Preview
        st.markdown("")
        st.markdown('<p class="overline">Preview</p>', unsafe_allow_html=True)

        # Show rows with any data
        preview = output[
            (output["scraper_output"].str.len() > 0)
            | (output["search_context"].str.len() > 50)
            | (output["ai_brief"].str.len() > 0)
        ]
        if len(preview) == 0:
            preview = output

        preview_display = preview.head(20).copy()
        preview_display["scraper_output"] = preview_display["scraper_output"].str[:100] + "..."
        preview_display["search_context"] = preview_display["search_context"].str[:100] + "..."
        preview_display["ai_brief"] = preview_display["ai_brief"].str[:100] + "..."
        st.dataframe(preview_display, use_container_width=True, height=400)

        # Expand a single product to see full output
        st.markdown("")
        st.markdown('<p class="overline">Full product preview</p>', unsafe_allow_html=True)

        product_options = preview["title"].tolist()[:500]
        if product_options:
            selected = st.selectbox(
                "Select a product",
                options=[""] + product_options,
                format_func=lambda x: x[:80] if x else "Select a product...",
                key="output_product_select",
            )
            if selected:
                row = output[output["title"] == selected].iloc[0]
                if row["scraper_output"]:
                    st.markdown("**Scraper output:**")
                    st.code(row["scraper_output"], language=None)
                else:
                    st.caption("No scraper data for this product.")

                if len(row["search_context"]) > 50:
                    st.markdown("**Search context:**")
                    st.code(row["search_context"], language=None)
                else:
                    st.caption("No search context for this product.")

                if row["ai_brief"]:
                    st.markdown("**AI brief:**")
                    st.markdown(row["ai_brief"])
                else:
                    st.caption("No AI brief for this product.")

        # Download
        st.markdown("---")
        st.markdown('<p class="overline">Download</p>', unsafe_allow_html=True)

        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "Download enrichment file (CSV)",
                data=to_csv_bytes(output),
                file_name=f"{feed_file.name.rsplit('.', 1)[0]}_enrichment.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with dl2:
            try:
                st.download_button(
                    "Download enrichment file (XLSX)",
                    data=to_xlsx_bytes(output),
                    file_name=f"{feed_file.name.rsplit('.', 1)[0]}_enrichment.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            except Exception:
                st.caption("XLSX export requires openpyxl")


# ============================================================
# TAB: EXPLORE MATCHES
# ============================================================

with tab_explore:
    if "matched" not in st.session_state:
        st.info("Run search intelligence first to explore matches.")
    else:
        matched = st.session_state["matched"]

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

        keyword_themes = st.session_state.get("keyword_themes", {})
        search_contexts = st.session_state.get("search_contexts", {})

        product_options = [
            str(row[title_col])
            for _, row in feed.iterrows()
            if keyword_themes.get(str(row[id_col]), "")
        ][:500]

        if product_options:
            selected = st.selectbox(
                "Search for a product",
                options=[""] + product_options,
                format_func=lambda x: x[:80] if x else "Select a product...",
                key="explore_product_select",
            )
            if selected:
                sku_row = feed[feed[title_col] == selected].iloc[0]
                sku_id = str(sku_row[id_col])

                kw = keyword_themes.get(sku_id, "")
                if kw:
                    st.markdown(f"**Keyword themes:** {kw}")

                ctx = search_contexts.get(sku_id, "")
                if ctx:
                    st.code(ctx, language=None)

                sku_matches = matched[matched["sku_id"] == sku_id].sort_values("conv_value", ascending=False)
                if len(sku_matches) > 0:
                    st.markdown(f"**Matched n-grams** ({len(sku_matches)})")
                    display_cols = [
                        c for c in ["search_term", "relevance_score", "impressions", "clicks", "conversions", "conv_value", "specificity"]
                        if c in sku_matches.columns
                    ]
                    st.dataframe(sku_matches[display_cols], use_container_width=True, height=300)
