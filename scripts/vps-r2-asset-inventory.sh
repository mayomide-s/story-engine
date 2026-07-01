#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-/opt/story-engine}"

cd "${ROOT_DIR}"

docker compose --env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml exec -T backend \
  python - <<'PY'
from __future__ import annotations

from collections import defaultdict

import boto3
from botocore.exceptions import ClientError

from app.config import get_settings
from app.db.session import SessionLocal
from app.models import Asset


def human_size(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    unit = 0
    while size >= 1024 and unit < len(units) - 1:
        size /= 1024
        unit += 1
    return f"{size:.2f} {units[unit]}"


settings = get_settings()
client = boto3.client(
    "s3",
    endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
    aws_access_key_id=settings.r2_access_key_id,
    aws_secret_access_key=settings.r2_secret_access_key,
    region_name="auto",
)

bucket_name = settings.r2_bucket_name
prefixes = ("videos/", "thumbnails/")
summary: dict[str, dict[str, int]] = {prefix: {"count": 0, "size": 0} for prefix in prefixes}

paginator = client.get_paginator("list_objects_v2")
for prefix in prefixes:
    for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
        for obj in page.get("Contents", []):
            summary[prefix]["count"] += 1
            summary[prefix]["size"] += int(obj.get("Size", 0))

print(f"R2 bucket: {bucket_name}")
print(f"videos/: count={summary['videos/']['count']} total_size={human_size(summary['videos/']['size'])}")
print(f"thumbnails/: count={summary['thumbnails/']['count']} total_size={human_size(summary['thumbnails/']['size'])}")

missing_keys: list[str] = []
db_counts = defaultdict(int)

with SessionLocal() as db:
    assets = (
        db.query(Asset.storage_key, Asset.asset_type)
        .filter(Asset.storage_key.is_not(None))
        .all()
    )

for storage_key, asset_type in assets:
    if not storage_key:
        continue
    if storage_key.startswith("videos/") or storage_key.startswith("thumbnails/"):
        db_counts[str(asset_type)] += 1
        try:
            client.head_object(Bucket=bucket_name, Key=storage_key)
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                missing_keys.append(storage_key)
            else:
                print(f"Warning: could not verify key '{storage_key}': {error_code or exc.__class__.__name__}")

print(f"DB asset records checked: video_mp4={db_counts['video_mp4']} thumbnail={db_counts['thumbnail']}")
print(f"Missing R2 objects referenced by DB: {len(missing_keys)}")

if missing_keys:
    print("First missing keys:")
    for key in missing_keys[:20]:
        print(f"- {key}")
PY
