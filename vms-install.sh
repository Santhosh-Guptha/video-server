#!/usr/bin/env bash
# ==============================================================================
# Unified VMS Stack - Automated Bootstrap Role-Based Installation Script
# Target Platform: Ubuntu 20.04/22.04 LTS (Fresh VM)
# Design: Supports installing Core (VM 2), Transcoder (VM 1), or Both (all).
# ==============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 1. Root check
if [[ "$EUID" -ne 0 ]]; then
    log_error "This installation script must be executed as root (using sudo)."
    exit 1
fi

INSTALL_LOG="/var/log/vms-install.log"
touch "$INSTALL_LOG"
exec > >(tee -ia "$INSTALL_LOG") 2>&1

ROLE="all"
TRANSCODER_IP="127.0.0.1"

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  --role <core|transcoder|all>   Deploy VMS Core, Standalone Transcoder, or both (all). Default: all"
    echo "  --transcoder-ip <IP>           IP address of Transcoder VM (required for 'core' role if remote). Default: 127.0.0.1"
    echo "  --help                         Show this help message"
    exit 1
}

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --role) ROLE="$2"; shift ;;
        --transcoder-ip) TRANSCODER_IP="$2"; shift ;;
        --help) usage ;;
        *) log_error "Unknown parameter passed: $1"; usage ;;
    esac
    shift
done

echo "=========================================================="
echo "      VMS AUTOMATED INSTALLATION - ROLE: ${ROLE^^}"
echo "      Configured Transcoder Target IP: $TRANSCODER_IP"
echo "      Log file: $INSTALL_LOG"
echo "=========================================================="

REPO_URL="https://github.com/Santhosh-Guptha/video-server.git"
CORE_BRANCH="feature/hybrid-transcoding"
TRANSCODER_BRANCH="feature/transcoding-server"

CORE_DIR="/opt/video-server"
TRANSCODER_DIR="/opt/vms-transcoder"

# Get Host IP address
CORE_IP=$(hostname -I | awk '{print $1}')
if [ -z "$CORE_IP" ]; then
    CORE_IP="127.0.0.1"
fi
log_info "Detected Host IP: $CORE_IP"

# 2. System updates and initial packages
log_info "Checking for background update locks (e.g. unattended-upgrades)..."
systemctl stop unattended-upgrades || true
while pgrep -f "unattended-upgr" >/dev/null || pgrep -f "apt-get" >/dev/null || pgrep -f "dpkg" >/dev/null; do
    log_warn "Apt/Dpkg lock is active. Waiting 5 seconds for other package tasks to complete..."
    sleep 5
done

log_info "1. Installing base packages (Git, Curl, Jq)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git curl wget jq build-essential net-tools unzip bc

