#!/usr/bin/env bash
# ==============================================================================
# Unified VMS Stack - Automated Boostrap Installation & Deployment Script
# Target Platform: Ubuntu 20.04/22.04 LTS (Fresh VM)
# Design: Installs both VMS Core and Standalone Transcoder on a single host.
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
    log_error "This installation script must be executed as root (sudo)."
    exit 1
fi

INSTALL_LOG="/var/log/vms-install.log"
touch "$INSTALL_LOG"
exec > >(tee -ia "$INSTALL_LOG") 2>&1

echo "=========================================================="
echo "      VMS CORE & TRANSCODER AUTOMATED INSTALLATION"
echo "      Log file: $INSTALL_LOG"
echo "=========================================================="

REPO_URL="https://github.com/Santhosh-Guptha/video-server.git"
CORE_BRANCH="feature/hybrid-transcoding"
TRANSCODER_BRANCH="feature/transcoding-server"

CORE_DIR="/opt/video-server"
TRANSCODER_DIR="/opt/vms-transcoder"

# 2. System updates and initial packages
log_info "1/10. Installing Git and system build tools..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git curl wget jq build-essential net-tools unzip bc

# 3. Cloning codebases for Core and Transcoder
log_info "2/10. Cloning VMS codebase from Git..."

# Clone VMS Core
if [ -d "$CORE_DIR" ]; then
    log_warn "Target VMS Core directory $CORE_DIR already exists. Pulling updates..."
    cd "$CORE_DIR"
    git fetch --all
    git checkout -f "$CORE_BRANCH"
    git reset --hard "origin/$CORE_BRANCH"
    cd - >/dev/null
else
    git clone -b "$CORE_BRANCH" "$REPO_URL" "$CORE_DIR"
fi

# Clone VMS Transcoder (using feature/transcoding-server branch)
if [ -d "$TRANSCODER_DIR" ]; then
    log_warn "Target Transcoder directory $TRANSCODER_DIR already exists. Pulling updates..."
    cd "$TRANSCODER_DIR"
    git fetch --all
    git checkout -f "$TRANSCODER_BRANCH"
    git reset --hard "origin/$TRANSCODER_BRANCH"
    cd - >/dev/null
else
    # Create the transcoder directory and clone/checkout the branch
    git clone -b "$TRANSCODER_BRANCH" "$REPO_URL" "$TRANSCODER_DIR"
fi

# 4. Storage permissions
log_info "3/10. Configuring storage structure..."
mkdir -p "$CORE_DIR/backend/data/recordings"
mkdir -p "$CORE_DIR/backend/data/hls"
chmod -R 777 "$CORE_DIR/backend/data"

# 5. Installing system packages for Core & Transcoder
log_info "4/10. Installing VMS Core & Transcoder system requirements..."
apt-get install -y ffmpeg python3-pip python3-venv redis-server postgresql postgresql-contrib coturn

# Detect IP address
CORE_IP=$(hostname -I | awk '{print $1}')
if [ -z "$CORE_IP" ]; then
    CORE_IP="127.0.0.1"
fi
log_info "Detected Host IP: $CORE_IP"

# 6. Database Configuration
log_info "5/10. Configuring PostgreSQL database..."
systemctl start postgresql
systemctl enable postgresql

DB_NAME="vms_db"
DB_USER="vms_admin"
DB_PASS="vms_secure_password"

# Terminate active connections and recreate DB
sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" || true
sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;"
sudo -u postgres psql -c "DROP USER IF EXISTS $DB_USER;"
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
sudo -u postgres psql -d "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER;" &>/dev/null || true

# 7. Redis Configuration
log_info "6/10. Configuring Redis cache..."
systemctl start redis-server
systemctl enable redis-server
redis-cli flushall || true

# 8. MediaMTX Configuration
log_info "7/10. Installing and configuring MediaMTX..."
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

# MediaMTX systemd
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

# 9. Coturn Config
log_info "8/10. Configuring TURN server (Coturn)..."
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

# 10. Backend Deployment
log_info "9/10. Deploying VMS Core Backend..."
VENV_PATH="/opt/video-backend-venv"
rm -rf "$VENV_PATH"
python3 -m venv "$VENV_PATH"
"$VENV_PATH/bin/pip" install --upgrade pip
"$VENV_PATH/bin/pip" install -r "$CORE_DIR/backend/requirements.txt"

# Production Core .env
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

# Link Core cluster policy to local transcoder service on port 8500
sed -i "s|cloud_gateway_url:.*|cloud_gateway_url: http://127.0.0.1:8500|g" "$CORE_DIR/backend/app/configs/cluster_policy.yaml"

# Alembic migrations
cd "$CORE_DIR/backend"
"$VENV_PATH/bin/alembic" upgrade head
cd - >/dev/null

# Backend systemd service
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

# 11. Transcoding Server Service Setup
log_info "10/10. Deploying Standalone Transcoder Service..."
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
systemctl enable vms-transcoder
systemctl restart vms-transcoder
cd - >/dev/null

# 12. Frontend Deployment
log_info "Installing Node.js and building VMS Frontend..."
if ! command -v node &>/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - || true
    apt-get install -y nodejs
fi

cd "$CORE_DIR/frontend"
npm install --no-audit --no-fund
npm run build

# Frontend systemd service
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

# Reload services status
systemctl daemon-reload
systemctl restart mediamtx video-backend vms-transcoder video-frontend

log_success "VMS Core & Standalone Transcoder Stack successfully installed!"
log_info "VMS Core API is running at: http://${CORE_IP}:8005"
log_info "VMS Transcoder is running at: http://127.0.0.1:8500"
log_info "VMS Frontend Panel is running at: http://${CORE_IP}:5173"
log_info "Full installation log written to: $INSTALL_LOG"
