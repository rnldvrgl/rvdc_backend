#!/bin/sh

set -e

echo ">>> Waiting for PostgreSQL to be ready..."
DB_HOST=${DB_HOST:-db}
until nc -z "$DB_HOST" 5432; do
  echo "Postgres is unavailable - sleeping"
  sleep 1
done
echo ">>> PostgreSQL is up!"

echo ">>> Applying Django migrations..."
python manage.py migrate --noinput

echo ">>> Collecting static files..."
python manage.py collectstatic --noinput

echo ">>> Starting: $@"
exec "$@"
