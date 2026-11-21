#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
umask 077
mkdir -p backups
destination="backups/market-$(date -u +%Y%m%dT%H%M%SZ).dump"
temporary=$(mktemp backups/.market.XXXXXX)
trap 'rm -f "$temporary"' EXIT
docker compose exec -T db pg_dump -U market -d market -Fc > "$temporary"
mv "$temporary" "$destination"
printf '%s\n' "$destination"
