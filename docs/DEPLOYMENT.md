# Deployment

> **Quickest path:** Docker Compose, in [DEPLOY_VPS.md](DEPLOY_VPS.md).

Two containers plus a persistent folder:

| Container | Image | Role | Public? |
|---|---|---|---|
| `web` | `frontend/Dockerfile` (Node build → nginx) | Serves the Vue app; proxies `/api`, `/webhooks`, `/healthz` to `api` | **Yes**, behind TLS |
| `api` | `Dockerfile` (Python + gunicorn) | Flask JSON API + webhooks; data in `/data` (SQLite + uploads) | No (internal only) |
| `evolution` (+ Postgres, Redis) | `evoapicloud/evolution-api` | Optional (`--profile evolution`): self-hosted Evolution API for QR-linked numbers | No |

WhatsApp providers must reach `https://<your domain>/webhooks/...`, which nginx forwards to Flask.

## Option A: Docker Compose (recommended)
```bash
git clone <repo> agentry && cd agentry
scripts/init-env.sh agentry.example.com
docker compose up -d --build
```
The full walkthrough is in [DEPLOY_VPS.md](DEPLOY_VPS.md): HTTPS with Caddy, the first account, Evolution API, backups and updates.

## Option B: without Docker
**Frontend:** `cd frontend && npm ci && npm run build`, then serve `frontend/dist/` with any web server
that (1) falls back to `index.html` for unknown paths and (2) proxies `/api`, `/webhooks` and `/healthz`
to the API. `frontend/nginx.conf` is a complete example: change `proxy_pass http://api:8000` to
`http://127.0.0.1:8000`.

**API** (`/etc/systemd/system/agentry.service`):
```ini
[Service]
WorkingDirectory=/opt/agentry
EnvironmentFile=/opt/agentry/.env
ExecStart=/opt/agentry/.venv/bin/gunicorn wsgi:app --bind 127.0.0.1:8000 --workers 1 --threads 16 --timeout 120
Restart=always
User=agentry
[Install]
WantedBy=multi-user.target
```

> The frontend and API **must share one origin** (same scheme + host + port) because auth uses a
> SameSite cookie and there is no CORS. Hosting them on different domains needs code changes
> (CORS + cookie settings); see MAINTENANCE.md.

## Required scheduled job
Data retention (Settings › Security) runs from cron, once a day:
```
15 3 * * *  cd /opt/agentry && .venv/bin/flask --app wsgi purge >> /var/log/agentry-purge.log 2>&1
```
Docker: `docker compose exec -T api flask --app wsgi purge` (from the repo folder).

## ⚠️ One API process only
Run **one** gunicorn worker (`--workers 1`) and scale with `--threads`. Background jobs live in that
process's memory, and SQLite should have one writer process. The `web` container is stateless and
can be scaled freely. To scale the API, see MAINTENANCE.md › Scaling.

## Backups
Back up three things: the SQLite file (`sqlite3 /data/agentry.db ".backup '/backups/agentry-$(date +%F).db'"`,
safe while running), the `/data/uploads` folder, and the `ENCRYPTION_KEY` (in your secret manager).

## Upgrades
`git pull && docker compose up -d --build`. API migrations run automatically at boot; back up the DB
first. The frontend is static, so a rebuild replaces it atomically. Rollback = previous images + the DB
backup taken before the upgrade (migrations are forward-only).

## Release checklist
- [ ] `make test` green; `make check` (Vue production build) succeeds
- [ ] `.env` has SECRET_KEY, ENCRYPTION_KEY, PUBLIC_BASE_URL + FRONTEND_URL (https), SESSION_COOKIE_SECURE=true, `ENABLE_TEST_TOOLS` unset or `false`, and either real `PLATFORM_LLM_*` or a plan for workspaces to add their own keys
- [ ] `https://<domain>/healthz` returns ok (proves nginx → API)
- [ ] Reload a deep link such as `/settings/models` and confirm it loads (SPA fallback works)
- [ ] Settings › Models: a key is saved and **Test** passes; the Playground answers
- [ ] Real number: send yourself a WhatsApp message and get a draft or reply
- [ ] Cron `purge` installed; backups scheduled and one restore tested
