# Feed Enrichment Tool - Local Setup Guide

## Prerequisites

You need Python 3 installed on your computer.

**Check if Python is installed:** Open Terminal (Mac) or Command Prompt (Windows) and type:
```
python3 --version
```

If you see a version number (e.g., `Python 3.12.x`), you're good. If not:

- **Mac:** `brew install python3` (if you have Homebrew) or download from https://www.python.org/downloads/
- **Windows:** Download from https://www.python.org/downloads/ - IMPORTANT: tick "Add Python to PATH" during install


## First-Time Setup (do this once)

### Step 1: Open Terminal

- **Mac:** Search "Terminal" in Spotlight (Cmd+Space, type Terminal)
- **Windows:** Search "Command Prompt" in Start menu

### Step 2: Navigate to the project folder

Type `cd ` (with a space after), then drag the "Feed Optimisation Project" folder from Finder/Explorer into the Terminal window. It will paste the path automatically. Press Enter.

It should look something like:
```bash
cd "/Users/yourname/Documents/Feed Optimisation Project"
```

**Important:** Always wrap the path in double quotes because the folder name has spaces. Don't use backslash escaping like `Feed\ Optimisation\ Project` - quotes are simpler and less error-prone.

### Step 3: Create a virtual environment

**Mac:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
```

You'll see `(.venv)` appear at the start of your terminal prompt. This means the virtual environment is active.

### Step 4: Install dependencies

```bash
pip install -r requirements.txt
```

Done! You only need to do Steps 1-4 once.


## Running the Streamlit App

Every time you want to use the tool:

```bash
# 1. Open Terminal and navigate to the folder
cd "/Users/yourname/Documents/Feed Optimisation Project"

# 2. Activate the virtual environment
source .venv/bin/activate          # Mac
# .venv\Scripts\activate           # Windows

# 3. Run the app
streamlit run streamlit_app.py
```

A browser window will open automatically with the app. Upload your files and click Enrich.


## Running via Command Line (alternative)

If you prefer the terminal over the Streamlit UI:

```bash
# Make sure .venv is activated first, then:

# Enrich a feed with search terms
python run_enrichment.py your_feed.tsv your_search_terms.xlsx

# Scrape product pages (test with 5 first)
python run_scraper.py your_feed.tsv --max 5
```


## Troubleshooting

**"externally-managed-environment" error**
You're not in the virtual environment. Run `source .venv/bin/activate` (Mac) or `.venv\Scripts\activate` (Windows) first.

**"python3 is not recognized" (Windows)**
Try `python` instead of `python3`

**"No module named streamlit" or "command not found: streamlit"**
Make sure the virtual environment is active (you should see `(.venv)` in your prompt), then run `pip install -r requirements.txt`

**"Feed column not found"**
The script expects standard GMC column names (id, title, product type). If your feed uses different names, adjust the column mapping in the Streamlit sidebar.

**The browser doesn't open automatically**
Copy the URL from the Terminal (usually `http://localhost:8501`) and paste it into your browser.
