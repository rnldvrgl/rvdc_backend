#!/usr/bin/env bash
set -Eeuo pipefail

# =============================================================================
# RVDC Backend Deployment Script
# =============================================================================
# This script handles the deployment of the RVDC backend application
# Usage: bash deploy.sh [--init-users]
# Options:
#   --init-users    Initialize default stalls and users (optional)
# =============================================================================

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
WHITE='\033[1;37m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

# Icons
ICON_SUCCESS="✓"
ICON_ERROR="✗"
ICON_WARNING="⚠"
ICON_INFO="ℹ"
ICON_ARROW="→"
ICON_ROCKET="🚀"
ICON_PACKAGE="📦"
ICON_DATABASE="🗄️"
ICON_CODE="💻"
ICON_CHECK="✔"
ICON_CLOCK="⏱️"

timestamp() { date +'%Y-%m-%d %H:%M:%S'; }
log() { echo -e "${GRAY}[$(timestamp)]${NC} ${CYAN}${ICON_INFO}${NC} $*"; }
success() { echo -e "${GRAY}[$(timestamp)]${NC} ${GREEN}${ICON_SUCCESS}${NC} $*"; }
err() { echo -e "${GRAY}[$(timestamp)]${NC} ${RED}${ICON_ERROR} ERROR:${NC} $*" >&2; }
warning() { echo -e "${GRAY}[$(timestamp)]${NC} ${YELLOW}${ICON_WARNING}${NC} $*"; }
step() { echo -e "\n${MAGENTA}${ICON_ARROW}${NC} ${WHITE}$*${NC}"; }
header() { echo -e "${CYAN}$*${NC}"; }

APP_NAME="rvdc_backend"
PROJECT_DIR="/srv/${APP_NAME}"
ENV_FILE="${PROJECT_DIR}/.env.production"

# Parse command line arguments
INIT_USERS=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --init-users)
            INIT_USERS=true
            shift
            ;;
        *)
            err "Unknown option: $1"
            echo "Usage: bash deploy.sh [--init-users]"
            exit 1
            ;;
    esac
done

