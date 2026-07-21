"""Telegram bot: handle subscriptions, interactive commands, and the weekly push.

Runs as a single long-lived process (``python -m watchlist bot``):

* a long-polling loop serves interactive commands (/check, /watch, ...);
* a background thread fires the weekly notification on its own, so no
  external cron is needed.

Subscriber state lives in a single JSON file. Its location defaults to
``watchlist/subscribers.json`` but can be pointed anywhere (e.g. a persistent
volume) via the ``SUBSCRIBERS_FILE`` environment variable.
"""

import json
import os
import threading
import time
from datetime import datetime
from html import escape as _html_escape
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

PARIS = ZoneInfo("Europe/Paris")

# Weekly push: Wednesday (weekday 2) at 10:00 Paris time — start of the cinema week.
NOTIFY_WEEKDAY = 2
NOTIFY_HOUR = 10


def _subscribers_file() -> Path:
    override = os.environ.get("SUBSCRIBERS_FILE")
    if override:
        return Path(override)
    return Path(__file__).parent / "subscribers.json"


def _state_file() -> Path:
    return _subscribers_file().parent / "bot_state.json"


def _load_subscribers() -> list[dict]:
    """Each subscriber: {"chat_id": str, "username": str, "name": str, "auto": bool}"""
    path = _subscribers_file()
    if path.exists():
        return json.loads(path.read_text())
    return []


def _save_subscribers(subscribers: list[dict]):
    path = _subscribers_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(subscribers, indent=2))


def _find_subscriber(chat_id: str) -> dict | None:
    for sub in _load_subscribers():
        if sub["chat_id"] == chat_id:
            return sub
    return None


def _load_state() -> dict:
    path = _state_file()
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _save_state(state: dict):
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def get_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _require_token() -> str:
    token = get_token()
    if not token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN environment variable.")
    return token


TELEGRAM_LIMIT = 4096
MAX_POSTERS = 10  # Telegram albums hold at most 10 photos


def _post_message(token, chat_id, text, parse_mode="HTML", reply_markup=None):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return requests.post(url, json=payload, timeout=15)


def send_message(token: str, chat_id: str, text: str, reply_markup: dict | None = None) -> dict:
    """Send one message. If the HTML fails to parse, retry as plain text so the
    user still gets the content instead of an error."""
    resp = _post_message(token, chat_id, text, parse_mode="HTML", reply_markup=reply_markup)
    if resp.status_code == 400:
        print(f"HTML send rejected ({resp.text.strip()}); retrying as plain text.")
        resp = _post_message(token, chat_id, text, parse_mode=None, reply_markup=reply_markup)
    resp.raise_for_status()
    return resp.json()


def send_long_message(token: str, chat_id: str, text: str):
    """Send a possibly-long message, splitting on blank-line (section) boundaries
    so each chunk stays under Telegram's limit AND keeps its HTML tags balanced."""
    if len(text) <= TELEGRAM_LIMIT:
        send_message(token, chat_id, text)
        return
    chunk = ""
    for section in text.split("\n\n"):
        candidate = f"{chunk}\n\n{section}" if chunk else section
        if len(candidate) > TELEGRAM_LIMIT and chunk:
            send_message(token, chat_id, chunk)
            chunk = section
        else:
            chunk = candidate
    if chunk:
        send_message(token, chat_id, chunk)


def send_posters(token: str, chat_id: str, movies: list):
    """After the text digest, send the top movies' posters as one album.

    Movies arrive already sorted by number of screenings, so the first ones
    with a poster are the most-screened. Telegram albums hold 2-10 photos;
    a lone poster is sent as a single photo instead."""
    media = []
    for m in movies:
        poster = getattr(m, "poster_url", None)
        if not poster:
            continue
        caption = f"<b>{_html_escape(m.title, quote=False)}</b>"
        if getattr(m, "year", None):
            caption += f" ({m.year})"
        media.append({"type": "photo", "media": poster,
                      "caption": caption, "parse_mode": "HTML"})
        if len(media) >= MAX_POSTERS:
            break
    if not media:
        return
    try:
        if len(media) == 1:
            p = media[0]
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                json={"chat_id": chat_id, "photo": p["media"],
                      "caption": p["caption"], "parse_mode": "HTML"},
                timeout=30,
            )
        else:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMediaGroup",
                json={"chat_id": chat_id, "media": media},
                timeout=30,
            )
        if resp.status_code != 200:
            print(f"Poster send failed: {resp.text.strip()}")
    except requests.RequestException as exc:
        print(f"Poster send error: {exc}")


