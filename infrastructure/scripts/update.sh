#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
git diff --quiet
git diff --cached --quiet
bash infrastructure/scripts/backup.sh
git pull --ff-only
docker compose up -d --build --wait
