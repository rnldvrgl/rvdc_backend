#!/usr/bin/env bash
set -Eeuo pipefail

timestamp() { date +'%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(timestamp)] $*"; }
err() { echo "[$(timestamp)] ERROR: $*" >&2; }

APP_NAME="${APP_NAME:-rvdc_backend}"
PROJECT_DIR="${PROJECT_DIR:-/srv/$APP_NAME}"
FRONTEND_DIR="${FRONTEND_DIR:-/srv/rvdc}"
BRANCH="${BRANCH:-master}"
WEB_SERVICE="${WEB_SERVICE:-api}"
FRONTEND_SERVICE="${FRONTEND_SERVICE:-rvdc-frontend}"
ENV_FILE="${ENV_FILE:-${PROJECT_DIR}/.env.production}"

[ -f "${ENV_FILE}" ] || { err "Env file not found: ${ENV_FILE}"; exit 1; }

log "Starting deployment for ${APP_NAME} (branch ${BRANCH})"

command -v docker >/dev/null 2>&1 || { err "Docker not found"; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { err "docker-compose not found"; exit 1; }
[ -d "${PROJECT_DIR}" ] || { err "Backend project dir not found: ${PROJECT_DIR}"; exit 1; }
[ -d "${FRONTEND_DIR}" ] || { err "Frontend project dir not found: ${FRONTEND_DIR}"; exit 1; }

# ---------------- BACKEND ----------------
log "Updating backend repository..."
cd "${PROJECT_DIR}" || { err "Failed to cd into ${PROJECT_DIR}"; exit 1; }
git fetch origin "${BRANCH}"
git reset --hard "origin/${BRANCH}"
log "Backend at origin/${BRANCH}"

DOCKER_COMPOSE="docker-compose --env-file ${ENV_FILE} -f docker-compose.yml -f docker-compose.prod.yml"

log "Ensuring database is running..."
${DOCKER_COMPOSE} up -d db || { err "Failed to start database"; exit 1; }

log "Building backend Docker image..."
${DOCKER_COMPOSE} build --pull "${WEB_SERVICE}" || { err "Failed to build backend image"; exit 1; }

log "Starting backend service..."
${DOCKER_COMPOSE} up -d "${WEB_SERVICE}" || { err "Failed to start backend service"; exit 1; }

log "Running migrations..."
${DOCKER_COMPOSE} exec -T "${WEB_SERVICE}" python manage.py migrate --noinput || { err "Migrations failed"; exit 1; }

log "Creating default users..."
${DOCKER_COMPOSE} exec -T "${WEB_SERVICE}" python manage.py create_default_users || log "create_default_users failed (non-fatal)"

log "Collecting static files..."
${DOCKER_COMPOSE} exec -T "${WEB_SERVICE}" python manage.py collectstatic --noinput || { err "Collectstatic failed"; exit 1; }

# ---------------- FRONTEND ----------------
log "Updating frontend repository..."
cd "${FRONTEND_DIR}" || { err "Failed to cd into ${FRONTEND_DIR}"; exit 1; }
git fetch origin "${BRANCH}"
git reset --hard "origin/${BRANCH}"
log "Frontend at origin/${BRANCH}"

log "Installing frontend deps..."
rm -rf node_modules package-lock.json
npm install || { err "npm install failed"; exit 1; }

log "Building frontend..."
npm run build || { err "Frontend build failed"; exit 1; }

log "Restarting frontend (PM2)..."
pm2 restart "${FRONTEND_SERVICE}" || pm2 start ecosystem.config.js || log "PM2 start failed (non-fatal)"

# ---------------- CLEANUP ----------------
log "Cleaning up dangling Docker images..."
docker image prune -f || log "Image prune failed (non-fatal)"

log "Deployment complete ✅"