# ────────────────────────────────────────────────────────
# VMS CORE DEPLOYMENT
# ────────────────────────────────────────────────────────
setup_core() {
    log_info "Stopping existing VMS Core services to release database locks..."
    systemctl stop video-backend.service || true
    systemctl stop video-frontend.service || true

    log_info "Cloning VMS Core codebase ($CORE_BRANCH)..."
    if [ -d "$CORE_DIR" ]; then
        log_warn "Target Core directory $CORE_DIR already exists. Pulling updates..."
        cd "$CORE_DIR"
        git fetch --all
        git checkout -f "$CORE_BRANCH"
        git reset --hard "origin/$CORE_BRANCH"
        cd - >/dev/null
    else
        git clone -b "$CORE_BRANCH" "$REPO_URL" "$CORE_DIR"
    fi

    log_info "Configuring VMS Core storage structure..."
    mkdir -p "$CORE_DIR/backend/data/recordings"
    mkdir -p "$CORE_DIR/backend/data/hls"
    chmod -R 777 "$CORE_DIR/backend/data"

    log_info "Installing VMS Core system requirements (Redis, PostgreSQL, Coturn)..."
    apt-get install -y ffmpeg python3-pip python3-venv redis-server postgresql postgresql-contrib coturn

    log_info "Configuring PostgreSQL database..."
    systemctl start postgresql
    systemctl enable postgresql

    DB_NAME="vms_db"
    DB_USER="vms_admin"
    DB_PASS="vms_secure_password"

    sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" || true
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;"
    sudo -u postgres psql -c "DROP USER IF EXISTS $DB_USER;"
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
    sudo -u postgres psql -d "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER;" &>/dev/null || true

    log_info "Configuring Redis cache..."
    systemctl start redis-server
    systemctl enable redis-server
    redis-cli flushall || true

    log_info "Installing and configuring MediaMTX..."
    MEDIAMTX_DIR="/opt/mediamtx"
    if [ ! -f "$MEDIAMTX_DIR/mediamtx" ]; then
        mkdir -p "$MEDIAMTX_DIR"
        LATEST_TAG=$(curl -s https://api.github.com/repos/bluenviron/mediamtx/releases/latest | jq -r '.tag_name')
        if [ -z "$LATEST_TAG" ] || [ "$LATEST_TAG" == "null" ]; then
            LATEST_TAG="v1.19.1"
        fi
        wget -q "https://github.com/bluenviron/mediamtx/releases/download/${LATEST_TAG}/mediamtx_${LATEST_TAG}_linux_amd64.tar.gz" -O "$MEDIAMTX_DIR/mediamtx.tar.gz"
        cd "$MEDIAMTX_DIR"
        tar -xzf mediamtx.tar.gz
        rm -f mediamtx.tar.gz
        cd - >/dev/null
    fi

    cp "$CORE_DIR/backend/app/mediamtx.yml" "$MEDIAMTX_DIR/mediamtx.yml"
    sed -i "s|^apiAddress:.*|apiAddress: ${CORE_IP}:9997|g" "$MEDIAMTX_DIR/mediamtx.yml" || true

    cat <<EOF > /etc/systemd/system/mediamtx.service
[Unit]
Description=MediaMTX RTSP WebRTC Media Server
After=network.target

[Service]
Type=simple
WorkingDirectory=$MEDIAMTX_DIR
ExecStart=$MEDIAMTX_DIR/mediamtx
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable mediamtx
    systemctl restart mediamtx

    log_info "Configuring TURN server (Coturn)..."
    sed -i 's/TURNSERVER_ENABLED=0/TURNSERVER_ENABLED=1/g' /etc/default/coturn || true
    echo "TURNSERVER_ENABLED=1" > /etc/default/coturn
    cat <<EOF > /etc/turnserver.conf
listening-port=3478
fingerprint
lt-cred-mech
user=admin:admin123
realm=vms-realm
simple-log
EOF
    systemctl enable coturn
    systemctl restart coturn

    log_info "Deploying VMS Core Backend..."
    VENV_PATH="/opt/video-backend-venv"
    rm -rf "$VENV_PATH"
    python3 -m venv "$VENV_PATH"
    "$VENV_PATH/bin/pip" install --upgrade pip
    "$VENV_PATH/bin/pip" install -r "$CORE_DIR/backend/requirements.txt"

    NODE_ID="node_$(hostname | tr '-' '_')_$(echo $CORE_IP | tr '.' '_')"
    cat <<EOF > "$CORE_DIR/backend/.env"
DATABASE_URL=postgresql+asyncpg://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME
REDIS_URL=redis://localhost:6379/0
MEDIAMTX_API_URL=http://${CORE_IP}:9997
MEDIAMTX_WEBRTC_URL=http://${CORE_IP}:8889
UPSTREAM_CAMERA_API_URL=https://iportal-poc.iviscloud.net/api/cameras/camera-videoserver
TURN_SERVER_URL=turn:${CORE_IP}:3478
TURN_SERVER_USERNAME=admin
TURN_SERVER_CREDENTIAL=admin123
NODE_ID=${NODE_ID}
EOF

    # Link Core to the target transcoder service IP
    log_info "Configuring cluster policy mapping for transcoder: http://${TRANSCODER_IP}:8500"
    sed -i "s|cloud_gateway_url:.*|cloud_gateway_url: http://${TRANSCODER_IP}:8500|g" "$CORE_DIR/backend/app/configs/cluster_policy.yaml"

    cd "$CORE_DIR/backend"
    "$VENV_PATH/bin/alembic" upgrade head
    cd - >/dev/null

    cat <<EOF > /etc/systemd/system/video-backend.service
[Unit]
Description=VMS Backend FastAPI Service
After=network.target postgresql.service redis-server.service

[Service]
WorkingDirectory=$CORE_DIR/backend
ExecStart=$VENV_PATH/bin/uvicorn app.main:app --host 0.0.0.0 --port 8005
Restart=always
RestartSec=5
User=root
Environment=PATH=$VENV_PATH/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=NODE_ID=${NODE_ID}

[Install]
WantedBy=multi-user.target
EOF
    systemctl enable video-backend
    systemctl restart video-backend

    log_info "Installing Node.js and building VMS Frontend..."
    NODE_OK=0
    if command -v node &>/dev/null; then
        NODE_VER=$(node -v | cut -d'v' -f2 | cut -d'.' -f1 || echo "0")
        if [ "$NODE_VER" -ge 18 ]; then
            NODE_OK=1
            log_info "Node.js version verified: v$NODE_VER"
        fi
    fi

    if [ "$NODE_OK" -eq 0 ]; then
        log_info "Node.js is missing or version is older than v18. Enforcing Node.js 18 installation..."
        apt-get purge -y nodejs npm nodejs-doc || true
        apt-get autoremove -y || true
        
        curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
        apt-get install -y nodejs
    fi

    cd "$CORE_DIR/frontend"
    npm install --no-audit --no-fund
    npm run build

    NPM_BIN=$(command -v npm)
    cat <<EOF > /etc/systemd/system/video-frontend.service
[Unit]
Description=VMS Frontend Vite Server
After=network.target video-backend.service

[Service]
User=root
WorkingDirectory=$CORE_DIR/frontend
ExecStart=$NPM_BIN run dev -- --host 0.0.0.0
Restart=always
RestartSec=5
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF
    systemctl enable video-frontend
    systemctl restart video-frontend
    cd - >/dev/null

    log_success "VMS Core components setup successfully!"
}

# ────────────────────────────────────────────────────────
# STANDALONE TRANSCODER DEPLOYMENT
# ────────────────────────────────────────────────────────
setup_transcoder() {
    log_info "Cloning VMS Transcoder codebase ($TRANSCODER_BRANCH)..."
    if [ -d "$TRANSCODER_DIR" ]; then
        log_warn "Target Transcoder directory $TRANSCODER_DIR already exists. Pulling updates..."
        cd "$TRANSCODER_DIR"
        git fetch --all
        git checkout -f "$TRANSCODER_BRANCH"
        git reset --hard "origin/$TRANSCODER_BRANCH"
        cd - >/dev/null
    else
        git clone -b "$TRANSCODER_BRANCH" "$REPO_URL" "$TRANSCODER_DIR"
    fi

    log_info "Installing Transcoder system requirements (FFmpeg, Python venv)..."
    apt-get install -y ffmpeg python3-pip python3-venv

    log_info "Deploying VMS Transcoder Service..."
    cd "$TRANSCODER_DIR/transcoding-server"
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install fastapi uvicorn httpx prometheus-client pyyaml pydantic

    cat <<EOF > /etc/systemd/system/vms-transcoder.service
[Unit]
Description=Hybrid Codec-Aware VMS Transcoding Platform
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$TRANSCODER_DIR/transcoding-server
ExecStart=$TRANSCODER_DIR/transcoding-server/venv/bin/uvicorn api.app:app --host 0.0.0.0 --port 8500 --workers 2
Restart=always
RestartSec=5
Environment=PYTHONPATH=$TRANSCODER_DIR/transcoding-server
Environment=TENANT_ID=tenant_default
Environment=NODE_ID=node_default

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable vms-transcoder
    systemctl restart vms-transcoder
    cd - >/dev/null

    log_success "VMS Transcoder components setup successfully!"
}

# Run deployment blocks
if [ "$ROLE" == "core" ]; then
    setup_core
elif [ "$ROLE" == "transcoder" ]; then
    setup_transcoder
elif [ "$ROLE" == "all" ]; then
    setup_transcoder
    setup_core
else
    log_error "Invalid role specified: $ROLE"
    usage
fi

log_success "Deployment process completed successfully!"
