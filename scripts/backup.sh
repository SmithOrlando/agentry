#!/usr/bin/env bash
# Consistent copy of the database while Agentry runs, kept 14 days, in the agentry-data volume (/data/backups).
#   scripts/backup.sh                          # run from anywhere; uses the repo's docker-compose.yml
#   docker compose cp api:/data/backups ./backups   # copy them off the server
# Daily at 03:15 (crontab -e):
#   15 3 * * * /path/to/agentry/scripts/backup.sh >> /var/log/agentry-backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T api python - << 'PY'
import datetime, pathlib, sqlite3
d = pathlib.Path("/data/backups"); d.mkdir(exist_ok=True)
out = d / f"agentry-{datetime.datetime.now():%Y%m%d-%H%M}.db"
src = sqlite3.connect("/data/agentry.db"); dst = sqlite3.connect(out)
src.backup(dst); dst.close(); src.close()
for old in sorted(d.glob("agentry-*.db"))[:-14]:
    old.unlink()
print("backup:", out)
PY
