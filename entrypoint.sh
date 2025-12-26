#!/usr/bin/env sh
set -e

# ---------- Defaults ----------
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-rvdc_owner}"
DB_NAME="${DB_NAME:-rvdc_db}"
DB_RETRIES="${DB_RETRIES:-30}"
DB_WAIT_SLEEP="${DB_WAIT_SLEEP:-1}"

GUNICORN_WORKERS="${GUNICORN_WORKERS:-3}"

# ---------- Wait for Postgres ----------
echo ">>> Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT} (db=${DB_NAME}, user=${DB_USER})"
i=1
while ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; do
  if [ "$i" -ge "$DB_RETRIES" ]; then
    echo ">>> ERROR: PostgreSQL did not become ready after ${DB_RETRIES} attempts"
    exit 1
  fi
  echo ">>> PostgreSQL not ready (attempt ${i}/${DB_RETRIES}) — sleeping ${DB_WAIT_SLEEP}s"
  i=$((i + 1))
  sleep "$DB_WAIT_SLEEP"
done
echo ">>> PostgreSQL is ready"

# ---------- Start application ----------
echo ">>> Starting application with ${GUNICORN_WORKERS} Gunicorn workers"
exec "$@" --workers "$GUNICORN_WORKERS"

