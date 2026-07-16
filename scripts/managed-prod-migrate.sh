#!/bin/sh
set -eu

ENV_FILE="${1:-.env.production}"
ACTION="${2:-upgrade}"

case "$ACTION" in
  upgrade)
    docker compose --env-file "$ENV_FILE" -f docker-compose.managed.prod.yml run --rm migrate
    ;;
  current)
    docker compose --env-file "$ENV_FILE" -f docker-compose.managed.prod.yml run --rm revision
    ;;
  *)
    echo "Usage: $0 [env-file] {upgrade|current}" >&2
    exit 1
    ;;
esac
