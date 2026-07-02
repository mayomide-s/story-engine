#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-/opt/story-engine}"
STAGING_URL="${STAGING_URL:-https://story.soremekun.org}"
DEMO_VIDEO_KEY="videos/30ea2e8e-780a-471b-b85e-80ff8d84fe51.mp4"
DEMO_THUMBNAIL_KEY="thumbnails/30ea2e8e-780a-471b-b85e-80ff8d84fe51.jpg"
PYTHON3_BIN="$(command -v python3 || true)"

critical_failures=0
warning_count=0

pass() {
  printf 'PASS %s\n' "$1"
}

warn() {
  warning_count=$((warning_count + 1))
  printf 'WARN %s\n' "$1"
}

fail() {
  critical_failures=$((critical_failures + 1))
  printf 'FAIL %s\n' "$1"
}

cd "${ROOT_DIR}"

echo "Story Engine demo readiness check"
echo "Root: ${ROOT_DIR}"
echo "URL: ${STAGING_URL}"
echo

if [[ -z "${PYTHON3_BIN}" ]]; then
  fail "python3 is required for demo readiness checks"
else
  pass "python3 detected at ${PYTHON3_BIN}"
fi

echo "Running staging release checklist first..."
if bash scripts/vps-staging-release-check.sh "${ROOT_DIR}"; then
  pass "Staging release checklist passed"
else
  fail "Staging release checklist failed"
fi

details_tmp="$(mktemp)"
cleanup() {
  rm -f "${details_tmp}"
}
trap cleanup EXIT

details_status="$(curl -k -sS -o "${details_tmp}" -w '%{http_code}' "${STAGING_URL}/health/details" || true)"
if [[ "${details_status}" == "200" ]]; then
  pass "health/details returned 200"
else
  fail "health/details returned ${details_status:-request_failed}"
fi

if [[ "${details_status}" == "200" && -n "${PYTHON3_BIN}" ]]; then
  set +e
  mapfile -t health_lines < <("${PYTHON3_BIN}" - "${details_tmp}" <<'PY'
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
  parser_status=$?
  set -e
  if [[ ${parser_status} -ne 0 || ${#health_lines[@]} -eq 0 ]]; then
    fail "Could not parse health/details"
  else
    declare -A health_map=()
    for line in "${health_lines[@]}"; do
      key="${line%%=*}"
      value="${line#*=}"
      health_map["${key}"]="${value}"
    done

    [[ "${health_map[video_provider]:-}" == "mock" ]] \
      && pass "Current environment remains in mock mode" \
      || fail "Current environment is not in mock mode"

    [[ "${health_map[storage_provider]:-}" == "r2" ]] \
      && pass "Current environment uses R2 storage" \
      || fail "Current environment is not using R2 storage"

    [[ "${health_map[runway_mode_enabled]:-}" == "false" ]] \
      && pass "Runway is disabled for demo safety" \
      || fail "Runway is currently enabled"

    [[ "${health_map[database_status]:-}" == "ok" ]] \
      && pass "Database check is ok" \
      || fail "Database check is not ok"

    [[ "${health_map[redis_status]:-}" == "ok" ]] \
      && pass "Redis check is ok" \
      || fail "Redis check is not ok"

    [[ "${health_map[storage_status]:-}" == "ok" ]] \
      && pass "Storage check is ok" \
      || fail "Storage check is not ok"
  fi
fi

if [[ -f "scripts/vps-r2-asset-inventory.sh" ]]; then
  set +e
  inventory_output="$(bash scripts/vps-r2-asset-inventory.sh "${ROOT_DIR}" 2>&1)"
  inventory_status=$?
  set -e
  if [[ ${inventory_status} -eq 0 && "${inventory_output}" == *"Missing R2 objects referenced by DB: 0"* ]]; then
    pass "R2 inventory confirmed zero missing DB-referenced objects"
  else
    fail "R2 inventory did not confirm a clean zero-missing result"
  fi
else
  fail "Missing R2 inventory script"
fi

set +e
r2_object_check_output="$(
  docker compose --env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml exec -T backend \
    python - "${DEMO_VIDEO_KEY}" "${DEMO_THUMBNAIL_KEY}" <<'PY' 2>&1
from __future__ import annotations

import sys

import boto3
from botocore.exceptions import ClientError

from app.config import get_settings

settings = get_settings()
client = boto3.client(
    "s3",
    endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
    aws_access_key_id=settings.r2_access_key_id,
    aws_secret_access_key=settings.r2_secret_access_key,
    region_name="auto",
)

bucket_name = settings.r2_bucket_name
keys = sys.argv[1:]
missing = []

for key in keys:
    try:
        client.head_object(Bucket=bucket_name, Key=key)
        print(f"FOUND {key}")
    except ClientError:
        missing.append(key)
        print(f"MISSING {key}")

if missing:
    raise SystemExit(1)
PY
)"
r2_object_status=$?
set -e

if [[ ${r2_object_status} -eq 0 && "${r2_object_check_output}" == *"FOUND ${DEMO_VIDEO_KEY}"* ]]; then
  pass "Golden demo video exists in R2"
else
  fail "Golden demo video is missing from R2"
fi

if [[ ${r2_object_status} -eq 0 && "${r2_object_check_output}" == *"FOUND ${DEMO_THUMBNAIL_KEY}"* ]]; then
  pass "Golden demo thumbnail exists in R2"
else
  fail "Golden demo thumbnail is missing from R2"
fi

echo
if (( critical_failures == 0 )); then
  echo "DEMO READINESS PASSED"
  if (( warning_count > 0 )); then
    echo "Warnings: ${warning_count}"
  fi
  exit 0
fi

echo "DEMO READINESS FAILED"
echo "Critical failures: ${critical_failures}"
if (( warning_count > 0 )); then
  echo "Warnings: ${warning_count}"
fi
exit 1
