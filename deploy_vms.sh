#!/bin/bash

# ==============================================================================
# VMS Observability & Core Video Platform - Unified Standalone Deployer Script
# ==============================================================================
# Usage: Place this script and your custom '.env' file in the same directory.
#        Run with: sudo bash deploy_vms.sh
# ==============================================================================

set -e

# ANSI Color Codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO] $(date +'%H:%M:%S')${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS] $(date +'%H:%M:%S')${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN] $(date +'%H:%M:%S')${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR] $(date +'%H:%M:%S')${NC} $1"
}

# 1. Root Privilege Enforcement
if [ "$EUID" -ne 0 ]; then
    log_error "Please run this script as root (using sudo)."
    exit 1
fi

CURRENT_DIR="$(pwd)"
log_info "Deployment initiated from: $CURRENT_DIR"

# 2. Check for Provided .env File
if [ ! -f "$CURRENT_DIR/.env" ]; then
    log_warn "No .env file found in current directory ($CURRENT_DIR)."
    log_warn "Creating a default template configuration..."
    
    PRIMARY_IP=$(hostname -I | awk '{print $1}')
    cat <<EOF > "$CURRENT_DIR/.env"
DATABASE_URL=sqlite+aiosqlite:///./data/app.db
REDIS_URL=redis://localhost:6379/0
MEDIAMTX_API_URL=http://localhost:9997
MEDIAMTX_WEBRTC_URL=http://localhost:8889
UPSTREAM_CAMERA_API_URL=https://iportal.iviscloud.net/api/cameras/camera-videoserver
TURN_SERVER_URL=turn:$PRIMARY_IP:3478
TURN_SERVER_USERNAME=admin
TURN_SERVER_CREDENTIAL=admin123
EOF
    log_info "Created default template .env successfully."
fi

# 3. Stop Existing Services (if any) to prevent lockouts
log_info "Stopping any active VMS services..."
systemctl stop video-backend.service || true
systemctl stop mediamtx.service || true
systemctl stop vms-monitor.service || true

# 4. Clone or Pull Latest Project Source
INSTALL_DIR="/opt/video-server"
REPO_URL="https://github.com/Santhosh-Guptha/video-server.git"

if [ -d "$CURRENT_DIR/backend" ]; then
    log_info "Deploying directly from local source folder ($CURRENT_DIR) into $INSTALL_DIR..."
    mkdir -p "$INSTALL_DIR"
    rsync -a --exclude='node_modules' --exclude='.git' --exclude='*.db' --exclude='.venv' "$CURRENT_DIR/" "$INSTALL_DIR/" 2>/dev/null || true
elif [ -d "$INSTALL_DIR/.git" ]; then
    log_info "Directory $INSTALL_DIR exists and is a git repository. Performing clean git reset..."
    cd "$INSTALL_DIR"
    git fetch origin || true
    git reset --hard origin/develop || true
    git clean -fd || true
else
    log_info "Cloning fresh repository into $INSTALL_DIR..."
    rm -rf "$INSTALL_DIR"
    git clone -b develop "$REPO_URL" "$INSTALL_DIR"
fi

# 5. Inject the Provided .env File
log_info "Copying user .env configuration into backend folder..."
cp "$CURRENT_DIR/.env" "$INSTALL_DIR/backend/.env"

# 6. Install Host OS Packages
log_info "Updating system repositories and installing dependencies..."
apt-get update -y
apt-get install -y git python3-pip python3-venv ffmpeg sqlite3 redis-server curl wget tar

# 7. Setup Clean Python Virtual Environment
VENV_PATH="/opt/video-backend-venv"
log_info "Setting up Python virtual environment at $VENV_PATH..."
if [ -d "$VENV_PATH" ]; then
    log_info "Cleaning up previous environment data..."
    rm -rf "$VENV_PATH"
fi
python3 -m venv "$VENV_PATH"

log_info "Upgrading pip and installing requirements (excluding AI/CUDA dependencies)..."
"$VENV_PATH/bin/pip" install --upgrade pip
"$VENV_PATH/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt"
# Telemetry daemon packages
"$VENV_PATH/bin/pip" install fastapi uvicorn psutil websockets httpx

