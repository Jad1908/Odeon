# Cine Watchlist Telegram Bot

Notifies you and friends when a movie on your Letterboxd watchlist is screening
in Paris. **One always-on process** serves interactive commands and pushes a
weekly digest — no external cron, no commits, no manual subscriber files.

## Commands (in Telegram)

| Command | Does |
| --- | --- |
| `/start` | Intro / status |
| `/watch <username>` | Set your Letterboxd username, then choose weekly notifications (Yes/No) |
| `/check` | Screenings from your watchlist, right now |
| `/check <username>` | Screenings from any Letterboxd user's watchlist |
| `/subscribe` · `/unsubscribe` | Turn the weekly push on/off |
| `/help` | List commands |

Friends just `/start` → `/watch <username>` → **Yes**. That captures them
automatically — you never edit a file.

## How it runs

- **One process:** `python -m watchlist bot` long-polls Telegram for commands and
  runs the weekly push on a background thread (**Wednesday ~10:00 Paris**).
- **Storage:** subscribers live in one JSON file at `$SUBSCRIBERS_FILE`
  (git-ignored). The weekly push only messages those who opted in (`auto: true`).

---

## Setup on a free VM (Google Cloud e2-micro)

**1 · Telegram bot** — [@BotFather](https://t.me/BotFather): `/newbot`, copy the
token. Then `/setcommands` and paste:
```
start - Intro and status
watch - Set your Letterboxd username
check - Screenings from your (or another) watchlist
subscribe - Turn on weekly notifications
unsubscribe - Turn off weekly notifications
help - List commands
```

**2 · VM** — Compute Engine → Create instance, **always-free** config:
`e2-micro` · region `us-central1` · Ubuntu 24.04 LTS · **30 GB Standard** disk ·
no snapshot schedule · firewall HTTP/HTTPS **off** (the bot is outbound-only).
Compute + disk are free; only the external IP costs ~$3/mo (covered by trial credits).

**3 · Install** (click **SSH** on the instance):
```bash
sudo apt update && sudo apt install -y python3 python3-venv git
git clone https://github.com/Jad1908/Odeon.git   # private repo: username + a GitHub PAT as the password
cd Odeon && git checkout watchlist-notifier       # skip if already merged to main
python3 -m venv .venv && ./.venv/bin/pip install requests cloudscraper
mkdir -p ~/watchlist-data
```

**4 · Create the service** (paths auto-fill from your user — paste as-is):
```bash
sudo tee /etc/systemd/system/watchlist-bot.service >/dev/null <<EOF
[Unit]
Description=Cine Watchlist Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/Odeon
Environment=TELEGRAM_BOT_TOKEN=PASTE_TOKEN
Environment=SUBSCRIBERS_FILE=$HOME/watchlist-data/subscribers.json
ExecStart=$HOME/Odeon/.venv/bin/python -m watchlist bot
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

**5 · Set the token** (kept visible so you can catch a bad paste — Ubuntu Minimal
has no `nano`):
```bash
read -rp "Paste the bot token: " TG_TOKEN
printf 'Check: [%s]\n' "$TG_TOKEN"     # nothing may appear after the token before the ]
sudo sed -i "s|^Environment=TELEGRAM_BOT_TOKEN=.*|Environment=TELEGRAM_BOT_TOKEN=$TG_TOKEN|" /etc/systemd/system/watchlist-bot.service
unset TG_TOKEN
```

**6 · Start it:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now watchlist-bot
systemctl status watchlist-bot --no-pager      # want: active (running)
```
Close SSH and message the bot — it answers on its own, and restarts after crashes
or reboots.

---

## Everyday commands

| Task | Command |
| --- | --- |
| Restart | `sudo systemctl restart watchlist-bot` |
| Status | `systemctl status watchlist-bot --no-pager` |
| Live logs | `journalctl -u watchlist-bot -f` |
| Update code | `cd ~/Odeon && git pull && sudo systemctl restart watchlist-bot` |
| After editing the service file | `sudo systemctl daemon-reload && sudo systemctl restart watchlist-bot` |
| Test the weekly push now | define `pushnow` (below), then run `pushnow` |
| See who's subscribed | `cat ~/watchlist-data/subscribers.json` |

Manual push trigger (define once per SSH session):
```bash
pushnow() {
  TELEGRAM_BOT_TOKEN="$(sudo grep -oP 'TELEGRAM_BOT_TOKEN=\K.*' /etc/systemd/system/watchlist-bot.service)" \
  SUBSCRIBERS_FILE="$HOME/watchlist-data/subscribers.json" \
  ~/Odeon/.venv/bin/python -m watchlist notify
}
```

---

## Troubleshooting

| Symptom | Cause → Fix |
| --- | --- |
| Commands ignored, but status is `active (running)` | Edited the service file (e.g. the token) without reloading → **`sudo systemctl daemon-reload && sudo systemctl restart watchlist-bot`** |
| `pgrep -af 'watchlist bot'` shows **2+** lines | A stray manual run is fighting the service (Telegram allows one poller) → `sudo systemctl stop watchlist-bot; pkill -f 'watchlist bot'; sudo systemctl start watchlist-bot` |
| Push fails with `404` and a `.../bot<token>/...` URL | Malformed token in the service file → redo step 5; the printed value must have nothing after the token |
| `nano: command not found` | Ubuntu Minimal → edit via `sed` (step 5), or `sudo apt install -y nano` |

**Rotate a leaked token:** BotFather → `/mybots` → your bot → API Token → Revoke,
then redo step 5. Never paste the token — or a full `.../bot<token>/...` URL — into
a chat, screenshot, or issue.

> A container `Dockerfile` is also included for non-VM hosts; it's optional and not
> needed for the setup above.
