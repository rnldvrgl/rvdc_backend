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
[ -d "${PROJECT_DIR}" ] || { err "Backend project dir not found: ${PROJECT_DIR}"; exit 1; }
[ -d "${FRONTEND_DIR}" ] || { err "Frontend project dir not found: ${FRONTEND_DIR}"; exit 1; }

# ---------------- BACKEND ----------------
log "Updating backend repository..."
cd "${PROJECT_DIR}"
git fetch origin "${BRANCH}"
git reset --hard "origin/${BRANCH}"
log "Backend at origin/${BRANCH}"

log "Ensuring database is running..."
docker compose --env-file "${ENV_FILE}" -f docker-compose.yml -f docker-compose.prod.yml up -d db

log "Building backend Docker image..."
docker compose --env-file "${ENV_FILE}" -f docker-compose.yml -f docker-compose.prod.yml build --pull "${WEB_SERVICE}"

log "Starting backend service..."
docker compose --env-file "${ENV_FILE}" -f docker-compose.yml -f docker-compose.prod.yml up -d "${WEB_SERVICE}"

log "Running migrations..."
docker compose --env-file "${ENV_FILE}" -f docker-compose.yml -f docker-compose.prod.yml exec -T "${WEB_SERVICE}" python manage.py migrate --noinput

log "Creating default users..."
docker compose --env-file "${ENV_FILE}" -f docker-compose.yml -f docker-compose.prod.yml exec -T "${WEB_SERVICE}" python manage.py create_default_users

log "Collecting static files..."
docker compose --env-file "${ENV_FILE}" -f docker-compose.yml -f docker-compose.prod.yml exec -T "${WEB_SERVICE}" python manage.py collectstatic --noinput

# ---------------- FRONTEND ----------------
log "Updating frontend repository..."
cd "${FRONTEND_DIR}"
git fetch origin "${BRANCH}"
git reset --hard "origin/${BRANCH}"
log "Frontend at origin/${BRANCH}"

log "Installing frontend deps..."
npm install

log "Building frontend..."
npm run build

log "Restarting frontend (PM2)..."
pm2 restart "${FRONTEND_SERVICE}" || pm2 start ecosystem.config.js

# ---------------- CLEANUP ----------------
log "Cleaning up dangling Docker images..."
docker image prune -f || log "Image prune failed (non-fatal)"

log "Deployment complete ✅"
