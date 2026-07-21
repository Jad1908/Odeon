"""
Letterboxd Watchlist -> Paris Cinema Notification Bot.

Usage:
    python -m watchlist bot                 Run the bot: serve commands + weekly push (main entry)
    python -m watchlist notify              Fire the weekly push once, now (manual test)
    python -m watchlist check <username>    Check a user and print results (no Telegram)

`bot` is the long-lived process you deploy. It serves interactive commands and
runs the weekly notification itself on a background thread, so no external cron
is needed.
"""

import argparse
import os
import sys
from pathlib import Path


def _load_dotenv():
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main():
    _load_dotenv()
    parser = argparse.ArgumentParser(
        description="Check Letterboxd watchlists against Paris cinema screenings.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("bot", help="Run the bot: serve commands + weekly push (main entry)")

    sub.add_parser("notify", help="Fire the weekly push once, now (manual test)")

    p_check = sub.add_parser("check", help="Check a user and print results (no Telegram)")
    p_check.add_argument("username", help="Letterboxd username")

    args = parser.parse_args()

    if args.command == "notify":
        from .bot import notify
        notify()

    elif args.command == "check":
        from .checker import check_usernames
        movies, errors = check_usernames([args.username])
        for err in errors:
            print(f"Warning: {err}", file=sys.stderr)
        if movies:
            print(f"\n{len(movies)} match(es) found:\n")
            for m in movies:
                showtimes_count = len(m.showtimes)
                print(f"  {m.title} ({m.year or '?'}) — {m.director or 'Unknown'} — {showtimes_count} showtimes")
        else:
            print("No matches found.")

    elif args.command == "bot":
        from .bot import poll
        poll()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