def _answer_callback(token: str, callback_id: str, text: str = ""):
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json={"callback_query_id": callback_id, "text": text},
            timeout=15,
        )
    except requests.RequestException:
        pass


def _auto_prompt_markup() -> dict:
    return {
        "inline_keyboard": [[
            {"text": "Yes, notify me weekly", "callback_data": "auto:on"},
            {"text": "No thanks", "callback_data": "auto:off"},
        ]]
    }


# --- Weekly push -----------------------------------------------------------

def _notify_subscribers(token: str) -> int:
    """Send each opted-in subscriber their watchlist matches. Returns count notified."""
    from .checker import check_usernames, format_telegram_message

    subscribers = [s for s in _load_subscribers() if s.get("auto")]
    notified = 0
    for sub in subscribers:
        chat_id = sub["chat_id"]
        username = sub["username"]
        try:
            movies, errors = check_usernames([username])
            msg = format_telegram_message(movies, errors, [username])
            send_long_message(token, chat_id, msg)
            if movies:
                send_posters(token, chat_id, movies)
            notified += 1
            print(f"Notified {sub.get('name', '?')} ({username}): {len(movies)} match(es)")
        except Exception as exc:
            print(f"Failed to notify {sub.get('name', '?')} ({username}): {exc}")
    return notified


def notify():
    """CLI entry point: run the weekly push once, now."""
    token = _require_token()
    subscribers = [s for s in _load_subscribers() if s.get("auto")]
    if not subscribers:
        raise SystemExit("No subscribers have opted into automatic notifications yet.")
    count = _notify_subscribers(token)
    print(f"Done. Notified {count} subscriber(s).")


def _scheduler_loop(token: str):
    """Background thread: fire the weekly push at the scheduled time, once per week."""
    while True:
        try:
            now = datetime.now(PARIS)
            if now.weekday() == NOTIFY_WEEKDAY and now.hour == NOTIFY_HOUR:
                today = now.strftime("%Y-%m-%d")
                state = _load_state()
                if state.get("last_notify") != today:
                    print(f"[scheduler] Weekly push firing ({today})...")
                    _notify_subscribers(token)
                    state["last_notify"] = today
                    _save_state(state)
        except Exception as exc:  # never let the scheduler thread die
            print(f"[scheduler] error: {exc}")
        time.sleep(60)


# --- Long-polling loop -----------------------------------------------------

def poll():
    """Long-polling loop: serve commands and run the weekly push in the background."""
    token = _require_token()

    scheduler = threading.Thread(target=_scheduler_loop, args=(token,), daemon=True)
    scheduler.start()

    print("Bot polling started. Press Ctrl+C to stop.")
    offset = 0

    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
            updates = resp.json().get("result", [])
        except requests.RequestException as exc:
            print(f"Polling error: {exc}")
            time.sleep(5)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            try:
                if "callback_query" in update:
                    _handle_callback(token, update["callback_query"])
                    continue

                message = update.get("message", {})
                text = message.get("text", "")
                chat_id = str(message.get("chat", {}).get("id", ""))
                user_name = message.get("from", {}).get("first_name", "Unknown")

                if not chat_id or not text.startswith("/"):
                    continue

                _handle_command(token, chat_id, user_name, text)
            except Exception as exc:
                # One bad update must never take the whole bot down.
                print(f"Error handling update {update.get('update_id')}: {exc}")


def _handle_callback(token: str, callback: dict):
    data = callback.get("data", "")
    callback_id = callback.get("id", "")
    chat_id = str(callback.get("message", {}).get("chat", {}).get("id", ""))
    if not chat_id or not data.startswith("auto:"):
        _answer_callback(token, callback_id)
        return

    want_auto = data == "auto:on"
    subscribers = _load_subscribers()
    for sub in subscribers:
        if sub["chat_id"] == chat_id:
            sub["auto"] = want_auto
            _save_subscribers(subscribers)
            break

    _answer_callback(token, callback_id, "Saved")
    if want_auto:
        send_message(
            token,
            chat_id,
            "Automatic weekly notifications are <b>on</b>. "
            "I'll message you every Wednesday. Turn them off anytime with /unsubscribe.",
        )
    else:
        send_message(
            token,
            chat_id,
            "No automatic notifications — you can still use /check anytime. "
            "Change your mind with /watch or /subscribe.",
        )


