"""
Send the validated newsletter through Resend.

The prerendered preview HTML (the exact output validation checked) is uploaded
to Resend as a broadcast against the configured audience, then sent. Only an
issue whose status is "ready" can be sent; any edit puts it back into draft,
so what goes out is always what was validated.

Configuration comes from the environment (a repo-root .env file is also read):
    RESEND_API_KEY     secret API key from resend.com/api-keys
    RESEND_SEGMENT_ID  segment (formerly "audience") to send to
    RESEND_FROM        sender, e.g. "Paris Ciné <cine@yourdomain.com>"
                       (the domain must be verified in Resend)
"""
import json
import os
from datetime import datetime

import requests

from . import issue as issue_store
from .prerender import PREVIEW_FILE

RESEND_API = "https://api.resend.com"
ENV_FILE = ".env"

# Resend substitutes this placeholder with a per-recipient unsubscribe link
UNSUBSCRIBE_SNIPPET = (
    '<p style="text-align:center;font-size:12px;color:#94a3b8;margin:24px 0;">'
    '<a href="{{{RESEND_UNSUBSCRIBE_URL}}}" style="color:#94a3b8;">Se désinscrire</a></p>'
)


def _load_env_file():
    """Fill os.environ from a repo-root .env file (existing vars win)."""
    if not os.path.exists(ENV_FILE):
        return
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


def get_config() -> dict:
    _load_env_file()
    return {
        "api_key": os.environ.get("RESEND_API_KEY", ""),
        # RESEND_AUDIENCE_ID kept as an alias from before Resend's rename
        "segment_id": (os.environ.get("RESEND_SEGMENT_ID", "")
                       or os.environ.get("RESEND_AUDIENCE_ID", "")),
        "from": os.environ.get("RESEND_FROM", ""),
    }


def config_problems(config: dict) -> list:
    missing = [name for name, key in
               [("RESEND_API_KEY", "api_key"),
                ("RESEND_SEGMENT_ID", "segment_id"),
                ("RESEND_FROM", "from")]
               if not config[key]]
    if missing:
        return [f"Missing configuration: set {', '.join(missing)} "
                f"(environment or .env file at the repo root)."]
    return []


def default_subject(issue: dict) -> str:
    content = issue.get("content") or {}
    title = content.get("title") or "Newsletter"
    kicker = content.get("kicker") or ""
    return f"{title} — {kicker}" if kicker else title


def _api_error(resp: requests.Response) -> str:
    try:
        detail = resp.json().get("message") or resp.text
    except (ValueError, json.JSONDecodeError):
        detail = resp.text
    return f"Resend API error (HTTP {resp.status_code}): {detail}"


def send_newsletter(subject: str = None) -> dict:
    """Upload the validated render as a Resend broadcast and send it."""
    issue = issue_store.load_issue()
    if issue.get("status") != "ready":
        return {"ok": False, "error": "The issue is not validated — run validation "
                                      "until all checks pass before sending."}

    config = get_config()
    problems = config_problems(config)
    if problems:
        return {"ok": False, "error": problems[0]}

    if not os.path.exists(PREVIEW_FILE):
        return {"ok": False, "error": "No prerender found — validate again to regenerate it."}
    with open(PREVIEW_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    # Broadcasts to an audience should always carry an unsubscribe link
    if "RESEND_UNSUBSCRIBE_URL" not in html:
        if "</body>" in html:
            html = html.replace("</body>", UNSUBSCRIBE_SNIPPET + "</body>", 1)
        else:
            html += UNSUBSCRIBE_SNIPPET

    subject = (subject or "").strip() or default_subject(issue)
    headers = {"Authorization": f"Bearer {config['api_key']}",
               "Content-Type": "application/json"}
    name = f"{subject} ({datetime.now().strftime('%Y-%m-%d')})"

    try:
        # "send": true creates the broadcast and sends it in one atomic call
        resp = requests.post(f"{RESEND_API}/broadcasts", headers=headers, timeout=30,
                             json={"segment_id": config["segment_id"],
                                   "from": config["from"],
                                   "subject": subject,
                                   "name": name,
                                   "html": html,
                                   "send": True})
        if resp.status_code >= 400:
            return {"ok": False, "error": _api_error(resp)}
        broadcast_id = resp.json().get("id")
        if not broadcast_id:
            return {"ok": False, "error": f"Resend did not return a broadcast id: {resp.text}"}
    except requests.RequestException as e:
        return {"ok": False, "error": f"Could not reach Resend: {type(e).__name__}: {e}"}

    sent = issue_store.record_send(broadcast_id, subject)
    return {"ok": True, "error": None, "broadcast_id": broadcast_id,
            "subject": subject, "sent_at": sent["last_send"]["sent_at"]}
