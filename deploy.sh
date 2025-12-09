#!/usr/bin/env bash
set -Eeuo pipefail

############################################
# Config
############################################
APP_NAME="${APP_NAME:-rvdc_backend}"
PROJECT_DIR="${PROJECT_DIR:-/srv/$APP_NAME}"
BRANCH="${BRANCH:-master}"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml"
DOCKER_COMPOSE="docker compose ${COMPOSE_FILES}"
WEB_SERVICE="${WEB_SERVICE:-web}"
HEALTHCHECK_URL="${HEALTHCHECK_URL:-http://127.0.0.1:8000/health}"

timestamp() { date +'%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(timestamp)] $*"; }
err() { echo "[$(timestamp)] ERROR: $*" >&2; }

############################################
# Preconditions
############################################
log "Starting deploy for ${APP_NAME} (branch ${BRANCH})"

if ! command -v docker >/dev/null 2>&1; then
  err "Docker not found"
  exit 1
fi

if [ ! -d "${PROJECT_DIR}" ]; then
  err "Project dir not found: ${PROJECT_DIR}"
  exit 1
fi

cd "${PROJECT_DIR}"

############################################
# Pull latest
############################################
log "Fetching git updates..."
git fetch origin "${BRANCH}"
git reset --hard "origin/${BRANCH}"
log "Checked out origin/${BRANCH}"

############################################
# Build
############################################
log "Building production image(s)..."
${DOCKER_COMPOSE} build --pull "${WEB_SERVICE}"
log "Build complete"

############################################
# Run migrations and collectstatic using the built image
############################################
log "Running migrations..."
${DOCKER_COMPOSE} run --rm --no-deps "${WEB_SERVICE}" python manage.py migrate --noinput
log "Migrations applied"

log "Collecting static files..."
${DOCKER_COMPOSE} run --rm --no-deps "${WEB_SERVICE}" python manage.py collectstatic --noinput
log "Static collected"

############################################
# Deploy: start / update the service (no rebuild)
############################################
log "Bringing up web service..."
${DOCKER_COMPOSE} up -d --no-deps --no-build "${WEB_SERVICE}"
log "Service up"

############################################
# Health check
############################################
log "Checking health at ${HEALTHCHECK_URL} ..."
if curl -fsS --max-time 5 "${HEALTHCHECK_URL}" >/dev/null 2>&1; then
  log "Health check OK"
else
  err "Health check failed. You should inspect logs: docker compose -f docker-compose.yml -f docker-compose.prod.yml logs ${WEB_SERVICE}"
fi

############################################
# Cleanup
############################################
log "Cleaning up dangling images..."
docker image prune -f || log "image prune failed (non-fatal)"

log "Deployment finished"
