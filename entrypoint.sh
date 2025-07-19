#!/bin/sh

echo ">>> Applying Django migrations..."
# Apply migrations
python manage.py migrate --noinput

echo ">>> Collecting static files..."
# Collect static files
python manage.py collectstatic --noinput

echo ">>> Creating default users..."
# Create default users
python manage.py create_default_users

# Run the passed command (e.g., gunicorn or dev server)
exec "$@"