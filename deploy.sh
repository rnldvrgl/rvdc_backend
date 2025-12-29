#!/usr/bin/env bash
set -Eeuo pipefail

timestamp() { date +'%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(timestamp)] $*"; }
err() { echo "[$(timestamp)] ERROR: $*" >&2; }

APP_NAME="rvdc_backend"
PROJECT_DIR="/srv/${APP_NAME}"
ENV_FILE="${PROJECT_DIR}/.env.production"

[ -f "${ENV_FILE}" ] || { err "Env file not found: ${ENV_FILE}"; exit 1; }

log "Starting backend deployment (pull-only mode)"

command -v docker >/dev/null 2>&1 || { err "Docker not installed"; exit 1; }
command -v docker compose >/dev/null 2>&1 || { err "docker compose missing"; exit 1; }

cd "${PROJECT_DIR}" || { err "Cannot cd to ${PROJECT_DIR}"; exit 1; }

COMPOSE="docker compose --env-file ${ENV_FILE} -f docker-compose.yml -f docker-compose.prod.yml"

log "Pulling latest images..."
${COMPOSE} pull

log "Starting database..."
${COMPOSE} up -d db

log "Starting API..."
${COMPOSE} up -d api

log "Running migrations..."
${COMPOSE} exec -T api python manage.py migrate --noinput

log "Collecting static files..."
${COMPOSE} exec -T api python manage.py collectstatic --noinput

log "Backend deployment complete ✅"
