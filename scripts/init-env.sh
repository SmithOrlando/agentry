#!/usr/bin/env bash
# Create .env from .env.example with fresh secrets:   scripts/init-env.sh agentry.example.com
# Refuses to overwrite an existing .env (it holds the encryption key for your stored credentials).
set -euo pipefail
cd "$(dirname "$0")/.."
DOMAIN="${1:?usage: scripts/init-env.sh agentry.example.com}"
DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN%/}"
[ -f .env ] && { echo ".env already exists: not touching it."; exit 1; }

rand() { openssl rand -hex "$1"; }
FERNET=$(openssl rand -base64 32 | tr '+/' '-_')
sed -e "s|^SECRET_KEY=.*|SECRET_KEY=$(rand 32)|" \
    -e "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=$FERNET|" \
    -e "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://$DOMAIN|" \
    -e "s|^FRONTEND_URL=.*|FRONTEND_URL=https://$DOMAIN|" \
    -e "s|^EVOLUTION_API_KEY=.*|EVOLUTION_API_KEY=$(rand 24)|" \
    -e "s|^EVOLUTION_DB_PASSWORD=.*|EVOLUTION_DB_PASSWORD=$(rand 24)|" \
    .env.example > .env
chmod 600 .env
echo "Created .env for https://$DOMAIN"
echo "Back up this line (password manager): $(grep '^ENCRYPTION_KEY=' .env)"
echo "Next: docker compose up -d --build"
