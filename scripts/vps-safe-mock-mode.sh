#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-/opt/story-engine}"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing env file: ${ENV_FILE}" >&2
  exit 1
fi

backup_file="${ENV_FILE}.bak.$(date +%Y%m%d%H%M%S)"
cp "${ENV_FILE}" "${backup_file}"
echo "Backed up ${ENV_FILE} to ${backup_file}"

set_env_value() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" "${ENV_FILE}"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
  else
    printf '%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
  fi
}

set_env_value "VIDEO_PROVIDER" "mock"
set_env_value "STORAGE_PROVIDER" "r2"
set_env_value "VITE_API_BASE_URL" "/api"

echo "Updated ${ENV_FILE} for safe mock mode."
echo "Current values:"
grep -E '^(VIDEO_PROVIDER|STORAGE_PROVIDER|VITE_API_BASE_URL)=' "${ENV_FILE}"
echo
echo "Restart with:"
echo "docker compose --env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml up -d --build backend celery_worker frontend"

