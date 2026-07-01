#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-/opt/story-engine}"
BACKUP_DIR="${BACKUP_DIR:-/root/story-engine-backups/db}"
KEEP_COUNT="${KEEP_COUNT:-14}"

cd "${ROOT_DIR}"
mkdir -p "${BACKUP_DIR}"

timestamp="$(date +%Y%m%d-%H%M%S)"
backup_base="story-engine-staging-${timestamp}.sql"
backup_path="${BACKUP_DIR}/${backup_base}"
gzip_path="${backup_path}.gz"

docker compose --env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml exec -T postgres \
  sh -lc 'pg_dump -U "${POSTGRES_USER:-postgres}" "${POSTGRES_DB:-sociopost}"' > "${backup_path}"

gzip -f "${backup_path}"

mapfile -t backups < <(find "${BACKUP_DIR}" -maxdepth 1 -type f -name '*.sql.gz' | sort)
if (( ${#backups[@]} > KEEP_COUNT )); then
  delete_count=$(( ${#backups[@]} - KEEP_COUNT ))
  for old_backup in "${backups[@]:0:delete_count}"; do
    rm -f "${old_backup}"
  done
fi

file_size="$(du -h "${gzip_path}" | awk '{print $1}')"
echo "Created backup: ${gzip_path}"
echo "Backup size: ${file_size}"
