#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-/opt/story-engine}"
STAGING_URL="${STAGING_URL:-https://story.soremekun.org}"
BACKUP_DIR="${BACKUP_DIR:-/root/story-engine-backups/db}"
COMPOSE_ARGS=(--env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml)
SERVICES=(backend celery_worker frontend postgres redis)
DB_BACKUP_TIMER="story-engine-db-backup.timer"
R2_TIMER="story-engine-r2-inventory.timer"
R2_INVENTORY_SCRIPT="scripts/vps-r2-asset-inventory.sh"
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

echo "Story Engine staging release checklist"
echo "Root: ${ROOT_DIR}"
echo "URL: ${STAGING_URL}"
echo

if [[ -n "${PYTHON3_BIN}" ]]; then
  pass "python3 detected at ${PYTHON3_BIN}"
else
  fail "python3 is required for health/details parsing"
fi

current_commit="$(git rev-parse --short HEAD 2>/dev/null || true)"
if [[ -n "${current_commit}" ]]; then
  pass "Git commit ${current_commit}"
else
  warn "Unable to determine current Git commit"
fi

latest_tag="$(git describe --tags --abbrev=0 2>/dev/null || true)"
if [[ -n "${latest_tag}" ]]; then
  pass "Latest Git tag ${latest_tag}"
else
  warn "No Git tag found from current checkout"
fi

git_status_output="$(git status --short 2>/dev/null || true)"
if [[ -z "${git_status_output}" ]]; then
  pass "Git working tree clean"
else
  warn "Git working tree has local changes"
  printf '%s\n' "${git_status_output}"
fi

compose_ps_output="$(docker compose "${COMPOSE_ARGS[@]}" ps 2>&1 || true)"
if [[ "${compose_ps_output}" == *"Name"* || "${compose_ps_output}" == *"SERVICE"* ]]; then
  pass "Docker compose status available"
else
  warn "Unable to read docker compose service status"
fi
printf '%s\n' "${compose_ps_output}"

for service in "${SERVICES[@]}"; do
  if [[ "${compose_ps_output}" == *"${service}"* ]]; then
    pass "Compose service listed: ${service}"
  else
    warn "Compose service missing from ps output: ${service}"
  fi
done

health_status="$(curl -k -sS -o /tmp/story-engine-health.out -w '%{http_code}' "${STAGING_URL}/health" || true)"
if [[ "${health_status}" == "200" ]]; then
  pass "Public /health returned 200"
else
  fail "Public /health returned ${health_status:-request_failed}"
fi

details_status="$(curl -k -sS -o /tmp/story-engine-health-details.json -w '%{http_code}' "${STAGING_URL}/health/details" || true)"
if [[ "${details_status}" == "200" ]]; then
  pass "Public /health/details returned 200"
else
  fail "Public /health/details returned ${details_status:-request_failed}"
fi

