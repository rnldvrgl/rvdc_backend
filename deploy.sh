#!/usr/bin/env bash
set -Eeuo pipefail

timestamp() { date +'%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(timestamp)] $*"; }
err() { echo "[$(timestamp)] ERROR: $*" >&2; }

APP_NAME="${APP_NAME:-rvdc_backend}"
PROJECT_DIR="${PROJECT_DIR:-/srv/$APP_NAME}"
FRONTEND_DIR="${FRONTEND_DIR:-/srv/rvdc}"
BRANCH="${BRANCH:-staging}"
WEB_SERVICE="${WEB_SERVICE:-api}"
FRONTEND_SERVICE="${FRONTEND_SERVICE:-rvdc}"
ENV_FILE="${ENV_FILE:-${PROJECT_DIR}/.env.production}"

[ -f "${ENV_FILE}" ] || { err "Env file not found: ${ENV_FILE}"; exit 1; }

log "Starting deployment for ${APP_NAME} (branch ${BRANCH})"

command -v docker >/dev/null 2>&1 || { err "Docker not found"; exit 1; }
[ -d "${PROJECT_DIR}" ] || { err "Backend project dir not found: ${PROJECT_DIR}"; exit 1; }
[ -d "${FRONTEND_DIR}" ] || { err "Frontend project dir not found: ${FRONTEND_DIR}"; exit 1; }

# ---------------- BACKEND ----------------
log "Updating backend repository..."
cd "${PROJECT_DIR}"
git fetch origin "${BRANCH}"
git reset --hard "origin/${BRANCH}"
log "Backend at origin/${BRANCH}"

DOCKER_COMPOSE_BACKEND="docker compose \
  --env-file ${ENV_FILE} \
  -f docker-compose.yml \
  -f docker-compose.prod.yml"

log "Ensuring database is running..."
${DOCKER_COMPOSE_BACKEND} up -d db

log "Building backend Docker image..."
${DOCKER_COMPOSE_BACKEND} build --pull "${WEB_SERVICE}"

log "Starting backend service..."
${DOCKER_COMPOSE_BACKEND} up -d "${WEB_SERVICE}"

log "Running migrations..."
${DOCKER_COMPOSE_BACKEND} exec -T "${WEB_SERVICE}" python manage.py migrate --noinput

log "Creating default users..."
${DOCKER_COMPOSE_BACKEND} exec -T "${WEB_SERVICE}" python manage.py create_default_users

log "Collecting static files..."
${DOCKER_COMPOSE_BACKEND} exec -T "${WEB_SERVICE}" python manage.py collectstatic --noinput


# ---------------- FRONTEND ----------------
log "Updating frontend repository..."
cd "${FRONTEND_DIR}"
git fetch origin "${BRANCH}"
git reset --hard "origin/${BRANCH}"
log "Frontend at origin/${BRANCH}"

DOCKER_COMPOSE_FRONTEND="docker compose -f docker-compose.yml"

log "Building frontend Docker image..."
${DOCKER_COMPOSE_FRONTEND} build "${FRONTEND_SERVICE}"

log "Bringing up frontend service..."
${DOCKER_COMPOSE_FRONTEND} up -d --build "${FRONTEND_SERVICE}"

# ---------------- CLEANUP ----------------
log "Cleaning up dangling Docker images..."
docker image prune -f || log "Image prune failed (non-fatal)"

log "Deployment complete ✅"
