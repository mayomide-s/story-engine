#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-/opt/story-engine}"
cd "${ROOT_DIR}"

git fetch origin
git checkout master
git reset --hard origin/master

docker compose --env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml up -d --build backend celery_worker frontend
