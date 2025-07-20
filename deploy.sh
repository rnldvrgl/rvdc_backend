#!/bin/bash
set -e
set -o pipefail

APP_NAME="rvdc_backend"
PROJECT_DIR="/srv/$APP_NAME"
DOCKER_COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

cd "$PROJECT_DIR"

echo "[$(date +'%Y-%m-%d %H:%M:%S')] >>> Pulling latest changes from Git..."
git fetch origin master
git reset --hard origin/master

echo "[$(date +'%Y-%m-%d %H:%M:%S')] >>> Pre-deploy Django checks..."
$DOCKER_COMPOSE run --rm web python manage.py check --deploy

echo "[$(date +'%Y-%m-%d %H:%M:%S')] >>> Building production containers..."
$DOCKER_COMPOSE build web

echo "[$(date +'%Y-%m-%d %H:%M:%S')] >>> Updating web container..."
$DOCKER_COMPOSE up -d --no-deps --build web

echo "[$(date +'%Y-%m-%d %H:%M:%S')] >>> Cleaning up dangling images..."
docker image prune -f

echo "[$(date +'%Y-%m-%d %H:%M:%S')] ✅ Deployment complete!"
