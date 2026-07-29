#!/bin/bash
set -e

APP_DIR="/var/www/yaadein"

echo "Ensuring application directory exists: $APP_DIR"
mkdir -p "$APP_DIR"

# Ensure Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Docker not found. Installing Docker..."
    if command -v apt-get &> /dev/null; then
        apt-get update -y
        apt-get install -y docker.io docker-compose-plugin
    elif command -v dnf &> /dev/null; then
        dnf install -y docker docker-compose-plugin
    elif command -v yum &> /dev/null; then
        yum install -y docker
    fi
    systemctl enable docker
    systemctl start docker
fi

# Ensure Docker Compose (V2 plugin or stand-alone) is available
if ! docker compose version &> /dev/null && ! command -v docker-compose &> /dev/null; then
    echo "Installing Docker Compose CLI plugin..."
    mkdir -p ~/.docker/cli-plugins/
    curl -SL https://github.com/docker/compose/releases/download/v2.24.5/docker-compose-linux-x86_64 -o ~/.docker/cli-plugins/docker-compose
    chmod +x ~/.docker/cli-plugins/docker-compose
fi

echo "Dependencies installation completed."
