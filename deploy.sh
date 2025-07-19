#!/bin/bash

set -e
set -o pipefail

APP_NAME="rvdc_backend"
PROJECT_DIR="/srv/$APP_NAME"
DOCKER_COMPOSE="docker compose"

echo ">>> Pulling latest changes from Git..."
cd "$PROJECT_DIR"
git pull origin master

echo ">>> Building Docker containers..."
$DOCKER_COMPOSE build

echo ">>> Restarting Docker containers..."
$DOCKER_COMPOSE down
$DOCKER_COMPOSE up -d

echo ">>> Cleaning up unused Docker resources..."
docker system prune -f

echo ">>> ✅ Deployment complete!"
