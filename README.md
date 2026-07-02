# Paris Ciné Newsletter

A small pipeline that turns the weekly Paris cinema program into a curated
HTML newsletter.

Every week, hundreds of movies play across ~80 Paris theaters. This project
scrapes the full lineup (with showtimes and ratings from IMDB, SensCritique,
Allociné, Letterboxd, Metacritic and Rotten Tomatoes), sorts it into
newsletter-friendly sections — new releases, current landscape, premieres,
old classics, Letterboxd picks, niche gems — lets you hand-pick the final
selection in a web UI, and renders it as an email-ready HTML newsletter.

## How it works

```
paris-cine.info API
        │
        ▼
1. Scrape        pipeline/scraper.py      → data/week_full.json
        │
        ▼
2. Categorize    pipeline/analysis.py     → data/newsletter_data.json
        │
        ▼
3. Curate        viewer.py (Flask UI)     → data/newsletter_selection.json
        │
        ▼
4. Render        builder/build.js (EJS)   → builder/output/newsletter_output_v2.html
```

## Repository layout

| Path | Purpose |
|---|---|
| `pipeline/` | Python package: scraper, categorization logic, background runner |
| `viewer.py` | Flask web UI to browse categories, curate the selection, and trigger pipeline runs |
| `builder/` | Node/EJS renderer producing the final newsletter HTML (`assets/` logos, `output/` results) |
| `data/` | Generated pipeline outputs (committed as sample data from a February 2026 run) |
| `reference/` | Saved paris-cine.info pages used to reverse-engineer the API |

## Running it

Python steps run from the repo root:

```bash
pip install -r requirements.txt

# 1+2. Scrape and categorize (or drive both from the web UI)
python -m pipeline.scraper --showtimes -o data/week_full.json
python -m pipeline.analysis

# 3. Curate in the browser (http://localhost:5000)
python viewer.py

# 4. Render the newsletter
cd builder && npm install && node build.js
```

Status: proof of concept. Sending (e.g. via Mailjet) is manual — the builder
output is pasted into the email tool by hand.
