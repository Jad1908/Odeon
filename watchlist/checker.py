"""Match a Letterboxd watchlist against current Paris cinema screenings."""

import unicodedata
import re
from collections import defaultdict
from datetime import datetime
from html import escape as _html_escape

from pipeline.scraper import (
    fetch_movies_from_api,
    parse_movie_data,
    fetch_showtimes_for_movie,
    Movie,
)
from .letterboxd import WatchlistEntry, fetch_watchlist


FRENCH_DAYS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
FRENCH_MONTHS = [
    "jan", "fev", "mar", "avr", "mai", "jun",
    "jul", "aou", "sep", "oct", "nov", "dec",
]
MAX_CINEMAS_PER_MOVIE = 6


def check_usernames(usernames: list[str]) -> tuple[list[Movie], list[str]]:
    """Run the full pipeline for one or more Letterboxd usernames.

    Returns (matched_movies, errors).
    """
    all_slugs: dict[str, WatchlistEntry] = {}
    all_titles: dict[str, WatchlistEntry] = {}
    errors: list[str] = []

    for username in usernames:
        try:
            entries = fetch_watchlist(username)
        except Exception as exc:
            errors.append(f"Could not fetch watchlist for '{username}': {exc}")
            continue
        if not entries:
            errors.append(
                f"Watchlist for '{username}' is empty or private."
            )
            continue
        for e in entries:
            all_slugs[e.slug] = e
            all_titles[_normalize(e.title)] = e

    if not all_slugs and not all_titles:
        return [], errors

    raw_movies = fetch_movies_from_api()
    matched: list[Movie] = []

    for raw in raw_movies:
        lb_slug = raw.get("lb_u", "")
        if lb_slug and lb_slug in all_slugs:
            movie = _parse_with_showtimes(raw)
            matched.append(movie)
            continue

        original = raw.get("o_ti") or ""
        title = raw.get("ti") or ""
        if (_normalize(original) in all_titles and original) or (
            _normalize(title) in all_titles and title
        ):
            movie = _parse_with_showtimes(raw)
            matched.append(movie)

    matched.sort(key=lambda m: m.copies_count, reverse=True)
    return matched, errors


def format_telegram_message(
    movies: list[Movie],
    errors: list[str],
    usernames: list[str],
) -> str:
    """Build an HTML-formatted Telegram message."""
    if errors and not movies:
        return "\n".join(errors)

    if not movies:
        who = ", ".join(usernames)
        return f"No movies from the watchlist ({who}) are screening in Paris this week."

    count = len(movies)
    header = (
        f"<b>{count} film{'s' if count > 1 else ''} from your watchlist"
        f" {'are' if count > 1 else 'is'} screening in Paris this week!</b>"
    )

    sections = [header]
    for movie in movies:
        sections.append(_format_movie(movie))

    return "\n\n".join(sections)


def _parse_with_showtimes(raw: dict) -> Movie:
    movie = parse_movie_data(raw)
    movie.showtimes = fetch_showtimes_for_movie(
        movie_id=movie.id,
        movie_language=movie.language or "",
    )
    return movie


def _format_movie(movie: Movie) -> str:
    title = _esc(movie.title)
    year = f" ({movie.year})" if movie.year else ""
    parts = [f"<b>{title}</b>{year}"]

    meta = []
    if movie.director:
        meta.append(_esc(movie.director))
    if movie.duration_minutes:
        h, m = divmod(movie.duration_minutes, 60)
        meta.append(f"{h}h{m:02d}" if h else f"{m}min")
    if meta:
        parts.append(" · ".join(meta))

    ratings = _format_ratings(movie)
    if ratings:
        parts.append(ratings)

    if movie.showtimes:
        parts.append(_format_showtimes(movie))
    else:
        parts.append(f"{movie.copies_count} screenings (showtimes unavailable)")

    return "\n".join(parts)


def _format_ratings(movie: Movie) -> str:
    picks = []
    for r in movie.ratings:
        if r.source == "Letterboxd":
            picks.append(f"LB {r.score:.1f}/{r.max_score:.0f}")
        elif r.source == "IMDB":
            picks.append(f"IMDB {r.score:.1f}")
        elif r.source == "Allociné (Presse)":
            picks.append(f"AC {r.score:.1f}/{r.max_score:.0f}")
    return " · ".join(picks)


def _format_showtimes(movie: Movie) -> str:
    by_cinema: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for st in movie.showtimes:
        try:
            dt = datetime.fromisoformat(st.datetime)
        except ValueError:
            continue
        day_key = dt.strftime("%Y-%m-%d")
        by_cinema[st.cinema_name][day_key].append(st)

    lines = []
    cinema_items = sorted(by_cinema.items())
    shown = cinema_items[:MAX_CINEMAS_PER_MOVIE]
    remaining = len(cinema_items) - len(shown)

    for cinema_name, days in shown:
        lines.append(f"  <b>{_esc(cinema_name)}</b>")
        for day_str in sorted(days):
            sts = days[day_str]
            dt = datetime.fromisoformat(sts[0].datetime)
            day_label = (
                f"{FRENCH_DAYS[dt.weekday()]} {dt.day} {FRENCH_MONTHS[dt.month - 1]}"
            )
            times = []
            for s in sorted(sts, key=lambda x: x.datetime):
                t = datetime.fromisoformat(s.datetime).strftime("%H:%M")
                if s.version:
                    t += f" {s.version}"
                times.append(t)
            lines.append(f"    {day_label} — {', '.join(times)}")

    if remaining > 0:
        lines.append(f"  <i>... and {remaining} more cinemas</i>")

    return "\n".join(lines)


def _esc(text: str) -> str:
    return _html_escape(text, quote=False)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9 ]", "", text)
    return text.strip()