if [[ "${details_status}" == "200" ]]; then
  if [[ -z "${PYTHON3_BIN}" ]]; then
    fail "Skipping health/details parsing because python3 is unavailable"
  else
    set +e
    mapfile -t health_lines < <("${PYTHON3_BIN}" - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

payload = json.loads(Path("/tmp/story-engine-health-details.json").read_text(encoding="utf-8"))

def line(name: str, value: str) -> None:
    print(f"{name}={value}")

line("video_provider", str(payload.get("video_provider", "")).strip().lower())
line("storage_provider", str(payload.get("storage_provider", "")).strip().lower())
line("runway_mode_enabled", "true" if bool(payload.get("runway_mode_enabled", False)) else "false")
checks = payload.get("checks", {})
for name in ("database", "redis", "storage"):
    status = checks.get(name, {}).get("status", "")
    line(f"{name}_status", str(status).strip().lower())
PY
)
    parser_status=$?
    set -e
    if [[ ${parser_status} -ne 0 || ${#health_lines[@]} -eq 0 ]]; then
      fail "Could not parse /health/details JSON with python3"
    else
      declare -A health_map=()
      for line in "${health_lines[@]}"; do
        key="${line%%=*}"
        value="${line#*=}"
        health_map["${key}"]="${value}"
      done

      [[ "${health_map[video_provider]:-}" == "mock" ]] \
        && pass "health/details video_provider is mock" \
        || fail "health/details video_provider is ${health_map[video_provider]:-unknown}"

      [[ "${health_map[storage_provider]:-}" == "r2" ]] \
        && pass "health/details storage_provider is r2" \
        || fail "health/details storage_provider is ${health_map[storage_provider]:-unknown}"

      [[ "${health_map[runway_mode_enabled]:-}" == "false" ]] \
        && pass "health/details runway_mode_enabled is false" \
        || fail "health/details runway_mode_enabled is ${health_map[runway_mode_enabled]:-unknown}"

      [[ "${health_map[database_status]:-}" == "ok" ]] \
        && pass "health/details database status ok" \
        || fail "health/details database status is ${health_map[database_status]:-unknown}"

      [[ "${health_map[redis_status]:-}" == "ok" ]] \
        && pass "health/details redis status ok" \
        || fail "health/details redis status is ${health_map[redis_status]:-unknown}"

      [[ "${health_map[storage_status]:-}" == "ok" ]] \
        && pass "health/details storage status ok" \
        || fail "health/details storage status is ${health_map[storage_status]:-unknown}"
    fi
  fi
fi

timers_output="$(systemctl list-timers --all 2>&1 || true)"
for timer in "${DB_BACKUP_TIMER}" "${R2_TIMER}"; do
  if [[ "${timers_output}" == *"${timer}"* ]]; then
    pass "Timer listed: ${timer}"
  else
    warn "Timer not listed: ${timer}"
  fi
done

for timer in "${DB_BACKUP_TIMER}" "${R2_TIMER}"; do
  timer_enabled="$(systemctl is-enabled "${timer}" 2>/dev/null || true)"
  if [[ "${timer_enabled}" == "enabled" ]]; then
    pass "Timer enabled: ${timer}"
  else
    warn "Timer not enabled: ${timer} (${timer_enabled:-unknown})"
  fi
done

latest_backup="$(find "${BACKUP_DIR}" -maxdepth 1 -type f -name '*.sql.gz' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n 1 | cut -d' ' -f2- || true)"
if [[ -n "${latest_backup}" && -f "${latest_backup}" ]]; then
  backup_size="$(du -h "${latest_backup}" | awk '{print $1}')"
  pass "Latest DB backup found: ${latest_backup} (${backup_size})"
else
  warn "No DB backup found under ${BACKUP_DIR}"
fi

if [[ -f "${R2_INVENTORY_SCRIPT}" ]]; then
  set +e
  inventory_output="$(bash "${R2_INVENTORY_SCRIPT}" "${ROOT_DIR}" 2>&1)"
  inventory_status=$?
  set -e
  if [[ ${inventory_status} -eq 0 && "${inventory_output}" == *"Missing R2 objects referenced by DB: 0"* ]]; then
    pass "R2 inventory script ran successfully with zero missing DB-referenced objects"
  else
    warn "R2 inventory check did not reach a clean zero-missing result"
  fi
else
  warn "R2 inventory script not found at ${R2_INVENTORY_SCRIPT}"
fi

ufw_status_output="$(ufw status 2>&1 || true)"
if [[ "${ufw_status_output}" == Status:\ active* ]]; then
  pass "UFW is active"
else
  fail "UFW is not active"
fi

ufw_numbered_output="$(ufw status numbered 2>&1 || true)"
if [[ "${ufw_numbered_output}" == *"Nginx Full"* || ( "${ufw_numbered_output}" == *"80/tcp"* && "${ufw_numbered_output}" == *"443/tcp"* ) ]]; then
  pass "UFW allows expected web ports"
else
  warn "UFW rules do not clearly show web access via Nginx Full or 80/443"
fi

if [[ "${ufw_numbered_output}" == *"OpenSSH"* || "${ufw_numbered_output}" == *"22/tcp"* ]]; then
  pass "UFW allows SSH access"
else
  warn "UFW rules do not clearly show SSH access via OpenSSH or 22/tcp"
fi

fail2ban_status="$(fail2ban-client status 2>&1 || true)"
if [[ "${fail2ban_status}" == *"Status for the jail:"* || "${fail2ban_status}" == *"Jail list:"* ]]; then
  pass "Fail2ban is active"
else
  fail "Fail2ban is not active"
fi

fail2ban_sshd="$(fail2ban-client status sshd 2>&1 || true)"
if [[ "${fail2ban_sshd}" == *"Status for the jail: sshd"* ]]; then
  pass "Fail2ban sshd jail exists"
else
  fail "Fail2ban sshd jail missing"
fi

sshd_output="$(sshd -T 2>/dev/null | grep -Ei 'passwordauthentication|kbdinteractiveauthentication|permitrootlogin|pubkeyauthentication' || true)"
[[ "${sshd_output}" == *"passwordauthentication no"* ]] \
  && pass "SSH password authentication disabled" \
  || fail "SSH passwordauthentication is not set to no"

[[ "${sshd_output}" == *"kbdinteractiveauthentication no"* ]] \
  && pass "SSH keyboard-interactive authentication disabled" \
  || fail "SSH kbdinteractiveauthentication is not set to no"

[[ "${sshd_output}" == *"pubkeyauthentication yes"* ]] \
  && pass "SSH public key authentication enabled" \
  || fail "SSH pubkeyauthentication is not set to yes"

if [[ "${sshd_output}" == *"permitrootlogin without-password"* || "${sshd_output}" == *"permitrootlogin prohibit-password"* ]]; then
  pass "SSH root login restricted to keys"
else
  fail "SSH permitrootlogin is not without-password/prohibit-password"
fi

ports_output="$(ss -tulpn 2>/dev/null | grep -E ':(22|80|443|8000|8001|5174|5432|6379)\b' || true)"
printf '%s\n' "${ports_output}"

if [[ "${ports_output}" == *"0.0.0.0:22"* || "${ports_output}" == *"[::]:22"* ]]; then
  pass "SSH port 22 is publicly reachable as expected"
else
  warn "SSH port 22 not observed as a public listener"
fi

if [[ "${ports_output}" == *"0.0.0.0:80"* || "${ports_output}" == *"[::]:80"* ]]; then
  pass "HTTP port 80 is publicly reachable as expected"
else
  warn "HTTP port 80 not observed as a public listener"
fi

if [[ "${ports_output}" == *"0.0.0.0:443"* || "${ports_output}" == *"[::]:443"* ]]; then
  pass "HTTPS port 443 is publicly reachable as expected"
else
  warn "HTTPS port 443 not observed as a public listener"
fi

if [[ "${ports_output}" == *"0.0.0.0:8001"* || "${ports_output}" == *"[::]:8001"* ]]; then
  fail "Backend port 8001 is publicly exposed"
else
  pass "Backend port 8001 is not publicly exposed"
fi

if [[ "${ports_output}" == *"0.0.0.0:5174"* || "${ports_output}" == *"[::]:5174"* ]]; then
  fail "Frontend port 5174 is publicly exposed"
else
  pass "Frontend port 5174 is not publicly exposed"
fi

if [[ "${ports_output}" == *"0.0.0.0:8000"* || "${ports_output}" == *"[::]:8000"* ]]; then
  fail "Backend container port 8000 is publicly exposed"
else
  pass "Backend container port 8000 is not publicly exposed"
fi

if [[ "${ports_output}" == *"0.0.0.0:5432"* || "${ports_output}" == *"[::]:5432"* ]]; then
  fail "Postgres port 5432 is publicly exposed"
else
  pass "Postgres port 5432 is not publicly exposed"
fi

if [[ "${ports_output}" == *"0.0.0.0:6379"* || "${ports_output}" == *"[::]:6379"* ]]; then
  fail "Redis port 6379 is publicly exposed"
else
  pass "Redis port 6379 is not publicly exposed"
fi

if [[ "${ports_output}" == *"127.0.0.1:8001"* ]]; then
  pass "Backend port 8001 bound to localhost"
else
  warn "Backend port 8001 not observed on 127.0.0.1"
fi

if [[ "${ports_output}" == *"127.0.0.1:5174"* ]]; then
  pass "Frontend port 5174 bound to localhost"
else
  warn "Frontend port 5174 not observed on 127.0.0.1"
fi

echo
if (( critical_failures == 0 )); then
  echo "STAGING CHECK PASSED"
  if (( warning_count > 0 )); then
    echo "Warnings: ${warning_count}"
  fi
  exit 0
fi

echo "STAGING CHECK FAILED"
echo "Critical failures: ${critical_failures}"
if (( warning_count > 0 )); then
  echo "Warnings: ${warning_count}"
fi
exit 1
