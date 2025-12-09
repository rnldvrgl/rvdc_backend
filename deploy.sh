#!/bin/bash
set -e
set -o pipefail

APP_NAME="rvdc_backend"
PROJECT_DIR="/srv/$APP_NAME"
DOCKER_COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
WEB_SERVICE="web"
HEALTHCHECK_URL="http://127.0.0.1:8000/health"

# Default branch: staging (override with BRANCH environment variable)
BRANCH="${BRANCH:-staging}"

cd "$PROJECT_DIR"

log() { echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"; }

log ">>> Pulling latest changes from Git branch '$BRANCH'..."
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

log ">>> Pre-deploy Django checks..."
$DOCKER_COMPOSE run --rm $WEB_SERVICE python manage.py check --deploy

log ">>> Building production containers..."
$DOCKER_COMPOSE build $WEB_SERVICE

log ">>> Applying migrations..."
$DOCKER_COMPOSE run --rm $WEB_SERVICE python manage.py migrate --noinput

log ">>> Collecting static files..."
$DOCKER_COMPOSE run --rm $WEB_SERVICE python manage.py collectstatic --noinput

log ">>> Creating default users..."
$DOCKER_COMPOSE run --rm $WEB_SERVICE python manage.py create_default_users

log ">>> Updating web container..."
$DOCKER_COMPOSE up -d --no-deps --build $WEB_SERVICE

log ">>> Checking health at $HEALTHCHECK_URL..."
if curl -fsS --max-time 5 "$HEALTHCHECK_URL" >/dev/null 2>&1; then
    log "Health check OK"
else
    log "ERROR: Health check failed. Inspect logs with: $DOCKER_COMPOSE logs $WEB_SERVICE"
fi

log ">>> Cleaning up dangling images..."
docker image prune -f

log "✅ Deployment complete!"
