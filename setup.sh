#!/bin/bash

# VMS Video Server Automation Setup Script
# Installs dependencies, sets up virtualenv, configs, MediaMTX, and starts the systemd services.

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

log_info "Starting Camera Video Platform automation setup..."

# Get project path (directory where the setup script resides)
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
log_info "Project directory identified: $PROJECT_DIR"

# 2. System Dependencies
log_info "Installing system dependencies..."
apt-get update -y
apt-get install -y ffmpeg sqlite3 curl python3 python3-pip python3-venv nodejs npm git

# 3. Create MediaMTX Directory and Download Binary
log_info "Setting up MediaMTX..."
MTX_DIR="/opt/mediamtx"
mkdir -p "$MTX_DIR"

if [ ! -f "$MTX_DIR/mediamtx" ]; then
    log_info "Downloading MediaMTX v1.9.0..."
    MTX_TEMP=$(mktemp -d)
    curl -L -o "$MTX_TEMP/mediamtx.tar.gz" https://github.com/bluenviron/mediamtx/releases/download/v1.9.0/mediamtx_v1.9.0_linux_amd64.tar.gz
    tar -xzf "$MTX_TEMP/mediamtx.tar.gz" -C "$MTX_DIR"
    rm -rf "$MTX_TEMP"
    log_success "MediaMTX downloaded and extracted to $MTX_DIR"
else
    log_info "MediaMTX is already installed."
fi

# Copy mediamtx config from local project files
if [ -f "$PROJECT_DIR/mediamtx_linux.yml" ]; then
    log_info "Copying mediamtx config from mediamtx_linux.yml..."
    cp "$PROJECT_DIR/mediamtx_linux.yml" "$MTX_DIR/mediamtx.yml"
elif [ -f "$PROJECT_DIR/backend/app/mediamtx.yml" ]; then
    log_info "Copying mediamtx config from backend/app/mediamtx.yml..."
    cp "$PROJECT_DIR/backend/app/mediamtx.yml" "$MTX_DIR/mediamtx.yml"
else
    log_warn "MediaMTX config template not found, using default configuration."
fi

# Ensure segment complete hook script is executable
HOOK_SCRIPT="$PROJECT_DIR/backend/app/segment_hook.sh"
if [ -f "$HOOK_SCRIPT" ]; then
    log_info "Setting segment_hook.sh to executable..."
    chmod +x "$HOOK_SCRIPT"
fi

# Perform dynamic directory path adjustments inside configurations
log_info "Adapting configuration directories to dynamic install path..."
sed -i "s|/opt/video-server|$PROJECT_DIR|g" "$MTX_DIR/mediamtx.yml" || true
if [ -f "$HOOK_SCRIPT" ]; then
    sed -i "s|/opt/video-server|$PROJECT_DIR|g" "$HOOK_SCRIPT" || true
fi

# Create mediamtx.service
log_info "Creating mediamtx systemd service..."
cat <<EOF > /etc/systemd/system/mediamtx.service
[Unit]
Description=MediaMTX RTSP Server
After=network.target

[Service]
Type=simple
WorkingDirectory=$MTX_DIR
ExecStart=$MTX_DIR/mediamtx $MTX_DIR/mediamtx.yml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 4. Set up Backend Python Virtual Environment
log_info "Setting up Python virtual environment..."
VENV_DIR="/opt/video-backend-venv"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
if [ -f "$PROJECT_DIR/backend/requirements.txt" ]; then
    log_info "Installing requirements.txt..."
    "$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/backend/requirements.txt"
else
    log_error "requirements.txt not found!"
    exit 1
fi

# Setup backend env file
BACKEND_ENV="$PROJECT_DIR/backend/.env"
if [ ! -f "$BACKEND_ENV" ]; then
    log_info "Creating default .env file for backend..."
    if [ -f "$PROJECT_DIR/backend/.env.example" ]; then
        cp "$PROJECT_DIR/backend/.env.example" "$BACKEND_ENV"
    else
        cat <<EOF > "$BACKEND_ENV"
UPSTREAM_CAMERA_API_URL=https://uat1.iviscloud.net/api/cameras/camera-videoserver
DATABASE_URL=sqlite+aiosqlite:///./data/app.db
EOF
    fi
fi

# Create directories required by backend
mkdir -p "$PROJECT_DIR/backend/data/recordings"
mkdir -p "$PROJECT_DIR/backend/data/hls"

# Create video-backend.service
log_info "Creating video-backend systemd service..."
cat <<EOF > /etc/systemd/system/video-backend.service
[Unit]
Description=Camera Video Platform Backend FastAPI
After=network.target

[Service]
User=root
WorkingDirectory=$PROJECT_DIR/backend
ExecStart=$VENV_DIR/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
Environment=PATH=$VENV_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

# 5. Set up Frontend UI dependencies
log_info "Setting up frontend Node/npm dependencies..."
cd "$PROJECT_DIR/frontend"
npm install

# Create video-frontend.service
log_info "Creating video-frontend systemd service..."
cat <<EOF > /etc/systemd/system/video-frontend.service
[Unit]
Description=Camera Video Platform Frontend Vite Server
After=network.target video-backend.service

[Service]
User=root
WorkingDirectory=$PROJECT_DIR/frontend
ExecStart=/usr/bin/npm run dev -- --host 0.0.0.0
Restart=always
RestartSec=5
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

# 6. Reload Systemd and Enable Services
log_info "Enabling and starting systemd services..."
systemctl daemon-reload

systemctl enable mediamtx.service
systemctl enable video-backend.service
systemctl enable video-frontend.service

systemctl restart mediamtx.service
systemctl restart video-backend.service
systemctl restart video-frontend.service

log_success "Setup complete! Services are running under systemd."
log_info "System status check:"
systemctl status mediamtx.service --no-pager -n 5 || true
systemctl status video-backend.service --no-pager -n 5 || true
systemctl status video-frontend.service --no-pager -n 5 || true

log_success "Video Platform is fully deployed!"
log_info "Dashboard UI: http://localhost:5173"
log_info "Backend API: http://localhost:8000"
