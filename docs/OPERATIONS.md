# Operations runbook

Logs go to stdout: `docker compose logs -f api` (Flask) and `docker compose logs -f web` (nginx access/errors). Format: `time LEVEL logger message`.
Useful filters: `grep -E "ERROR|WARNING"`, `grep "LLM "`, `grep "send failed"`, `grep webhook`.

## Health
- `GET /healthz` → `{"status":"ok"}` (app + DB).
- Sidebar card "N of M numbers live" = WhatsApp connection status as last reported by the providers.

## Incident playbooks

### Site loads but every action fails / "Can't reach the server"
nginx is up but the API isn't: `docker compose ps`, `docker compose logs api`. A **502** in the nginx
log means `api` is down or still booting (migrations run at start).

### Blank page or 404 when reloading a URL like /inbox/3
The SPA fallback is missing: the web server must answer unknown paths with `index.html`
(`try_files … /index.html` in `frontend/nginx.conf`).

### Users get logged out immediately / "csrf_failed"
Frontend and API are on different origins, or `SESSION_COOKIE_SECURE=true` over plain http.
Serve both through the same nginx host over https.


### No replies on WhatsApp
Work down the pipeline (docs/reply-pipeline.png):
1. **Did the message arrive?** Inbox shows it? If not:
   - Evolution: `curl -H "apikey: $KEY" $EVO/webhook/find/<instance>` and check the URL equals the number's webhook URL (WhatsApp › Details). Check `connectionState` is `open`. Check the Evolution logs for webhook delivery errors (DNS/TLS to `PUBLIC_BASE_URL`).
   - Meta: Meta app › Webhooks shows delivery failures. A 401 in our logs means a wrong app secret.
   - Our logs show `webhook processing failed` with a traceback → payload format changed (see WHATSAPP_INTEGRATION.md › Version note).
2. **Arrived but no reply.** Open the chat and check:
   - Mode **Off**, no agent, agent **Paused**, or the **Needs you** state (handoff) → expected behaviour; use Resume agent.
   - Contact opted out (banner) → expected.
   - Chat is **Draft first** → the reply is waiting as a draft.
   - System note "The agent could not reply (model error)" → see "Model errors".
   - Draft with "Held as draft: sending limit reached" → raise Settings › WhatsApp › max per minute.
3. **Reply shows "Failed: …"** → the provider rejected the send. Evolution: the instance is disconnected (re-scan the QR). Meta: token expired, or outside the 24 h window.

### Model errors
Logs: `LLM <provider>/<model> failed: HTTP 401…` (bad key), `429` (quota/rate limit), `network error`.
- Workspace key: Settings › Models › provider › **Test**. The result shows the provider's message.
- Platform default: check `PLATFORM_LLM_*` env and that provider's status page. Turn on "Fallback to platform default" so customers keep getting answers when a user key fails.

### Number shows "Session expired"
The phone unlinked the device (logged out, phone offline for days, or WhatsApp action). Use WhatsApp › **Reconnect** and scan again. Frequent expiries on one number can mean a ban risk: move it to the Cloud API.

### Knowledge file stuck "Indexing…" / "Queued"
The worker died mid-job (e.g. a restart). Use the file's **…** › Re-index, or `flask --app wsgi reindex`.
"Failed · Scanned PDF" = the PDF has no text layer: OCR isn't included; upload a text PDF/DOCX instead.

### "database is locked"
Means more than one process is writing. Check you run `--workers 1` (DEPLOYMENT.md). Long-running admin
scripts against the live DB can also cause it: stop them.

### Lost ENCRYPTION_KEY
Stored API keys and WhatsApp credentials can't be decrypted (logged as "Could not decrypt a stored secret").
Set a new key, then users re-enter provider keys and reconnect numbers. Nothing else is affected.

### Disk filling up
`du -sh /data/uploads /data/agentry.db`. Lower retention days, then run `flask purge`, then `sqlite3 agentry.db "VACUUM;"` (needs free space roughly the size of the DB).

## Routine tasks
| Task | How |
|---|---|
| Create first owner when registration is closed | `docker compose exec api flask --app wsgi create-owner --email … --password …` |
| Reset a user's password | `python3 -c "from app.security import hash_password as h;print(h('NewPass123'))"` (run in the project folder) then `sqlite3 agentry.db "UPDATE users SET password_hash='<hash>' WHERE email='x@y'"` |
| Re-index everything (after chunk-size change) | `flask --app wsgi reindex` |
| Apply retention | `flask --app wsgi purge` (cron, daily) |
| Rotate SECRET_KEY | change env + restart; all users sign in again |
| Bump Meta API version | `META_GRAPH_VERSION=vNN.0` + restart |

## Install problems

### `pip install` fails: "Could not find a version that satisfies the requirement …" / "Requires-Python >=3.10"
Your Python is older than that release supports. `requirements.txt` uses version ranges, so pip
picks the newest compatible release. If it still fails:
1. `python3 --version`: Agentry supports **3.9 – 3.13**. Python 3.8 and older are not supported
   (the code uses `zoneinfo` and other 3.9 features). Install 3.11+ (pyenv, deadsnakes, python.org)
   or use Docker (`make docker`, image uses Python 3.13).
2. Upgrade pip first: `python3 -m pip install --upgrade pip` (old pips mis-resolve version ranges).
3. Always install inside a fresh virtualenv made with the right interpreter: `python3.11 -m venv .venv`.

### `make: python: No such file or directory`
Fixed in 1.1.2: the Makefile uses `.venv/bin/python` if `.venv` exists, otherwise `python3`. Force a
specific interpreter with `make test PYTHON=/usr/bin/python3.11`. Create the venv with `make venv`.

### `AttributeError: module 'hashlib' has no attribute 'scrypt'`
Fixed in 1.1.3. Python builds linked against LibreSSL (macOS's built-in `/usr/bin/python3` 3.9)
lack `hashlib.scrypt`, which Werkzeug uses by default for passwords. Agentry now always hashes with
PBKDF2-SHA256 (`app/security.py::hash_password`). That build also prints `NotOpenSSLWarning` from
urllib3; it works, but for production use a Python from python.org or Homebrew (OpenSSL 3).

### Login (or every API call) fails with `403 Forbidden` on a Mac
macOS 12+ runs the **AirPlay Receiver** on port 5000 and it answers every request with 403
(`curl -si localhost:5000/healthz` shows `Server: AirTunes`). Agentry's dev API therefore runs on
**5001** (`make api`; Vite proxies to 5001). If you start Flask yourself, pass `--port 5001`, or
turn off System Settings › General › AirDrop & Handoff › AirPlay Receiver.