# 8. Download and Configure MediaMTX Standalone
log_info "Setting up MediaMTX standalone binary..."
mkdir -p /opt/mediamtx

log_info "Detecting latest MediaMTX version..."
LATEST_TAG=$(curl -s https://api.github.com/repos/bluenviron/mediamtx/releases/latest | grep -oP '"tag_name": "\K[^"]+')
if [ -z "$LATEST_TAG" ] || [ "$LATEST_TAG" == "null" ]; then
    LATEST_TAG="v1.9.0"
fi

log_info "Downloading MediaMTX release $LATEST_TAG..."
wget -q "https://github.com/bluenviron/mediamtx/releases/download/${LATEST_TAG}/mediamtx_${LATEST_TAG}_linux_amd64.tar.gz" -O /opt/mediamtx/mediamtx.tar.gz

log_info "Extracting tarball..."
tar -xzf /opt/mediamtx/mediamtx.tar.gz -C /opt/mediamtx/
rm -f /opt/mediamtx/mediamtx.tar.gz

log_info "Applying configurations to MediaMTX..."
if [ -f "$INSTALL_DIR/mediamtx_linux.yml" ]; then
    cp "$INSTALL_DIR/mediamtx_linux.yml" /opt/mediamtx/mediamtx.yml
elif [ -f "$INSTALL_DIR/backend/app/mediamtx.yml" ]; then
    cp "$INSTALL_DIR/backend/app/mediamtx.yml" /opt/mediamtx/mediamtx.yml
else
    log_warn "No custom mediamtx config file found. Running with default configs..."
fi

# 9. Setup Clean Storage Directories (ROM data)
log_info "Wiping out previous databases, logs, and video fragments..."
rm -rf "$INSTALL_DIR/backend/data"
mkdir -p "$INSTALL_DIR/backend/data/recordings"
mkdir -p "$INSTALL_DIR/backend/data/hls"

log_info "Flushing Redis caches..."
if command -v redis-cli &> /dev/null; then
    redis-cli flushall || true
fi

# 10. Register systemd Units
log_info "Registering systemd unit configuration files..."

# backend service unit
cat <<EOF > /etc/systemd/system/video-backend.service
[Unit]
Description=Camera Video Platform Backend FastAPI
After=network.target redis-server.service

[Service]
User=root
WorkingDirectory=$INSTALL_DIR/backend
ExecStart=$VENV_PATH/bin/uvicorn app.main:app --host 0.0.0.0 --port 8005
Restart=always
RestartSec=5
Environment=PATH=$VENV_PATH/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

# mediamtx service unit
cat <<EOF > /etc/systemd/system/mediamtx.service
[Unit]
Description=MediaMTX RTSP/WebRTC Server
After=network.target

[Service]
User=root
WorkingDirectory=/opt/mediamtx
ExecStart=/opt/mediamtx/mediamtx /opt/mediamtx/mediamtx.yml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# system observability portal service unit
cat <<EOF > /etc/systemd/system/vms-monitor.service
[Unit]
Description=VMS Standalone Telemetry and Operations Portal
After=network.target redis-server.service video-backend.service

[Service]
User=root
WorkingDirectory=$INSTALL_DIR/monitoring-app
ExecStart=$VENV_PATH/bin/python app.py
Restart=always
RestartSec=5
Environment=PATH=$VENV_PATH/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

# 11. Enable & Launch Services
log_info "Reloading systemd daemons and launching services..."
systemctl daemon-reload

systemctl enable video-backend.service
systemctl enable mediamtx.service
systemctl enable vms-monitor.service

systemctl restart mediamtx.service
systemctl restart video-backend.service
systemctl restart vms-monitor.service

log_success "Deployment completed successfully!"
log_info "--------------------------------------------------------"
log_info "Core Backend port: http://(your-ip):8005"
log_info "Observability Portal port: http://(your-ip):8010"
log_info "--------------------------------------------------------"
log_info "System Status Indicators:"
systemctl is-active mediamtx.service
systemctl is-active video-backend.service
systemctl is-active vms-monitor.service
log_info "--------------------------------------------------------"
