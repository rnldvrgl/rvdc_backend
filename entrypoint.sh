#!/bin/sh

set -e

echo ">>> Waiting for PostgreSQL to be ready..."
DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-5432}

# Wait for DB to accept TCP connections
until nc -z "$DB_HOST" "$DB_PORT"; do
  echo "Postgres is unavailable at $DB_HOST:$DB_PORT - sleeping"
  sleep 1
done
echo ">>> PostgreSQL is up!"

echo ">>> Starting: $@"
exec "$@"
