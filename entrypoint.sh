#!/bin/sh

# Apply migrations
python manage.py migrate --noinput

# Collect static files
python manage.py collectstatic --noinput

# Create default users
python manage.py create_default_users

# Run the passed command (e.g., gunicorn or dev server)
exec "$@"