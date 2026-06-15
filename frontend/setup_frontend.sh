#!/bin/bash

# VMS Video Server Frontend Setup Script
# Installs dependencies, runs npm install, configs, and starts frontend systemd services.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color
BLUE='\033[0;34m'
YELLOW='\033[0;33m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 1. Root check
if [ "$EUID" -ne 0 ]; then
  log_error "Please run this script as root (using sudo)."
  exit 1
fi

log_info "Starting Camera Video Platform FRONTEND automation setup..."

# Get frontend directory path (directory where this script resides)
FRONTEND_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
log_info "Frontend directory identified: $FRONTEND_DIR"

# 2. System Dependencies
log_info "Installing system dependencies..."
apt-get update -y
apt-get install -y nodejs npm git

# 3. Install NPM Dependencies
log_info "Installing npm dependencies in frontend..."
cd "$FRONTEND_DIR"
npm install

# 4. Create video-frontend.service
log_info "Creating video-frontend systemd service..."
cat <<EOF > /etc/systemd/system/video-frontend.service
[Unit]
Description=Camera Video Platform Frontend Vite Server
After=network.target video-backend.service

[Service]
User=root
WorkingDirectory=$FRONTEND_DIR
ExecStart=/usr/bin/npm run dev -- --host 0.0.0.0
Restart=always
RestartSec=5
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

# 5. Reload Systemd and Enable Services
log_info "Enabling and starting frontend systemd service..."
systemctl daemon-reload
systemctl enable video-frontend.service
systemctl restart video-frontend.service

log_success "Frontend setup complete!"
log_info "System status check:"
systemctl status video-frontend.service --no-pager -n 5 || true

log_success "Video Platform Frontend UI is fully deployed!"
log_info "Dashboard UI: http://localhost:5173"
