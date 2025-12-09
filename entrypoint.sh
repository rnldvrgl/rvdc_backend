#!/bin/sh
set -e

: "${DB_HOST:=db}"
: "${DB_PORT:=5432}"
: "${DB_USER:=rvdc_owner}"
: "${DB_NAME:=rvdc_db}"
: "${DB_RETRIES:=30}"
: "${DB_WAIT_SLEEP:=1}"

echo ">>> Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT} ..."

i=0
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; do
  i=$((i+1))
  if [ "$i" -ge "$DB_RETRIES" ]; then
    echo ">>> ERROR: Postgres did not become ready in time (${DB_RETRIES} attempts)."
    exit 1
  fi
  echo "Postgres unavailable - sleeping ${DB_WAIT_SLEEP}s (attempt ${i}/${DB_RETRIES})"
  sleep "$DB_WAIT_SLEEP"
done

echo ">>> PostgreSQL is up!"

# execute the container CMD
echo ">>> Executing: $@"
exec "$@"
