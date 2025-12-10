#!/usr/bin/env bash
set -Eeuo pipefail

############################################
# CONFIG
############################################
APP_NAME="${APP_NAME:-rvdc_backend}"
PROJECT_DIR="${PROJECT_DIR:-/srv/$APP_NAME}"
FRONTEND_DIR="${FRONTEND_DIR:-/srv/rvdc}"
BRANCH="${BRANCH:-staging}"
WEB_SERVICE="${WEB_SERVICE:-web}"
FRONTEND_SERVICE="${FRONTEND_SERVICE:-rvdc}"
HEALTHCHECK_URL="${HEALTHCHECK_URL:-http://127.0.0.1:8000/health}"

# Compose commands for backend and frontend
BACKEND_COMPOSE="docker compose -f ${PROJECT_DIR}/docker-compose.yml -f ${PROJECT_DIR}/docker-compose.prod.yml"
FRONTEND_COMPOSE="docker compose -f ${FRONTEND_DIR}/docker-compose.yml"

timestamp() { date +'%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(timestamp)] $*"; }
err() { echo "[$(timestamp)] ERROR: $*" >&2; }

############################################
# PRECONDITIONS
############################################
log "Starting deployment for ${APP_NAME} (branch ${BRANCH})"

command -v docker >/dev/null 2>&1 || { err "Docker not found"; exit 1; }
[ -d "${PROJECT_DIR}" ] || { err "Backend project dir not found: ${PROJECT_DIR}"; exit 1; }
[ -d "${FRONTEND_DIR}" ] || { err "Frontend project dir not found: ${FRONTEND_DIR}"; exit 1; }

############################################
# BACKEND: Pull latest
############################################
log "Updating backend repository..."
cd "${PROJECT_DIR}"
git fetch origin "${BRANCH}"
git reset --hard "origin/${BRANCH}"
log "Backend at origin/${BRANCH}"

############################################
# FRONTEND: Pull latest
############################################
log "Updating frontend repository..."
cd "${FRONTEND_DIR}"
git fetch origin "${BRANCH}"
git reset --hard "origin/${BRANCH}"
log "Frontend at origin/${BRANCH}"

############################################
# BUILD BACKEND
############################################
log "Building backend Docker image..."
cd "${PROJECT_DIR}"
${BACKEND_COMPOSE} build --pull "${WEB_SERVICE}"

log "Running backend migrations..."
${BACKEND_COMPOSE} run --rm --no-deps "${WEB_SERVICE}" python manage.py migrate --noinput

log "Creating default users..."
${BACKEND_COMPOSE} run --rm --no-deps "${WEB_SERVICE}" python manage.py create_default_users

log "Collecting static files..."
${BACKEND_COMPOSE} run --rm --no-deps "${WEB_SERVICE}" python manage.py collectstatic --noinput

############################################
# BUILD FRONTEND
############################################
log "Building frontend Docker image..."
cd "${FRONTEND_DIR}"
${FRONTEND_COMPOSE} build "${FRONTEND_SERVICE}"

############################################
# DEPLOY: Start/Update services
############################################
log "Bringing up backend and frontend..."
cd "${PROJECT_DIR}"
${BACKEND_COMPOSE} up -d --no-deps --build "${WEB_SERVICE}"
cd "${FRONTEND_DIR}"
${FRONTEND_COMPOSE} up -d --no-deps --build "${FRONTEND_SERVICE}"

############################################
# HEALTHCHECK
############################################
log "Checking backend health at ${HEALTHCHECK_URL} ..."
if curl -fsS --max-time 5 "${HEALTHCHECK_URL}" >/dev/null 2>&1; then
    log "Backend health check OK"
else
    err "Backend health check failed! Inspect logs: ${BACKEND_COMPOSE} logs ${WEB_SERVICE}"
fi

############################################
# CLEANUP
############################################
log "Cleaning up dangling Docker images..."
docker image prune -f || log "Image prune failed (non-fatal)"

log "Deployment complete ✅"
