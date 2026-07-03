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

EMPTY_ISSUE = {
    "status": "draft",
    "updated_at": None,
    "movies": {},  # movie_id (str) -> {"section": key or None, "comment": str}
    "content": None  # editorial text, seeded by default_content() on load
}


def default_content() -> dict:
    """Editorial defaults for a fresh issue, seeded from the builder config."""
    try:
        with open("builder/text_content.json", "r", encoding="utf-8") as f:
            text = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        text = {}
    return {
        "kicker": "Cette semaine au cinéma",
        "title": text.get("newsletter_title", "Paris Ciné"),
        "intro": text.get("global_intro", ""),
        "conclusion": text.get("global_conclusion", ""),
        "footer": "Le programme de la semaine dans les salles parisiennes, choisi à la main.",
        "interludes": {}  # section key -> short editorial passage after the section
    }


def _clean_content(content: dict) -> dict:
    """Normalize a client-provided content payload onto the known fields."""
    base = default_content()
    content = content or {}
    for field in ("kicker", "title", "intro", "conclusion", "footer"):
        if field in content:
            base[field] = str(content[field] or "").strip()
    base["interludes"] = {
        str(k): str(v or "").strip()
        for k, v in (content.get("interludes") or {}).items()
        if str(v or "").strip()
    }
    return base


def _slugify(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_title.lower()).strip("_")
    return slug or "section"


def load_sections() -> dict:
    """Load the section library. Sections are always created by the editor —
    there are no defaults; a fresh setup starts with none."""
    if not os.path.exists(SECTIONS_FILE):
        return {}
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
        "description": description.strip()
    }
    save_sections(sections)
    return {"key": key, **sections[key]}


def reorder_sections(keys: list) -> dict:
    """Persist a new section order; sections not listed keep their place after."""
    sections = load_sections()
    unknown = [k for k in keys if k not in sections]
    if unknown:
        raise ValueError(f"Unknown sections: {', '.join(unknown)}")
    order = 1
    for k in keys:
        sections[k]["order"] = order
        order += 1
    for k, s in sorted(sections.items(), key=lambda kv: kv[1]["order"]):
        if k not in keys:
            s["order"] = order
            order += 1
    save_sections(sections)
    return sections


def update_section(key: str, title: str = None, description: str = None) -> dict:
    """Rename a section or change its description."""
    sections = load_sections()
    if key not in sections:
        raise ValueError(f"Unknown section: {key}")
    if title is not None and title.strip():
        sections[key]["title"] = title.strip()
    if description is not None:
        sections[key]["description"] = description.strip()
    save_sections(sections)
    return {"key": key, **sections[key]}


def delete_section(key: str):
    """Remove a section from the library."""
    sections = load_sections()
    if key not in sections:
        raise ValueError(f"Unknown section: {key}")
    del sections[key]
    save_sections(sections)


def load_issue() -> dict:
    if not os.path.exists(ISSUE_FILE):
        issue = json.loads(json.dumps(EMPTY_ISSUE))
        issue["content"] = default_content()
        return issue
    with open(ISSUE_FILE, "r", encoding="utf-8") as f:
        issue = json.load(f)
    if not issue.get("content"):
        issue["content"] = default_content()
    return issue


def save_issue(movies: dict, content: dict = None, status: str = "draft") -> dict:
    """Persist the issue draft. Any edit puts it back into draft status."""
    if content is None:
        content = load_issue().get("content")
    issue = {
        "status": status,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "content": _clean_content(content),
        "movies": {
            str(mid): {
                "section": entry.get("section") or None,
                "comment": (entry.get("comment") or "").strip(),
                "order": entry.get("order") if isinstance(entry.get("order"), int) else None
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
