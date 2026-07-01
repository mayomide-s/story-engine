#!/usr/bin/env bash
set -euo pipefail

STAGING_URL="${STAGING_URL:-https://story.soremekun.org}"

echo "Checking ${STAGING_URL}/health"
curl -i "${STAGING_URL}/health"
echo
echo "Checking ${STAGING_URL}/health/details"
curl -i "${STAGING_URL}/health/details"
echo
echo "Checking local frontend headers on 127.0.0.1:5174"
curl -I "http://127.0.0.1:5174/"

