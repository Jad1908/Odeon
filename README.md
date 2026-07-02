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
3. Curate        viewer.py (Flask UI)     → data/issue.json
        │
        ▼
4. Render        builder/build.js (EJS)   → builder/output/newsletter_output_v2.html
```

The Flask UI drives the whole workflow for an issue: fetch the week's movies
(cached per cinema week, Wed–Tue), select which ones make the cut, organize
them into sections (six defaults, plus your own saved custom sections), write
a comment for each, prerender the exact newsletter HTML through the Node
builder, and validate it (completeness, broken images, stale showtimes,
render integrity) before the issue is marked ready.

## Repository layout

| Path | Purpose |
|---|---|
| `pipeline/` | Python package: scraper, categorization logic, background runner |
| `viewer.py` | Flask web UI to browse categories, curate the selection, and trigger pipeline runs |
| `builder/` | Node/EJS renderer producing the final newsletter HTML (`assets/` logos, `output/` results) |
| `data/` | Generated pipeline outputs (committed as sample data from a February 2026 run) |
| `reference/` | Saved paris-cine.info pages used to reverse-engineer the API |

## Running it

Python steps use [uv](https://docs.astral.sh/uv/) and run from the repo root:

```bash
uv sync
cd builder && npm install && cd ..

# The whole workflow runs from the web UI (http://localhost:5000)
uv run python viewer.py
```

The scrape and render steps can also be run standalone:

```bash
uv run python -m pipeline.scraper --showtimes -o data/week_full.json
uv run python -m pipeline.analysis
cd builder && node build.js
```

Status: proof of concept. Sending (e.g. via Mailjet) is manual — the builder
output is pasted into the email tool by hand.
