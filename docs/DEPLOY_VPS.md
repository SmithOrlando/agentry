# Deploy with Docker

Agentry runs as two containers from `docker-compose.yml`:

| Container | What | Published |
|---|---|---|
| `agentry-web-1` | nginx serving the Vue app; forwards `/api`, `/webhooks`, `/healthz` to `api` | `127.0.0.1:8090` (change with `AGENTRY_BIND` / `AGENTRY_PORT`) |
| `agentry-api-1` | Flask API + WhatsApp webhooks | no (internal only) |

Data (SQLite database, uploaded files, backups) lives in the Docker volume `agentry_agentry-data`.

```
Internet ── HTTPS proxy (e.g. Caddy) ──► 127.0.0.1:8090  web (nginx + Vue) ──► api (Flask) ── volume
WhatsApp provider (Evolution / Meta) ──► https://agentry.<domain>/webhooks/…  (same path)
```

## 1. Prerequisites
- A Linux server with Docker and Compose v2 (`docker compose version`), and about 1 GB free RAM for the first build.
- A DNS `A` record such as `agentry.example.com` pointing at the server.
- Port 8090 free on the server: `ss -ltn | grep 8090` prints nothing. Otherwise set `AGENTRY_PORT` in `.env`.

## 2. Install
```bash
git clone https://github.com/<you>/agentry.git /opt/agentry && cd /opt/agentry
scripts/init-env.sh agentry.example.com      # creates .env: fresh SECRET_KEY, ENCRYPTION_KEY, Evolution passwords
docker compose up -d --build                 # first build takes a few minutes
docker compose ps                            # both "running"; api "healthy"
curl http://127.0.0.1:8090/healthz           # {"status":"ok"}
```
**Save `ENCRYPTION_KEY`** in a password manager now (`grep ENCRYPTION_KEY .env`). Every stored API key and
WhatsApp credential is encrypted with it. **Never commit `.env`**; `.gitignore` already excludes it.

## 3. HTTPS
Caddy installed on the host (`/etc/caddy/Caddyfile`):
```
agentry.example.com {
    encode gzip
    reverse_proxy 127.0.0.1:8090
}
```
`caddy validate --config /etc/caddy/Caddyfile && systemctl reload caddy`, then `curl https://agentry.example.com/healthz`.
Any other proxy works the same way: forward everything to `127.0.0.1:8090`.

## 4. First use
1. Open `https://agentry.example.com` and **create a workspace**. You become the owner.
2. Close public sign-up: `ALLOW_REGISTRATION=false` in `.env`, then `docker compose up -d`. Teammates join through
   **Settings › Team** invite links.
3. **Settings › Models:** add an API key (the first key is used automatically) and press **Test**.
4. **WhatsApp › Connect a number** (see below). Set the number to **Draft** until you trust the answers.

## 5. WhatsApp through Evolution API
**Already running Evolution elsewhere** (its own stack or another server): use its public URL, e.g.
`https://evo.example.com`, plus its API key. Evolution posts incoming messages to
`https://agentry.example.com/webhooks/…`, so `PUBLIC_BASE_URL` in `.env` must be that public https address.

**Or run Evolution from this repo** (the passwords come from `.env`):
```bash
docker compose --profile evolution up -d
```
In Agentry use server URL `http://evolution:8080` and the `EVOLUTION_API_KEY` from `.env`.

## 6. Backups and data retention
```bash
scripts/backup.sh                                   # consistent copy into the volume, 14 kept
docker compose cp api:/data/backups ./backups       # copy them off the server
```
Schedule both daily (`crontab -e`):
```
15 3 * * * /opt/agentry/scripts/backup.sh >> /var/log/agentry-backup.log 2>&1
30 3 * * * cd /opt/agentry && docker compose exec -T api flask --app wsgi purge >> /var/log/agentry-purge.log 2>&1
```
To restore: `docker compose stop api`, copy a backup over `/data/agentry.db` with `docker compose cp`, then
`docker compose start api`. Use the same `ENCRYPTION_KEY`.

## 7. Updating
```bash
cd /opt/agentry && git pull && docker compose up -d --build
```
`.env` and the data volume are untouched. Database migrations run when the API starts, so take a backup first.

## Everyday commands
| Task | Command |
|---|---|
| Status | `docker compose ps` |
| Logs | `docker compose logs -f api` (or `web`) |
| Restart | `docker compose restart` |
| Apply `.env` changes | `docker compose up -d` |
| Create an owner without the web form | `docker compose exec api flask --app wsgi create-owner --email you@x.com --password '…' --workspace "Name"` |
| Stop (keeps data) | `docker compose down` |

## Troubleshooting
- **502 from the proxy:** run `docker compose ps` and `docker compose logs api --tail 50`.
- **Signed out right after logging in:** `PUBLIC_BASE_URL`/`FRONTEND_URL` must be the exact `https://` address you open.
- **WhatsApp messages don't arrive:** check Evolution's logs. The webhook URL must start with your `PUBLIC_BASE_URL`.
  If it shows `localhost`, the number was added before `PUBLIC_BASE_URL` was set: delete the number in Agentry and add it again.
- **Build fails during `npm ci`:** not enough memory. Add swap, or build elsewhere and push the images to a registry.
