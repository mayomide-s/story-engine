#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-/opt/story-engine}"
if [[ "${ROOT_DIR}" =~ ^[0-9]+$ ]]; then
  WINDOW_MINUTES="${ROOT_DIR}"
  ROOT_DIR="/opt/story-engine"
else
  WINDOW_MINUTES="${2:-30}"
fi

STAGING_URL="${STAGING_URL:-https://story.soremekun.org}"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env}"
ENV_BACKUP_DIR="${ENV_BACKUP_DIR:-/root/story-engine-backups/env}"
COMPOSE_ARGS=(--env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml)
RELEASE_CHECK_SCRIPT="scripts/vps-staging-release-check.sh"
SAFE_MOCK_SCRIPT="scripts/vps-safe-mock-mode.sh"
PYTHON3_BIN="$(command -v python3 || true)"

if [[ ! "${WINDOW_MINUTES}" =~ ^[0-9]+$ ]]; then
  echo "Window minutes must be a whole number." >&2
  exit 1
fi

if (( WINDOW_MINUTES < 1 )); then
  echo "Window minutes must be at least 1." >&2
  exit 1
fi

if (( WINDOW_MINUTES > 60 )); then
  WINDOW_MINUTES=60
fi

cd "${ROOT_DIR}"

echo "Story Engine controlled Runway paid-test window"
echo "Root: ${ROOT_DIR}"
echo "URL: ${STAGING_URL}"
echo "Window: ${WINDOW_MINUTES} minutes"
echo
echo "Warning: this temporarily enables a paid video provider and may spend real Runway credits."
echo

if [[ "${CONFIRM_RUNWAY_COST:-}" != "YES" ]]; then
  read -r -p "Type RUNWAY_PAID_TEST to continue: " typed_confirmation
  if [[ "${typed_confirmation:-}" != "RUNWAY_PAID_TEST" ]]; then
    echo "Confirmation failed. Aborting."
    exit 1
  fi
fi

if [[ -z "${PYTHON3_BIN}" ]]; then
  echo "python3 is required for health verification." >&2
  exit 1
fi

if [[ ! -f "${RELEASE_CHECK_SCRIPT}" ]]; then
  echo "Missing release checklist script: ${RELEASE_CHECK_SCRIPT}" >&2
  exit 1
fi

if [[ ! -f "${SAFE_MOCK_SCRIPT}" ]]; then
  echo "Missing safe mock mode script: ${SAFE_MOCK_SCRIPT}" >&2
  exit 1
fi

echo "Running staging release checklist first..."
bash "${RELEASE_CHECK_SCRIPT}" "${ROOT_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing env file: ${ENV_FILE}" >&2
  exit 1
fi

current_video_provider="$(grep -E '^VIDEO_PROVIDER=' "${ENV_FILE}" | tail -n 1 | cut -d'=' -f2- || true)"
current_storage_provider="$(grep -E '^STORAGE_PROVIDER=' "${ENV_FILE}" | tail -n 1 | cut -d'=' -f2- || true)"
runway_api_key="$(grep -E '^RUNWAY_API_KEY=' "${ENV_FILE}" | tail -n 1 | cut -d'=' -f2- || true)"
r2_account_id="$(grep -E '^R2_ACCOUNT_ID=' "${ENV_FILE}" | tail -n 1 | cut -d'=' -f2- || true)"
r2_access_key_id="$(grep -E '^R2_ACCESS_KEY_ID=' "${ENV_FILE}" | tail -n 1 | cut -d'=' -f2- || true)"
r2_secret_access_key="$(grep -E '^R2_SECRET_ACCESS_KEY=' "${ENV_FILE}" | tail -n 1 | cut -d'=' -f2- || true)"
r2_bucket_name="$(grep -E '^R2_BUCKET_NAME=' "${ENV_FILE}" | tail -n 1 | cut -d'=' -f2- || true)"
r2_public_base_url="$(grep -E '^R2_PUBLIC_BASE_URL=' "${ENV_FILE}" | tail -n 1 | cut -d'=' -f2- || true)"

if [[ "${current_video_provider}" != "mock" ]]; then
  echo "Refusing to continue because VIDEO_PROVIDER is not mock." >&2
  exit 1
fi

if [[ "${current_storage_provider}" != "r2" ]]; then
  echo "Refusing to continue because STORAGE_PROVIDER is not r2." >&2
  exit 1
fi

if [[ -z "${runway_api_key}" ]]; then
  echo "RUNWAY_API_KEY is missing." >&2
  exit 1
fi

if [[ -z "${r2_account_id}" || -z "${r2_access_key_id}" || -z "${r2_secret_access_key}" || -z "${r2_bucket_name}" || -z "${r2_public_base_url}" ]]; then
  echo "R2 configuration is incomplete." >&2
  exit 1