# =============================================================================
# Print banner
# =============================================================================
echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${WHITE}                    ${ICON_ROCKET} RVDC BACKEND DEPLOYMENT ${ICON_ROCKET}${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo ""

# =============================================================================
# Step 0: Pre-flight checks
# =============================================================================
step "Step 0: Running pre-flight checks..."

[ -f "${ENV_FILE}" ] || { err "Env file not found: ${ENV_FILE}"; exit 1; }
command -v docker >/dev/null 2>&1 || { err "Docker not installed"; exit 1; }
command -v docker compose >/dev/null 2>&1 || { err "docker compose missing"; exit 1; }
cd "${PROJECT_DIR}" || { err "Cannot cd to ${PROJECT_DIR}"; exit 1; }

success "Pre-flight checks passed"
echo ""

# =============================================================================
# Step 1: Pull latest code from GitHub
# =============================================================================
step "Step 1: ${ICON_CODE} Pulling latest code from GitHub..."

# Configure git to ignore file permission changes
git config core.filemode false

# Stash any local changes
if ! git diff-index --quiet HEAD --; then
    warning "Local changes detected, stashing them..."
    git stash
    STASHED=true
else
    STASHED=false
fi

# Pull latest code
log "Fetching from origin..."
git fetch origin

log "Pulling changes..."
if git pull origin master; then
    success "Code updated successfully"
else
    err "Failed to pull from GitHub"
    if [ "$STASHED" = true ]; then
        log "Attempting to restore stashed changes..."
        git stash pop
    fi
    exit 1
fi

# Restore stashed changes if any
if [ "$STASHED" = true ]; then
    log "Restoring stashed changes..."
    if git stash pop; then
        success "Local changes restored"
    else
        warning "Could not restore stashed changes (may have conflicts)"
        log "Your changes are still in stash. Run 'git stash pop' manually to restore them."
    fi
fi

echo ""

# =============================================================================
# Step 2: Setup directories
# =============================================================================
step "Step 2: Setting up media and static directories..."

mkdir -p /srv/rvdc_backend/media/profile_images
mkdir -p /srv/rvdc_backend/staticfiles
chmod -R 755 /srv/rvdc_backend/media
chmod -R 755 /srv/rvdc_backend/staticfiles

success "Directories configured"
echo ""

# =============================================================================
# Step 3: Define compose command
# =============================================================================
COMPOSE="docker compose --env-file ${ENV_FILE} -f docker-compose.yml -f docker-compose.prod.yml"

# =============================================================================
# Step 4: Pull latest images
# =============================================================================
step "Step 4: ${ICON_PACKAGE} Pulling latest Docker images..."

${COMPOSE} pull

success "Images pulled"
echo ""

# =============================================================================
# Step 5: Start database
# =============================================================================
step "Step 5: ${ICON_DATABASE} Starting database container..."

${COMPOSE} up -d db

log "Waiting for database to be ready..."
sleep 5

# Check if database is ready
RETRIES=30
echo -ne "${GRAY}[$(timestamp)]${NC} ${CYAN}${ICON_CLOCK}${NC} Checking database health"
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
# Step 6: Start API container
# =============================================================================
step "Step 6: ${ICON_CODE} Starting API container..."

${COMPOSE} up -d api

log "Waiting for API to initialize..."
sleep 5

success "API container started"
echo ""

# =============================================================================
# Step 7: Initialize default stalls and users (optional)
# =============================================================================
if [ "$INIT_USERS" = true ]; then
    step "Step 7: Initializing default stalls and users..."

    log "Running create_default_users command to setup Main and Sub stalls..."
    ${COMPOSE} exec -T api python manage.py create_default_users

    success "Stalls and users initialized"
    echo ""
else
    step "Step 7: Skipping user initialization"
    log "Use --init-users flag to enable user initialization"
    echo ""
fi

# =============================================================================
# Step 8: Run database migrations
# =============================================================================
step "Step 8: ${ICON_DATABASE} Running database migrations..."

log "Checking for pending migrations..."
if MIGRATION_OUTPUT=$(${COMPOSE} exec -T api python manage.py migrate --noinput 2>&1); then
    if echo "$MIGRATION_OUTPUT" | grep -q "No migrations to apply"; then
        success "No pending migrations - database is up to date"
    else
        success "Migrations applied successfully"
        echo -e "${GRAY}${MIGRATION_OUTPUT}${NC}"
    fi
else
    err "Migration failed!"
    echo -e "${RED}${MIGRATION_OUTPUT}${NC}"
    exit 1
fi

echo ""

# =============================================================================
# Step 9: Collect static files
# =============================================================================
step "Step 9: ${ICON_PACKAGE} Collecting static files..."

${COMPOSE} exec -T api python manage.py collectstatic --noinput

success "Static files collected"
echo ""

# =============================================================================
# Step 10: Health checks
# =============================================================================
step "Step 10: ${ICON_CHECK} Running health checks..."

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
# Step 11: Show deployment summary
# =============================================================================
echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}                      ${ICON_SUCCESS} DEPLOYMENT COMPLETE ${ICON_SUCCESS}${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo ""
header "Services are running at:"
echo -e "  ${GREEN}•${NC} API: ${CYAN}http://localhost:8000${NC}"
echo -e "  ${GREEN}•${NC} Database: ${CYAN}localhost:5432${NC}"
echo ""
header "Useful commands:"
echo -e "  ${GREEN}•${NC} View logs: ${YELLOW}docker compose logs -f api${NC}"
echo -e "  ${GREEN}•${NC} Check status: ${YELLOW}docker compose ps${NC}"
echo -e "  ${GREEN}•${NC} Restart API: ${YELLOW}docker compose restart api${NC}"
echo -e "  ${GREEN}•${NC} Shell access: ${YELLOW}docker compose exec api bash${NC}"
echo -e "  ${GREEN}•${NC} Redeploy with user init: ${YELLOW}bash deploy.sh --init-users${NC}"
echo ""
header "Database management:"
echo -e "  ${GREEN}•${NC} Initialize users/stalls: ${YELLOW}docker compose exec api python manage.py create_default_users${NC}"
echo -e "  ${GREEN}•${NC} Clear transactional data: ${YELLOW}docker compose exec api python manage.py clear_database${NC}"
echo -e "  ${GREEN}•${NC} Interactive cleanup: ${YELLOW}docker compose exec api python manage.py clear_database_interactive${NC}"
echo -e "  ${GREEN}•${NC} Add holidays: ${YELLOW}docker compose exec api python manage.py add_philippine_holidays --year 2026${NC}"
echo -e "  ${GREEN}•${NC} Remove duplicate clients: ${YELLOW}docker compose exec api python manage.py remove_duplicate_clients${NC}"
echo ""
header "Optional maintenance:"
echo -e "  ${GREEN}•${NC} Cleanup unused images: ${YELLOW}docker compose exec api python manage.py cleanup_unused_images --dry-run${NC}"
echo -e "  ${GREEN}•${NC} Uppercase client names: ${YELLOW}docker compose exec api python manage.py uppercase_client_names --dry-run${NC}"
echo ""

if [ -f "${PROJECT_DIR}/nginx_config.conf" ]; then
    warning "Don't forget to update NGINX configuration if needed:"
    echo -e "  ${GREEN}•${NC} Config reference: ${CYAN}${PROJECT_DIR}/nginx_config.conf${NC}"
    echo -e "  ${GREEN}•${NC} Edit: ${YELLOW}sudo nano /etc/nginx/sites-available/rvdc_backend${NC}"
    echo -e "  ${GREEN}•${NC} Test: ${YELLOW}sudo nginx -t${NC}"
    echo -e "  ${GREEN}•${NC} Reload: ${YELLOW}sudo systemctl reload nginx${NC}"
    echo ""
fi

echo -e "${CYAN}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo ""

exit 0
