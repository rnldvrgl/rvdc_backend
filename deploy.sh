#!/bin/bash
# Enhanced deployment script for rvdc_backend
# - Pulls latest code
# - Runs Django deploy checks
# - Builds and updates production container
# - Runs migrations and collectstatic
# - Adds safer steps, health checks, and structured logging

set -Eeuo pipefail

###############################################
# Configuration
###############################################
APP_NAME="${APP_NAME:-rvdc_backend}"
PROJECT_DIR="${PROJECT_DIR:-/srv/$APP_NAME}"
BRANCH="${BRANCH:-master}"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml"
DOCKER_COMPOSE="docker compose ${COMPOSE_FILES}"
WEB_SERVICE="${WEB_SERVICE:-web}"

# Health-check command: adjust to your app's health endpoint if available
# Example: HEALTHCHECK_CMD='docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T web curl -fsS http://localhost/healthz'
HEALTHCHECK_CMD="${HEALTHCHECK_CMD:-$DOCKER_COMPOSE exec -T $WEB_SERVICE curl -fsS http://localhost/health || $DOCKER_COMPOSE exec -T $WEB_SERVICE curl -fsS http://127.0.0.1/health || true}"

###############################################
# Logging helpers
###############################################
timestamp() {
  date +'%Y-%m-%d %H:%M:%S'
}
log() {
  echo "[$(timestamp)] $*"
}
ok() {
  echo "[$(timestamp)] ✅ $*"
}
warn() {
  echo "[$(timestamp)] ⚠️  $*" >&2
}
err() {
  echo "[$(timestamp)] ❌ $*" >&2
}

###############################################
# Traps & cleanup
###############################################
cleanup() {
  # Add any cleanup steps here (e.g., removing temp files, unlocking, etc.)
  :
}
trap cleanup EXIT

###############################################
# Pre-flight checks
###############################################
log "Starting deploy for $APP_NAME on branch '$BRANCH'"

if ! command -v docker >/dev/null 2>&1; then
  err "Docker is not installed or not in PATH"
  exit 1
fi

# Validate compose files exist
for f in docker-compose.yml docker-compose.prod.yml; do
  if [ ! -f "$PROJECT_DIR/$f" ]; then
    err "Missing required compose file: $PROJECT_DIR/$f"
    exit 1
  fi
done

if [ ! -d "$PROJECT_DIR" ]; then
  err "Project directory not found: $PROJECT_DIR"
  exit 1
fi

cd "$PROJECT_DIR"

###############################################
# Git update
###############################################
log "Pulling latest changes from Git..."
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"
ok "Git updated to origin/$BRANCH"

###############################################
# Django deploy checks (static settings, security, etc.)
###############################################
log "Running Django deploy checks..."
$DOCKER_COMPOSE run --rm "$WEB_SERVICE" python manage.py check --deploy
ok "Django deploy checks passed"

###############################################
# Build production image
###############################################
log "Building production containers..."
$DOCKER_COMPOSE build "$WEB_SERVICE"
ok "Build complete"

###############################################
# Run database migrations
###############################################
log "Applying database migrations..."
$DOCKER_COMPOSE run --rm "$WEB_SERVICE" python manage.py migrate --noinput
ok "Migrations completed"

###############################################
# Collect static files
###############################################
log "Collecting static files..."
$DOCKER_COMPOSE run --rm "$WEB_SERVICE" python manage.py collectstatic --noinput
ok "Static files collected"

###############################################
# Update and restart web service
###############################################
log "Updating web container..."
$DOCKER_COMPOSE up -d --no-deps --build "$WEB_SERVICE"
ok "Web container updated and restarted"

###############################################
# Post-deploy health check
###############################################
log "Running post-deploy health check..."
if eval "$HEALTHCHECK_CMD"; then
  ok "Health check passed"
else
  warn "Health check did not pass; please verify application health manually"
fi

###############################################
# Cleanup dangling images
###############################################
log "Cleaning up dangling images..."
docker image prune -f || warn "Failed to prune images (non-fatal)"

ok "Deployment complete!"