fi

mkdir -p "${ENV_BACKUP_DIR}"
chmod 700 "${ENV_BACKUP_DIR}"
timestamp="$(date +%Y%m%d-%H%M%S)"
env_backup_path="${ENV_BACKUP_DIR}/story-engine-env-${timestamp}.env"
cp "${ENV_FILE}" "${env_backup_path}"
chmod 600 "${env_backup_path}"
echo "Backed up .env to ${env_backup_path}"

set_env_value() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" "${ENV_FILE}"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
  else
    printf '%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
  fi
}

set_env_value "VIDEO_PROVIDER" "runway"
echo "Updated VIDEO_PROVIDER=runway in ${ENV_FILE}"

echo "Restarting backend and celery_worker..."
docker compose "${COMPOSE_ARGS[@]}" up -d --build backend celery_worker

health_tmp="$(mktemp)"
cleanup() {
  rm -f "${health_tmp}"
}
trap cleanup EXIT

details_status=""
for _ in $(seq 1 12); do
  details_status="$(curl -k -sS -o "${health_tmp}" -w '%{http_code}' "${STAGING_URL}/health/details" || true)"
  if [[ "${details_status}" == "200" ]]; then
    break
  fi
  sleep 5
done

if [[ "${details_status}" != "200" ]]; then
  echo "health/details did not return 200 after enabling Runway." >&2
  echo "Run manual rollback: bash ${ROOT_DIR}/scripts/vps-safe-mock-mode.sh ${ROOT_DIR}" >&2
  exit 1
fi

mapfile -t health_lines < <("${PYTHON3_BIN}" - "${health_tmp}" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
checks = payload.get("checks", {})

def emit(name: str, value: str) -> None:
    print(f"{name}={value}")

emit("video_provider", str(payload.get("video_provider", "")).strip().lower())
emit("storage_provider", str(payload.get("storage_provider", "")).strip().lower())
emit("runway_mode_enabled", "true" if bool(payload.get("runway_mode_enabled", False)) else "false")
for name in ("database", "redis", "storage"):
    emit(f"{name}_status", str(checks.get(name, {}).get("status", "")).strip().lower())
PY
)

declare -A health_map=()
for line in "${health_lines[@]}"; do
  key="${line%%=*}"
  value="${line#*=}"
  health_map["${key}"]="${value}"
done

[[ "${health_map[video_provider]:-}" == "runway" ]] || {
  echo "health/details did not report video_provider=runway." >&2
  exit 1
}
[[ "${health_map[storage_provider]:-}" == "r2" ]] || {
  echo "health/details did not report storage_provider=r2." >&2
  exit 1
}
[[ "${health_map[runway_mode_enabled]:-}" == "true" ]] || {
  echo "health/details did not report runway_mode_enabled=true." >&2
  exit 1
}
[[ "${health_map[database_status]:-}" == "ok" ]] || {
  echo "health/details database check is not ok." >&2
  exit 1
}
[[ "${health_map[redis_status]:-}" == "ok" ]] || {
  echo "health/details redis check is not ok." >&2
  exit 1
}
[[ "${health_map[storage_status]:-}" == "ok" ]] || {
  echo "health/details storage check is not ok." >&2
  echo "Run manual rollback: bash ${ROOT_DIR}/scripts/vps-safe-mock-mode.sh ${ROOT_DIR}" >&2
  exit 1
}

echo "Runway mode verified in health/details."

if command -v systemd-run >/dev/null 2>&1; then
  systemd-run --on-active="${WINDOW_MINUTES}m" --unit=story-engine-return-to-mock /bin/bash "${ROOT_DIR}/scripts/vps-safe-mock-mode.sh" "${ROOT_DIR}" >/dev/null
  echo "Automatic rollback scheduled with systemd-run for ${WINDOW_MINUTES} minutes."
else
  echo "WARNING: systemd-run is not available. Automatic rollback was not scheduled."
  echo "Manual rollback command: bash ${ROOT_DIR}/scripts/vps-safe-mock-mode.sh ${ROOT_DIR}"
fi

echo
echo "Next steps:"
echo "1. Open ${STAGING_URL}"
echo "2. Generate exactly one test video"
echo "3. Review output, R2 assets, and the review page"
echo "4. Immediately run: bash ${ROOT_DIR}/scripts/vps-safe-mock-mode.sh ${ROOT_DIR}"
echo "5. Then run: bash ${ROOT_DIR}/scripts/vps-staging-release-check.sh ${ROOT_DIR}"
echo
echo "This script only enables Runway temporarily. It does not generate a video automatically."
