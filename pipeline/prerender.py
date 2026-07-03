"""
Prerender the current issue through the Node/EJS builder.

The issue draft is exported to builder inputs (movies grouped by assigned
section, with the editor's comment attached), then build.js renders the exact
HTML that would be sent. Movies not yet assigned to a section are rendered
under a trailing "Non classés" section so drafts can still be previewed.
"""
import json
import os
import subprocess

from . import analysis
from . import issue as issue_store

BUILDER_DIR = "builder"
PRERENDER_DIR = os.path.join(BUILDER_DIR, ".prerender")
PREVIEW_FILE = os.path.join(BUILDER_DIR, "output", "preview.html")
WEEK_FILE = "data/week_full.json"
BASE_TEXT_FILE = os.path.join(BUILDER_DIR, "text_content.json")

UNASSIGNED_KEY = "unassigned"


def load_movie_lookup() -> dict:
    """All scraped movies indexed by id, with the calculated score attached."""
    with open(WEEK_FILE, "r", encoding="utf-8") as f:
        movies = json.load(f)
    for m in movies:
        m["calculated_score"] = analysis.get_normalized_score(m)
    return {str(m["id"]): m for m in movies}


def export_issue_inputs() -> dict:
    """Write builder input files for the current issue; report unresolvable ids."""
    current = issue_store.load_issue()
    sections = issue_store.load_sections()
    lookup = load_movie_lookup()

    grouped = {}
    missing = []
    for idx, (movie_id, entry) in enumerate(current["movies"].items()):
        movie = lookup.get(str(movie_id))
        if movie is None:
            missing.append(str(movie_id))
            continue
        movie = dict(movie)
        section = entry.get("section") or UNASSIGNED_KEY
        movie["source_tab"] = section
        movie["comment"] = entry.get("comment") or ""
        order = entry.get("order")
        movie["_sort"] = (order if isinstance(order, int) else 10**9, idx)
        grouped.setdefault(section, []).append(movie)

    # The editor's manual order within each section wins over automatic sorting
    for movies_list in grouped.values():
        movies_list.sort(key=lambda mv: mv.pop("_sort"))
        for i, mv in enumerate(movies_list):
            mv["issue_order"] = i

    with open(BASE_TEXT_FILE, "r", encoding="utf-8") as f:
        text_data = json.load(f)

    # Per-issue editorial content overrides the static builder config
    content = current.get("content") or issue_store.default_content()
    interludes = content.get("interludes") or {}
    text_data["newsletter_title"] = content.get("title") or text_data.get("newsletter_title", "")
    text_data["kicker"] = content.get("kicker", "")
    text_data["global_intro"] = content.get("intro", "")
    text_data["global_conclusion"] = content.get("conclusion", "")
    text_data["footer_note"] = content.get("footer", "")

    text_sections = {
        key: {"order": s["order"], "title": s["title"],
              "description": s.get("description", ""),
              "interlude": interludes.get(key, "")}
        for key, s in sections.items()
    }
    max_order = max((s["order"] for s in text_sections.values()), default=0)
    text_sections[UNASSIGNED_KEY] = {
        "order": max_order + 1,
        "title": "Non classés (brouillon)",
        "description": "Films sélectionnés mais pas encore rangés dans une section."
    }
    text_data["sections"] = text_sections

    os.makedirs(PRERENDER_DIR, exist_ok=True)
    with open(os.path.join(PRERENDER_DIR, "movies.json"), "w", encoding="utf-8") as f:
        json.dump(grouped, f, ensure_ascii=False)
    with open(os.path.join(PRERENDER_DIR, "text_content.json"), "w", encoding="utf-8") as f:
        json.dump(text_data, f, ensure_ascii=False)

    return {
        "movie_count": sum(len(v) for v in grouped.values()),
        "sections_used": sorted(grouped.keys()),
        "missing_ids": missing
    }


def run_prerender() -> dict:
    """Export the issue and render it with the Node builder."""
    current = issue_store.load_issue()
    if not current["movies"]:
        return {"ok": False, "log": "No movies selected yet — nothing to render.", "export": None}

    export = export_issue_inputs()
    os.makedirs(os.path.join(BUILDER_DIR, "output"), exist_ok=True)

    try:
        result = subprocess.run(
            ["node", "build.js",
             "--movies", os.path.join(".prerender", "movies.json"),
             "--text", os.path.join(".prerender", "text_content.json"),
             "--out", os.path.join("output", "preview.html")],
            cwd=BUILDER_DIR, capture_output=True, text=True, timeout=60
        )
    except FileNotFoundError:
        return {"ok": False, "log": "node not found — install Node.js to prerender.", "export": export}
    except subprocess.TimeoutExpired:
        return {"ok": False, "log": "Builder timed out after 60s.", "export": export}

    log = (result.stdout + result.stderr).strip()
    ok = result.returncode == 0 and os.path.exists(PREVIEW_FILE)
    return {"ok": ok, "log": log, "export": export}
