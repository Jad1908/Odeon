# Cine Watchlist Telegram Bot

Notifies you (and friends) when a movie from your Letterboxd watchlist is
screening in Paris. It runs as **one always-on process** that:

- serves interactive commands over Telegram long-polling, and
- fires a **weekly push** every Wednesday ~10:00 Paris time from a background
  thread — no external cron, no commits, no manual files.

## Commands

| Command | What it does |
| --- | --- |
| `/start` | Intro / status |
| `/watch <username>` | Set your Letterboxd username, then choose auto-notify (Yes/No) |
| `/check` | Screenings from *your* watchlist, on demand |
| `/check <username>` | Screenings from any Letterboxd user's watchlist |
| `/subscribe` / `/unsubscribe` | Turn the weekly push on/off |
| `/help` | List commands |

Each person `/start`s the bot once and sets their own username — that
automatically captures their Telegram `chat_id` (required to message them), so
there is nothing to edit by hand.

## Storage

Subscribers live in a single JSON file (`{chat_id, username, name, auto}` per
person). Location: `watchlist/subscribers.json` by default, or wherever
`SUBSCRIBERS_FILE` points. It is git-ignored — it holds your users' data.

## Local run

```bash
uv sync                      # or: pip install requests cloudscraper
export TELEGRAM_BOT_TOKEN=... # from @BotFather
python -m watchlist bot      # serves commands + weekly push
# one-off manual test of the weekly push:
python -m watchlist notify
```

## BotFather setup

1. Talk to [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token.
2. `/setcommands` on your bot, paste:

```
start - Intro and status
watch - Set your Letterboxd username
check - Screenings from your (or another) watchlist
subscribe - Turn on weekly notifications
unsubscribe - Turn off weekly notifications
help - List commands
```

## Deploy: free always-on VM (recommended)

Any always-on Linux box works. A genuinely-free option is an **Oracle Cloud
"Always Free"** micro VM (or Google Cloud `e2-micro`). Real disk → the plain
local file just works.

1. Create the VM (Ubuntu), SSH in.
2. Install and fetch the code:
   ```bash
   sudo apt update && sudo apt install -y python3 python3-venv git
   git clone <your-repo-url> odeon && cd odeon
   python3 -m venv .venv && ./.venv/bin/pip install requests cloudscraper
   mkdir -p ~/watchlist-data   # stable storage, outside the repo
   ```
3. Install the service:
   ```bash
   sudo cp watchlist/deploy/watchlist-bot.service /etc/systemd/system/
   sudo nano /etc/systemd/system/watchlist-bot.service   # set TELEGRAM_BOT_TOKEN, paths, User
   sudo systemctl daemon-reload
   sudo systemctl enable --now watchlist-bot
   sudo systemctl status watchlist-bot          # verify it's running
   journalctl -u watchlist-bot -f               # live logs
   ```

`Restart=always` brings it back after crashes or reboots. To update: `git
pull` then `sudo systemctl restart watchlist-bot`.

## Deploy: container host (portable alternative)

A `Dockerfile` is included for container hosts (e.g. Fly.io). Build from the
repo root and mount a persistent volume at `/data` so the subscriber list
survives redeploys:

```bash
docker build -f watchlist/Dockerfile -t watchlist-bot .
docker run -d --restart=always \
  -e TELEGRAM_BOT_TOKEN=... \
  -v watchlist-data:/data \
  watchlist-bot
```
