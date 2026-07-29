#!/bin/bash
set -e

APP_DIR="/var/www/yaadein"

if [ ! -d "$APP_DIR" ]; then
    echo "Error: Application directory $APP_DIR does not exist!"
    exit 1
fi

cd "$APP_DIR"

echo "Building and starting Docker Compose containers..."
if docker compose version &> /dev/null; then
    docker compose up -d --build
else
    docker-compose up -d --build
fi

echo "Application started successfully."
