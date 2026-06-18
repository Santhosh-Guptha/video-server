#!/bin/bash

# VMS Video Server Backend Setup & Fresh Start Script
# Installs dependencies, cleans up all previous data (fresh restart),
# creates virtualenv, installs python packages, configures .env, and starts backend services.

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

log_info "Starting Camera Video Platform BACKEND automation setup and clean fresh restart..."

# Get backend directory path (directory where this script resides)
BACKEND_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
log_info "Backend directory identified: $BACKEND_DIR"

# 2. Stop Services for Cleanup
log_info "Stopping video-backend and mediamtx systemd services..."
systemctl stop video-backend.service || true
systemctl stop mediamtx.service || true

# 3. Clean up recordings, HLS, databases, and caches
log_info "Performing full cleanup of recording files, HLS segments, SQLite DB, and Redis cache..."

if [ -d "$BACKEND_DIR/data/recordings" ]; then
    log_info "Wiping recordings..."
    rm -rf "$BACKEND_DIR/data/recordings"/*
fi
mkdir -p "$BACKEND_DIR/data/recordings"

if [ -d "$BACKEND_DIR/data/hls" ]; then
    log_info "Wiping HLS segments..."
    rm -rf "$BACKEND_DIR/data/hls"/*
fi
mkdir -p "$BACKEND_DIR/data/hls"

log_info "Wiping SQLite database..."
rm -f "$BACKEND_DIR/data/app.db"
rm -f "$BACKEND_DIR/data/app.db-shm"
rm -f "$BACKEND_DIR/data/app.db-wal"

log_info "Flushing Redis cache..."
if command -v redis-cli &> /dev/null; then
    redis-cli flushall || true
fi

# 4. System Dependencies
log_info "Installing system dependencies..."
apt-get update -y
apt-get install -y python3-pip python3-venv ffmpeg sqlite3 redis-server

# 5. Setup Virtual Environment
VENV_PATH="/opt/video-backend-venv"
log_info "Creating virtual environment at $VENV_PATH..."
python3 -m venv "$VENV_PATH"

log_info "Upgrading pip and installing python dependencies..."
"$VENV_PATH/bin/pip" install --upgrade pip
"$VENV_PATH/bin/pip" install -r "$BACKEND_DIR/requirements.txt"

# 6. Recreate/Overwrite .env file with fresh values
log_info "Recreating .env configuration file..."
EXISTING_UPSTREAM=""
if [ -f "$BACKEND_DIR/.env" ]; then
    EXISTING_UPSTREAM=$(grep -E "^UPSTREAM_CAMERA_API_URL=" "$BACKEND_DIR/.env" | cut -d'=' -f2-)
fi
if [ -z "$EXISTING_UPSTREAM" ]; then
    EXISTING_UPSTREAM="https://uat1.iviscloud.net/api/cameras/camera-videoserver"
fi

cat <<EOF > "$BACKEND_DIR/.env"
DATABASE_URL=sqlite+aiosqlite:///./data/app.db
REDIS_URL=redis://localhost:6379/0
MEDIAMTX_API_URL=http://localhost:9997
MEDIAMTX_WEBRTC_URL=http://localhost:8889
UPSTREAM_CAMERA_API_URL=$EXISTING_UPSTREAM
EOF

# 7. Create video-backend.service
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

# 8. Reload Systemd and Enable/Restart Services
log_info "Reloading systemd, enabling services, and restarting..."
systemctl daemon-reload
systemctl enable video-backend.service
systemctl restart video-backend.service
systemctl restart mediamtx.service || true

log_success "Backend setup and fresh start complete!"
log_info "System status check:"
systemctl status video-backend.service --no-pager -n 5 || true
