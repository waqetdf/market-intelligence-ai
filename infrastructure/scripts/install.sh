#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
docker compose version >/dev/null
if [[ ! -e .env ]]; then
  umask 077
  sed -e "s/^POSTGRES_PASSWORD=$/POSTGRES_PASSWORD=$(openssl rand -hex 24)/" \
      -e "s/^MARKET_PASSWORD=$/MARKET_PASSWORD=$(openssl rand -hex 24)/" .env.example > .env
fi
mkdir -p data/mt5 backups
docker compose up -d --build --wait --wait-timeout 120
