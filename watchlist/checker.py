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


# source -> (brand-colored dot, short label, whether to show "/max")
RATING_STYLE = {
    "Letterboxd": ("🟢", "LB", True),
    "IMDB": ("🟡", "IMDB", False),
    "Allociné (Presse)": ("🔴", "AC", True),
}
_RATING_ORDER = ["Letterboxd", "IMDB", "Allociné (Presse)"]


def _format_ratings(movie: Movie) -> str:
    by_source = {r.source: r for r in movie.ratings}
    picks = []
    for source in _RATING_ORDER:
        r = by_source.get(source)
        if not r or r.score is None:
            continue
        dot, label, show_max = RATING_STYLE[source]
        text = f"{label} {r.score:.1f}/{r.max_score:.0f}" if show_max else f"{label} {r.score:.1f}"
        if r.url:
            text = f'<a href="{_html_escape(r.url, quote=True)}">{text}</a>'
        picks.append(f"{dot} {text}")
    return " · ".join(picks)


def _day_label(d) -> str:
    return f"{FRENCH_DAYS[d.weekday()]} {d.day} {FRENCH_MONTHS[d.month - 1]}"


def _day_range_label(days: list) -> str:
    """1 day -> 'jeu 23 jul'; 2 -> 'jeu 23 jul et ven 24 jul'; 3+ -> 'du .. au ..'."""
    if len(days) == 1:
        return _day_label(days[0])
    if len(days) == 2:
        return f"{_day_label(days[0])} et {_day_label(days[1])}"
    return f"du {_day_label(days[0])} au {_day_label(days[-1])}"


def _times_for_day(showtimes: list) -> tuple[str, ...]:
    """Ordered ('HH:MM VO', ...) for one day — used as both label and grouping key."""
    times = []
    for s in sorted(showtimes, key=lambda x: x.datetime):
        t = datetime.fromisoformat(s.datetime).strftime("%H:%M")
        if s.version:
            t += f" {s.version}"
        times.append(t)
    return tuple(times)


def _format_showtimes(movie: Movie) -> str:
    by_cinema: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    for st in movie.showtimes:
        try:
            day = datetime.fromisoformat(st.datetime).date()
        except ValueError:
            continue
        by_cinema[st.cinema_name][day].append(st)

    lines = []
    cinema_items = sorted(by_cinema.items())
    shown = cinema_items[:MAX_CINEMAS_PER_MOVIE]
    remaining = len(cinema_items) - len(shown)

    for cinema_name, days in shown:
        lines.append(f"  <b>{_esc(cinema_name)}</b>")
        sigs = {day: _times_for_day(sts) for day, sts in days.items()}

        # Merge calendar-consecutive days that share the exact same showtimes.
        run_days: list = []
        run_sig: tuple | None = None
        for day in sorted(sigs):
            sig = sigs[day]
            if run_days and sig == run_sig and (day - run_days[-1]).days == 1:
                run_days.append(day)
            else:
                if run_days:
                    lines.append(f"    {_day_range_label(run_days)} — {', '.join(run_sig)}")
                run_days, run_sig = [day], sig
        if run_days:
            lines.append(f"    {_day_range_label(run_days)} — {', '.join(run_sig)}")

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