def _handle_command(token: str, chat_id: str, user_name: str, text: str):
    from .checker import check_usernames, format_telegram_message

    parts = text.strip().split()
    command = parts[0].split("@")[0].lower()

    if command == "/start":
        sub = _find_subscriber(chat_id)
        if sub:
            state = "on" if sub.get("auto") else "off"
            send_message(
                token,
                chat_id,
                f"Welcome back! You're tracking <b>{sub['username']}</b> "
                f"(automatic notifications: {state}).\n\n"
                "/check — what's screening from your watchlist\n"
                "/check <i>username</i> — check another user\n"
                "/watch <i>username</i> — change your tracked username\n"
                "/subscribe — turn on automatic weekly notifications\n"
                "/unsubscribe — turn them off\n"
                "/help — all commands",
            )
            return

        send_message(
            token,
            chat_id,
            "<b>Cine Watchlist Bot</b>\n\n"
            "I check if movies from your Letterboxd watchlist are screening "
            "in Paris, and I can notify you automatically every week.\n\n"
            "To get started, tell me your Letterboxd username:\n"
            "/watch <i>username</i>",
        )
        return

    if command == "/help":
        send_message(
            token,
            chat_id,
            "/watch <i>username</i> — set your Letterboxd username\n"
            "/check — what's screening from your watchlist\n"
            "/check <i>username</i> — check any Letterboxd user\n"
            "/subscribe — turn on automatic weekly notifications\n"
            "/unsubscribe — turn them off\n"
            "/help — this message",
        )
        return

    if command == "/watch":
        if len(parts) < 2:
            send_message(token, chat_id, "Usage: /watch <i>username</i>")
            return
        username = parts[1].lower().strip()

        subscribers = _load_subscribers()
        existing = next((s for s in subscribers if s["chat_id"] == chat_id), None)
        if existing:
            old = existing["username"]
            existing["username"] = username
            existing["name"] = user_name
            _save_subscribers(subscribers)
            note = f"Updated: now tracking <b>{username}</b> (was {old})."
        else:
            subscribers.append({
                "chat_id": chat_id,
                "username": username,
                "name": user_name,
                "auto": False,
            })
            _save_subscribers(subscribers)
            note = f"Now tracking <b>{username}</b>."

        send_message(
            token,
            chat_id,
            f"{note}\n\nWant automatic weekly notifications every Wednesday?",
            reply_markup=_auto_prompt_markup(),
        )
        return

    if command == "/subscribe":
        subscribers = _load_subscribers()
        sub = next((s for s in subscribers if s["chat_id"] == chat_id), None)
        if not sub:
            send_message(
                token, chat_id,
                "Set your username first: /watch <i>username</i>",
            )
            return
        sub["auto"] = True
        _save_subscribers(subscribers)
        send_message(
            token, chat_id,
            "Automatic weekly notifications are <b>on</b>. "
            "I'll message you every Wednesday.",
        )
        return

    if command == "/unsubscribe":
        subscribers = _load_subscribers()
        sub = next((s for s in subscribers if s["chat_id"] == chat_id), None)
        if not sub or not sub.get("auto"):
            send_message(token, chat_id, "Automatic notifications are already off.")
            return
        sub["auto"] = False
        _save_subscribers(subscribers)
        send_message(
            token,
            chat_id,
            "Automatic notifications are <b>off</b>. You can still use /check anytime.",
        )
        return

    if command == "/check":
        if len(parts) > 1:
            usernames = [p.lower().strip() for p in parts[1:]]
        else:
            sub = _find_subscriber(chat_id)
            if sub:
                usernames = [sub["username"]]
            else:
                send_message(
                    token,
                    chat_id,
                    "No username set. Use /watch <i>username</i> first, "
                    "or /check <i>username</i>.",
                )
                return

        send_message(
            token,
            chat_id,
            f"Checking watchlist for {', '.join(usernames)}...",
        )

        try:
            movies, errors = check_usernames(usernames)
            msg = format_telegram_message(movies, errors, usernames)
        except Exception as exc:
            movies, msg = [], f"Error: {exc}"

        send_long_message(token, chat_id, msg)
        if movies:
            send_posters(token, chat_id, movies)
        return
