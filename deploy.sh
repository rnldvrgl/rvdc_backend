#!/usr/bin/env bash
set -Eeuo pipefail

# =============================================================================
# RVDC Backend Deployment Script
# =============================================================================
# This script handles the deployment of the RVDC backend application
# Usage: bash deploy.sh
# =============================================================================

timestamp() { date +'%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(timestamp)] $*"; }
err() { echo "[$(timestamp)] ERROR: $*" >&2; }
success() { echo "[$(timestamp)] SUCCESS: $*"; }
warning() { echo "[$(timestamp)] WARNING: $*"; }

APP_NAME="rvdc_backend"
PROJECT_DIR="/srv/${APP_NAME}"
ENV_FILE="${PROJECT_DIR}/.env.production"

# =============================================================================
# Print banner
# =============================================================================
echo ""
echo "================================================================================"
log "RVDC BACKEND DEPLOYMENT"
echo "================================================================================"
echo ""

# =============================================================================
# Step 0: Pre-flight checks
# =============================================================================
log "Step 0: Running pre-flight checks..."

[ -f "${ENV_FILE}" ] || { err "Env file not found: ${ENV_FILE}"; exit 1; }
command -v docker >/dev/null 2>&1 || { err "Docker not installed"; exit 1; }
command -v docker compose >/dev/null 2>&1 || { err "docker compose missing"; exit 1; }
cd "${PROJECT_DIR}" || { err "Cannot cd to ${PROJECT_DIR}"; exit 1; }

success "Pre-flight checks passed"
echo ""

# =============================================================================
# Step 1: Setup directories
# =============================================================================
log "Step 1: Setting up media and static directories..."

mkdir -p /srv/rvdc_backend/media/profile_images
mkdir -p /srv/rvdc_backend/staticfiles
chmod -R 755 /srv/rvdc_backend/media
chmod -R 755 /srv/rvdc_backend/staticfiles

success "Directories configured"
echo ""

# =============================================================================
# Step 2: Define compose command
# =============================================================================
COMPOSE="docker compose --env-file ${ENV_FILE} -f docker-compose.yml -f docker-compose.prod.yml"

# =============================================================================
# Step 3: Pull latest images
# =============================================================================
log "Step 3: Pulling latest Docker images..."

${COMPOSE} pull

success "Images pulled"
echo ""

# =============================================================================
# Step 4: Start database
# =============================================================================
log "Step 4: Starting database container..."

${COMPOSE} up -d db

log "Waiting for database to be ready..."
sleep 5

# Check if database is ready
RETRIES=30
until ${COMPOSE} exec -T db pg_isready -U postgres > /dev/null 2>&1 || [ $RETRIES -eq 0 ]; do
    echo -n "."
    sleep 1
    RETRIES=$((RETRIES - 1))
done
echo ""

if [ $RETRIES -eq 0 ]; then
    err "Database failed to start"
    exit 1
fi

success "Database is ready"
echo ""

# =============================================================================
# Step 5: Start API container
# =============================================================================
log "Step 5: Starting API container..."

${COMPOSE} up -d api

log "Waiting for API to initialize..."
sleep 5

success "API container started"
echo ""

# =============================================================================
# Step 6: Initialize default stalls
# =============================================================================
log "Step 6: Ensuring default stalls exist..."

log "Running create_default_users command to setup Main and Sub stalls..."
${COMPOSE} exec -T api python manage.py create_default_users

success "Stalls initialized"
echo ""

# =============================================================================
# Step 7: Run database migrations
# =============================================================================
log "Step 7: Running database migrations..."

${COMPOSE} exec -T api python manage.py migrate --noinput

success "Migrations completed"
echo ""

# =============================================================================
# Step 8: Collect static files
# =============================================================================
log "Step 8: Collecting static files..."

${COMPOSE} exec -T api python manage.py collectstatic --noinput

success "Static files collected"
echo ""

# =============================================================================
# Step 9: Health checks
# =============================================================================
log "Step 9: Running health checks..."

echo ""
log "Checking API health..."
if ${COMPOSE} exec -T api python manage.py check --deploy > /dev/null 2>&1; then
    success "API health check passed"
else
    warning "API check returned warnings (may be non-critical)"
fi

echo ""
log "Container status:"
${COMPOSE} ps

echo ""
success "Health checks complete"
echo ""

# =============================================================================
# Step 10: Show deployment summary
# =============================================================================
echo ""
echo "================================================================================"
success "DEPLOYMENT COMPLETE"
echo "================================================================================"
echo ""
log "Services are running at:"
log "  • API: http://localhost:8000"
log "  • Database: localhost:5432"
echo ""
log "Useful commands:"
log "  • View logs: docker compose logs -f api"
log "  • Check status: docker compose ps"
log "  • Restart API: docker compose restart api"
log "  • Shell access: docker compose exec api bash"
echo ""
log "Database management:"
log "  • Clear transactional data: docker compose exec api python manage.py clear_database"
log "  • Interactive cleanup: docker compose exec api python manage.py clear_database_interactive"
log "  • Add holidays: docker compose exec api python manage.py add_philippine_holidays --year 2026"
log "  • Remove duplicate clients: docker compose exec api python manage.py remove_duplicate_clients"
echo ""
log "Optional maintenance:"
log "  • Cleanup unused images: docker compose exec api python manage.py cleanup_unused_images --dry-run"
log "  • Uppercase client names: docker compose exec api python manage.py uppercase_client_names --dry-run"
echo ""

if [ -f "${PROJECT_DIR}/nginx_config.conf" ]; then
    warning "Don't forget to update NGINX configuration if needed:"
    log "  • Config reference: ${PROJECT_DIR}/nginx_config.conf"
    log "  • Edit: sudo nano /etc/nginx/sites-available/rvdc_backend"
    log "  • Test: sudo nginx -t"
    log "  • Reload: sudo systemctl reload nginx"
    echo ""
fi

echo "================================================================================"
echo ""

exit 0
