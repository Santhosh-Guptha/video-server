#!/bin/bash

# VMS Video Server Backend Setup Script
# Installs dependencies, creates virtualenv, installs python packages, and starts backend systemd services.

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

log_info "Starting Camera Video Platform BACKEND automation setup..."

# Get backend directory path (directory where this script resides)
BACKEND_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
log_info "Backend directory identified: $BACKEND_DIR"

# 2. System Dependencies
log_info "Installing system dependencies..."
apt-get update -y
apt-get install -y python3-pip python3-venv ffmpeg sqlite3

# 3. Setup Virtual Environment
VENV_PATH="/opt/video-backend-venv"
log_info "Creating virtual environment at $VENV_PATH..."
python3 -m venv "$VENV_PATH"

log_info "Upgrading pip and installing python dependencies..."
"$VENV_PATH/bin/pip" install --upgrade pip
"$VENV_PATH/bin/pip" install -r "$BACKEND_DIR/requirements.txt"

# 4. Create default .env if it doesn't exist
if [ ! -f "$BACKEND_DIR/.env" ]; then
    log_info "Creating default .env file..."
    cat <<EOF > "$BACKEND_DIR/.env"
DATABASE_URL=sqlite+aiosqlite:///./data/app.db
REDIS_URL=redis://localhost:6379/0
MEDIAMTX_API_URL=http://localhost:9997
MEDIAMTX_WEBRTC_URL=http://localhost:8889
UPSTREAM_CAMERA_API_URL=https://iportal2.sronprem.scanalitix.com/api/cameras/camera-videoserver?vsName=STVS1
EOF
fi

# 5. Create video-backend.service
log_info "Creating video-backend systemd service..."
cat <<EOF > /etc/systemd/system/video-backend.service
[Unit]
Description=Camera Video Platform Backend FastAPI
After=network.target

[Service]
User=root
WorkingDirectory=$BACKEND_DIR
ExecStart=$VENV_PATH/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
Environment=PATH=$VENV_PATH/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

# 6. Reload Systemd and Enable Services
log_info "Enabling and starting backend systemd service..."
systemctl daemon-reload
systemctl enable video-backend.service
systemctl restart video-backend.service

log_success "Backend setup complete!"
log_info "System status check:"
systemctl status video-backend.service --no-pager -n 5 || true
