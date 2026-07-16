#!/bin/sh
set -eu

ENV_FILE="${1:-.env.production}"

docker compose --env-file "$ENV_FILE" -f docker-compose.managed.prod.yml build reverse_proxy frontend backend celery_worker
