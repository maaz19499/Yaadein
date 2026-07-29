#!/bin/bash
set -e

APP_DIR="/var/www/yaadein"

if [ -d "$APP_DIR" ] && [ -f "$APP_DIR/docker-compose.yml" ]; then
    echo "Stopping existing Docker Compose services in $APP_DIR..."
    cd "$APP_DIR"
    docker compose down --remove-orphans || docker-compose down --remove-orphans || true
fi
