#!/bin/sh
set -e

echo "Waiting for database readiness..."
python - <<'PY'
import os
import sys
import time

import psycopg

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    print("DATABASE_URL is not set.", file=sys.stderr)
    sys.exit(1)

psycopg_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
deadline = time.time() + 60
last_error = None

while time.time() < deadline:
    try:
        with psycopg.connect(psycopg_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        print("Database is ready.")
        sys.exit(0)
    except Exception as exc:
        last_error = exc
        print(f"Database not ready yet: {exc}", file=sys.stderr)
        time.sleep(2)

print("Database did not become ready within 60 seconds.", file=sys.stderr)
if last_error is not None:
    print(f"Last database error: {last_error}", file=sys.stderr)
sys.exit(1)
PY

echo "Running Alembic migrations..."
alembic upgrade head
echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
