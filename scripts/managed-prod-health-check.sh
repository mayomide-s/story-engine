#!/bin/sh
set -eu

BASE_URL="${1:-https://api.storyengine.soremekun.org}"

curl --fail --silent --show-error "$BASE_URL/health" >/dev/null
curl --fail --silent --show-error "$BASE_URL/health/details" >/dev/null

echo "Managed production health checks passed for $BASE_URL"
