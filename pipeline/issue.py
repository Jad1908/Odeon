"""
Issue drafts and section configuration for the newsletter workflow.

An "issue" is one edition of the newsletter being put together: which movies
are in, which section each goes to, and the editor's comment for each.
Sections live in their own file so custom ones added for an issue stay
available for future issues.
"""
import json
import os
import re
import unicodedata
from datetime import datetime

ISSUE_FILE = "data/issue.json"
SECTIONS_FILE = "data/sections.json"

DEFAULT_SECTIONS = {
    "letterboxd_picks": {
        "order": 1,
        "title": "Letterboxd les adore",
        "description": "Il n'y a que l'avis de Letterboxd qui compte.",
        "default": True
    },
    "top_new_releases": {
        "order": 2,
        "title": "Nouveautes",
        "description": "Les films sortis cette semaine.",
        "default": True
    },
    "current_landscape": {
        "order": 3,
        "title": "Toujours au cine",
        "description": "Toujours temps de les voir.",
        "default": True
    },
    "premieres_events": {
        "order": 4,
        "title": "Avant-premieres",
        "description": "Prenez de l'avance pour montrer que vous êtes un vrai cinéphile.",
        "default": True
    },
    "old_classics": {
        "order": 5,
        "title": "Classiques",
        "description": "Voyage dans le temps.",
        "default": True
    },
    "niche_gems": {
        "order": 6,
        "title": "Pour les vrais cinephiles",
        "description": "Si t'es vraiment un prouveur....",
        "default": True
    }
}

EMPTY_ISSUE = {
    "status": "draft",
    "updated_at": None,
    "movies": {}  # movie_id (str) -> {"section": key or None, "comment": str}
}


def _slugify(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_title.lower()).strip("_")
    return slug or "section"


def load_sections() -> dict:
    """Load section config, seeding the file with the defaults on first use."""
    if not os.path.exists(SECTIONS_FILE):
        save_sections(DEFAULT_SECTIONS)
        return dict(DEFAULT_SECTIONS)
    with open(SECTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_sections(sections: dict):
    os.makedirs(os.path.dirname(SECTIONS_FILE), exist_ok=True)
    with open(SECTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(sections, f, indent=2, ensure_ascii=False)


def add_section(title: str, description: str = "") -> dict:
    """Add a custom section; it is saved and reusable in future issues."""
    title = title.strip()
    if not title:
        raise ValueError("Section title cannot be empty")

    sections = load_sections()
    key = _slugify(title)
    if key in sections:
        raise ValueError(f"A section named '{title}' already exists")

    sections[key] = {
        "order": max((s["order"] for s in sections.values()), default=0) + 1,
        "title": title,
        "description": description.strip(),
        "default": False
    }
    save_sections(sections)
    return {"key": key, **sections[key]}


def delete_section(key: str):
    """Remove a custom section (defaults cannot be removed)."""
    sections = load_sections()
    if key not in sections:
        raise ValueError(f"Unknown section: {key}")
    if sections[key].get("default"):
        raise ValueError("Default sections cannot be deleted")
    del sections[key]
    save_sections(sections)


def load_issue() -> dict:
    if not os.path.exists(ISSUE_FILE):
        return json.loads(json.dumps(EMPTY_ISSUE))
    with open(ISSUE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_issue(movies: dict, status: str = "draft") -> dict:
    """Persist the issue draft. Any edit puts it back into draft status."""
    issue = {
        "status": status,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "movies": {
            str(mid): {
                "section": entry.get("section") or None,
                "comment": (entry.get("comment") or "").strip()
            }
            for mid, entry in movies.items()
        }
    }
    os.makedirs(os.path.dirname(ISSUE_FILE), exist_ok=True)
    with open(ISSUE_FILE, "w", encoding="utf-8") as f:
        json.dump(issue, f, indent=2, ensure_ascii=False)
    return issue


def set_issue_status(status: str) -> dict:
    issue = load_issue()
    issue["status"] = status
    issue["updated_at"] = datetime.now().isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(ISSUE_FILE), exist_ok=True)
    with open(ISSUE_FILE, "w", encoding="utf-8") as f:
        json.dump(issue, f, indent=2, ensure_ascii=False)
    return issue
