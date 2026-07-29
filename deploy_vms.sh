#!/bin/bash

# ==============================================================================
# VMS ALL-IN-ONE STANDALONE DEPLOYER & CONFIGURATOR
# ==============================================================================
# Usage:
#   1. Edit the CONFIGURATION PROPERTIES below in this single file.
#   2. Run: sudo bash deploy_vms.sh
# ==============================================================================

# --- [ 1. CONFIGURATION PROPERTIES ] -----------------------------------------
UPSTREAM_CAMERA_API_URL="https://iportal.iviscloud.net/api/cameras/camera-videoserver"
DATABASE_URL="sqlite+aiosqlite:///./data/app.db"
REDIS_URL="redis://localhost:6379/0"
MEDIAMTX_API_URL="http://localhost:9997"
MEDIAMTX_WEBRTC_URL="http://localhost:8889"
RECORDING_DIR="./data/recordings"        # Set custom path e.g. "/mnt/storage" if needed

TURN_SERVER_URL=""                       # Leave empty to auto-detect system IP (turn:IP:3478)
TURN_SERVER_USERNAME="admin"
TURN_SERVER_CREDENTIAL="admin123"

# --- [ 2. DEPLOYMENT & RESET TOGGLES ] ---------------------------------------
CLEAN_DATABASE=true                      # Set true to wipe SQLite database on deploy
CLEAN_RECORDINGS=true                    # Set true to wipe video recordings/HLS on deploy
FLUSH_REDIS=true                         # Set true to flush Redis cache on deploy
REINSTALL_VENV=true                      # Set true to recreate Python venv
BRANCH_NAME="develop"                    # Git branch to clone/pull

# ==============================================================================
# DO NOT EDIT BELOW THIS LINE UNLESS WRITING CUSTOM SCRIPT LOGIC
# ==============================================================================

set -e

# ANSI Color Codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# Auto-detect TURN server URL if not explicitly set
if [ -z "$TURN_SERVER_URL" ]; then
    PRIMARY_IP=$(hostname -I | awk '{print $1}')
    TURN_SERVER_URL="turn:$PRIMARY_IP:3478"
fi

# 2. Generate .env File from Single-File Configuration Properties
log_info "Generating configuration (.env) from top-level script properties..."
cat <<EOF > "$CURRENT_DIR/.env"
DATABASE_URL=$DATABASE_URL
REDIS_URL=$REDIS_URL
MEDIAMTX_API_URL=$MEDIAMTX_API_URL
MEDIAMTX_WEBRTC_URL=$MEDIAMTX_WEBRTC_URL
UPSTREAM_CAMERA_API_URL=$UPSTREAM_CAMERA_API_URL
TURN_SERVER_URL=$TURN_SERVER_URL
TURN_SERVER_USERNAME=$TURN_SERVER_USERNAME
TURN_SERVER_CREDENTIAL=$TURN_SERVER_CREDENTIAL
RECORDING_DIR=$RECORDING_DIR
EOF
log_info "Generated configuration file successfully."

# 3. Stop Existing Services (if any)
log_info "Stopping active VMS services..."
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
    git reset --hard "origin/$BRANCH_NAME" || true
    git clean -fd || true
else
    log_info "Cloning fresh repository into $INSTALL_DIR..."
    rm -rf "$INSTALL_DIR"
    git clone -b "$BRANCH_NAME" "$REPO_URL" "$INSTALL_DIR"
fi

# 5. Inject Generated .env Configuration
log_info "Injecting .env configuration into backend folder..."
cp "$CURRENT_DIR/.env" "$INSTALL_DIR/backend/.env"

# 6. Install Host OS Dependencies
log_info "Updating system repositories and installing OS dependencies..."
apt-get update -y
apt-get install -y git python3-pip python3-venv ffmpeg sqlite3 redis-server curl wget tar rsync

