"""Check that a local Agentry setup actually works end to end, and say how to fix what doesn't.

    make doctor        (or: python3 scripts/doctor.py)

Run it while `make dev` (or `make api` + `make web`) is running in another terminal.
Checks: Python packages · .env · API on :5001 · port 5000 trap · Vue dev server + its /api proxy ·
database has a user · an AI model is configured · a real WhatsApp number exists.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = os.environ.get("AGENTRY_API", "http://localhost:5001")
WEB = os.environ.get("AGENTRY_WEB", "http://localhost:5173")
OK, BAD, WARN = "\033[32m✓\033[0m", "\033[31m✗\033[0m", "\033[33m!\033[0m"
problems = 0


def say(mark, text, fix=""):
    global problems
    if mark == BAD:
        problems += 1
    print(f" {mark} {text}")
    if fix:
        print(f"     → {fix}")


def fetch(url):
    """(status, content_type, body) or (None, None, error text)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=4) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read(2000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read(2000).decode("utf-8", "replace")
    except Exception as e:  # connection refused, timeout…
        return None, None, str(getattr(e, "reason", e))


print("\nAgentry doctor\n")

# 1. Python packages
missing = []
for mod in ("flask", "cryptography", "requests", "pypdf", "docx", "openpyxl", "dotenv"):
    try:
        __import__(mod)
    except ImportError:
        missing.append(mod)
say(BAD if missing else OK, "Python packages" + (f": missing {', '.join(missing)}" if missing else f" ({sys.executable})"),
    "make install" if missing else "")

# 2. .env
env = ROOT / ".env"
if env.exists():
    try:
        from dotenv import dotenv_values
        values = dotenv_values(env)
    except ImportError:
        values = {}
    os.environ.update({k: v for k, v in values.items() if v is not None and k not in os.environ})
    say(OK, ".env found")
    if str(values.get("SESSION_COOKIE_SECURE", "")).lower() == "true" and WEB.startswith("http://"):
        say(BAD, ".env has SESSION_COOKIE_SECURE=true but you're on plain http: Safari drops the login cookie",
            "for local development set SESSION_COOKIE_SECURE=false (keep true in production)")
    if str(values.get("PUBLIC_BASE_URL", "")).startswith("https://agents.example.com"):
        say(WARN, "PUBLIC_BASE_URL is still the example value", "set it to http://localhost:5001 (or your tunnel URL for WhatsApp webhooks)")
else:
    say(WARN, "No .env file: using development defaults (placeholder AI model)",
        "cp .env.example .env  (optional in development: you can add an API key in Settings → Models instead)")

# 3. API
status, ctype, text = fetch(f"{API}/healthz")
if status == 200 and "json" in (ctype or ""):
    say(OK, f"API answering at {API}")
elif status is None:
    say(BAD, f"API not running at {API} ({text})", "start it: make api   (or make dev for API + web together)")
else:
    say(BAD, f"{API}/healthz answered {status} {ctype}: that isn't Agentry", "is another program using that port? stop it, or set AGENTRY_API")

# 4. the port-5000 trap (macOS AirPlay Receiver)
s5000, c5000, _ = fetch("http://localhost:5000/healthz")
if s5000 == 403 and "json" not in (c5000 or ""):
    say(WARN, "Port 5000 is taken by macOS AirPlay Receiver (answers 403)",
        "harmless as long as nothing points at :5000 — Agentry uses :5001. Check you didn't start Flask with --port 5000 or set AGENTRY_API to it")

# 5. Vue dev server and its proxy
ws, wc, _ = fetch(f"{WEB}/")
if ws is None:
    say(BAD, f"Vue dev server not running at {WEB}", "start it: make web   (first time: cd frontend && npm install)")
else:
    say(OK, f"Vue dev server answering at {WEB}")
    ps, pc, pt = fetch(f"{WEB}/api/me")
    if ps == 401 and "json" in (pc or ""):
        say(OK, "Vue → API proxy works (/api/me reaches Flask)")
    elif ps == 200 and "json" in (pc or ""):
        say(OK, "Vue → API proxy works")
    else:
        say(BAD, f"Vue → API proxy broken: {WEB}/api/me answered {ps} {pc or ''}".strip(),
            f"the API must be running at {API} (make api). If it runs elsewhere, start Vite with AGENTRY_API=<url> npm run dev")
if not (ROOT / "frontend" / "node_modules").exists():
    say(BAD, "frontend/node_modules missing", "cd frontend && npm install")

# 6. database + setup state (read straight from SQLite; works even if the API is down)
db = Path(os.environ.get("DATABASE_PATH") or ROOT / "instance" / "agentry.db")
if not db.exists():
    say(WARN, f"No database yet at {db}", "it's created when the API starts; then open the app and create your workspace")
else:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    users = con.execute("SELECT email FROM users ORDER BY id").fetchall()
    say(OK if users else BAD, f"Database: {len(users)} user(s)" + (f" — e.g. {users[0]['email']}" if users else ""),
        "" if users else "open the app and create your workspace")
    platform = os.environ.get("PLATFORM_LLM_PROVIDER", "")
    test_tools = os.environ.get("ENABLE_TEST_TOOLS", "").lower() in ("1", "true", "yes", "on")
    if test_tools:
        say(WARN, "ENABLE_TEST_TOOLS is on: Sandbox, Simulate and the placeholder model are available",
            "fine on your laptop; never on the VPS")
    for w in con.execute("SELECT id, name, llm_settings FROM workspaces"):
        llm = json.loads(w["llm_settings"] or "{}")
        keys = {r["provider"] for r in con.execute("SELECT provider FROM provider_keys WHERE workspace_id = ?", [w["id"]])}
        if llm.get("source") == "byok" and llm.get("provider") in keys:
            say(OK, f"Workspace “{w['name']}”: AI model = own {llm['provider']} key · {llm.get('model') or '(no model name!)'}",
                "" if llm.get("model") else "Settings → Models: pick a model name")
        elif platform and (platform != "mock" or test_tools):
            say(OK, f"Workspace “{w['name']}”: AI model = platform default ({platform})")
        else:
            say(BAD, f"Workspace “{w['name']}”: no AI model, so agents can't reply",
                "in the app: Settings → Models → add an OpenAI / DeepSeek / Anthropic / Gemini / Qwen key "
                "(it's used automatically). Or for everyone: PLATFORM_LLM_PROVIDER / _MODEL / _API_KEY in .env, then restart the API")
        real = con.execute("SELECT provider, status, name FROM wa_connections WHERE workspace_id = ? AND provider != 'sandbox'", [w["id"]]).fetchall()
        if not real:
            say(WARN, f"Workspace “{w['name']}”: no real WhatsApp number linked",
                "WhatsApp page → Connect a number → Evolution API (needs an Evolution server: docker compose up evolution) or Meta Cloud API")
        for r in real:
            say(OK if r["status"] == "connected" else WARN, f"WhatsApp “{r['name']}” ({r['provider']}): {r['status']}",
                "" if r["status"] == "connected" else "WhatsApp page → open the number → scan the QR / check the details")

print(f"\n{'All good.' if not problems else f'{problems} problem(s) to fix.'}\n")
sys.exit(1 if problems else 0)
