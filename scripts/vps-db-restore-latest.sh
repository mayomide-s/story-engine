#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-/opt/story-engine}"
BACKUP_DIR="${BACKUP_DIR:-/root/story-engine-backups/db}"

cd "${ROOT_DIR}"

latest_backup="$(find "${BACKUP_DIR}" -maxdepth 1 -type f -name '*.sql.gz' | sort | tail -n 1)"

if [[ -z "${latest_backup}" ]]; then
  echo "No .sql.gz backups found in ${BACKUP_DIR}" >&2
  exit 1
fi

echo "WARNING: This will overwrite the staging database from:"
echo "${latest_backup}"
echo
read -r -p "Type RESTORE to continue: " confirmation

if [[ "${confirmation}" != "RESTORE" ]]; then
  echo "Restore cancelled."
  exit 1
fi

gzip -dc "${latest_backup}" | docker compose --env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml exec -T postgres \
  sh -lc '
    psql -U "${POSTGRES_USER:-postgres}" -d postgres -v ON_ERROR_STOP=1 \
      -c "DROP DATABASE IF EXISTS ${POSTGRES_DB:-sociopost};" \
      -c "CREATE DATABASE ${POSTGRES_DB:-sociopost};"
    psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-sociopost}" -v ON_ERROR_STOP=1
  '

echo "Restore completed from: ${latest_backup}"
