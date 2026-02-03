#!/usr/bin/env bash
set -Eeuo pipefail

timestamp() { date +'%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(timestamp)] $*"; }
err() { echo "[$(timestamp)] ERROR: $*" >&2; }

APP_NAME="rvdc_backend"
PROJECT_DIR="/srv/${APP_NAME}"
ENV_FILE="${PROJECT_DIR}/.env.production"

[ -f "${ENV_FILE}" ] || { err "Env file not found: ${ENV_FILE}"; exit 1; }

log "Starting backend deployment"

command -v docker >/dev/null 2>&1 || { err "Docker not installed"; exit 1; }
command -v docker compose >/dev/null 2>&1 || { err "docker compose missing"; exit 1; }

cd "${PROJECT_DIR}" || { err "Cannot cd to ${PROJECT_DIR}"; exit 1; }

COMPOSE="docker compose --env-file ${ENV_FILE} -f docker-compose.yml -f docker-compose.prod.yml"

# Setup media and static directories
log "Setting up media and static directories..."
mkdir -p /srv/rvdc_backend/media/profile_images
mkdir -p /srv/rvdc_backend/staticfiles
chmod -R 755 /srv/rvdc_backend/media
chmod -R 755 /srv/rvdc_backend/staticfiles

log "Pulling latest images..."
${COMPOSE} pull

log "Starting database..."
${COMPOSE} up -d db

log "Starting API..."
${COMPOSE} up -d api

log "Waiting a few seconds for API to be ready..."
sleep 5

log "Running migrations..."
${COMPOSE} exec -T api python manage.py migrate --noinput

log "Collecting static files..."
${COMPOSE} exec -T api python manage.py collectstatic --noinput

log "Updating NGINX configuration with CORS headers..."
if [ -f "${PROJECT_DIR}/nginx_config.conf" ]; then
    log "NGINX config reference available at: ${PROJECT_DIR}/nginx_config.conf"
    log "To update your NGINX config, run:"
    log "  sudo nano /etc/nginx/sites-available/rvdc_backend"
    log "  sudo nginx -t"
    log "  sudo systemctl reload nginx"
else
    log "Warning: nginx_config.conf not found"
fi

log "Backend deployment complete ✅"
log ""
log "Optional maintenance commands:"
log "  Cleanup unused images: ${COMPOSE} exec api python manage.py cleanup_unused_images --dry-run"
log "  Uppercase client names: ${COMPOSE} exec api python manage.py uppercase_client_names --dry-run"
