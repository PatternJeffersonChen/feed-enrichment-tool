# Feed Enrichment Tool

Enrich Google Merchant Centre product feeds with Google Ads search term intelligence. Built for Pattern's feed optimisation team.

## What it does

- Uploads a GMC feed export and a Supermetrics search terms export
- Extracts n-grams (unigrams, bigrams, trigrams) from the search term corpus
- Matches n-grams to products using an inverted index with specificity filtering
- Outputs an enriched feed with `search_context` and `keyword_themes` columns
- The search context block is designed to slot into description generation prompts

## Quick start

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## CLI alternative

```bash
python run_enrichment.py feed.tsv search_terms.xlsx
python run_scraper.py feed.tsv --max 5
```

## Access

Hosted on Streamlit Community Cloud with viewer authentication restricted to `@pattern.com` emails.