# 7. Setup Python Virtual Environment
VENV_PATH="/opt/video-backend-venv"
log_info "Setting up Python virtual environment at $VENV_PATH..."
if [ "$REINSTALL_VENV" = true ] && [ -d "$VENV_PATH" ]; then
    log_info "Wiping previous Python virtual environment..."
    rm -rf "$VENV_PATH"
fi
if [ ! -d "$VENV_PATH" ]; then
    python3 -m venv "$VENV_PATH"
fi

log_info "Installing Python backend requirements..."
"$VENV_PATH/bin/pip" install --upgrade pip
"$VENV_PATH/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt"
"$VENV_PATH/bin/pip" install fastapi uvicorn psutil websockets httpx

# 8. Setup MediaMTX Standalone Server
log_info "Setting up MediaMTX standalone binary..."
mkdir -p /opt/mediamtx

if [ ! -f /opt/mediamtx/mediamtx ]; then
    log_info "Detecting latest MediaMTX version..."
    LATEST_TAG=$(curl -s https://api.github.com/repos/bluenviron/mediamtx/releases/latest | grep -oP '"tag_name": "\K[^"]+' || echo "v1.9.0")
    if [ -z "$LATEST_TAG" ] || [ "$LATEST_TAG" == "null" ]; then
        LATEST_TAG="v1.9.0"
    fi

    log_info "Downloading MediaMTX release $LATEST_TAG..."
    wget -q "https://github.com/bluenviron/mediamtx/releases/download/${LATEST_TAG}/mediamtx_${LATEST_TAG}_linux_amd64.tar.gz" -O /opt/mediamtx/mediamtx.tar.gz
    tar -xzf /opt/mediamtx/mediamtx.tar.gz -C /opt/mediamtx/
    rm -f /opt/mediamtx/mediamtx.tar.gz
fi

log_info "Applying MediaMTX configuration..."
if [ -f "$INSTALL_DIR/mediamtx_linux.yml" ]; then
    cp "$INSTALL_DIR/mediamtx_linux.yml" /opt/mediamtx/mediamtx.yml
elif [ -f "$INSTALL_DIR/backend/app/mediamtx.yml" ]; then
    cp "$INSTALL_DIR/backend/app/mediamtx.yml" /opt/mediamtx/mediamtx.yml
fi

# 9. Perform Optional Cleanup Actions
if [ "$CLEAN_DATABASE" = true ]; then
    log_info "[CLEANUP] Removing SQLite database and backup camera cache..."
    rm -f "$INSTALL_DIR/backend/data/app.db"*
    rm -f "$INSTALL_DIR/backend/app/backup_cameras.json"
fi

if [ "$CLEAN_RECORDINGS" = true ]; then
    log_info "[CLEANUP] Removing recorded video files and HLS segments..."
    rm -rf "$INSTALL_DIR/backend/data/recordings/"*
    rm -rf "$INSTALL_DIR/backend/data/hls/"*
fi

mkdir -p "$INSTALL_DIR/backend/data/recordings"
mkdir -p "$INSTALL_DIR/backend/data/hls"

if [ "$FLUSH_REDIS" = true ]; then
    log_info "[CLEANUP] Flushing Redis cache..."
    if command -v redis-cli &> /dev/null; then
        redis-cli flushall || true
    fi
fi

# 10. Register systemd Service Units
log_info "Registering systemd unit configuration files..."

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
log_info "Reloading systemd daemons and starting VMS services..."
systemctl daemon-reload

systemctl enable video-backend.service
systemctl enable mediamtx.service
systemctl enable vms-monitor.service

systemctl restart mediamtx.service
systemctl restart video-backend.service
systemctl restart vms-monitor.service

log_success "VMS deployment and configuration completed successfully!"
log_info "--------------------------------------------------------"
log_info "Core Backend API   : http://(your-ip):8005"
log_info "Telemetry Portal   : http://(your-ip):8010"
log_info "--------------------------------------------------------"
log_info "Active Service Status:"
systemctl is-active mediamtx.service
systemctl is-active video-backend.service
systemctl is-active vms-monitor.service
log_info "--------------------------------------------------------"
