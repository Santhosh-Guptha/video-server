#!/usr/bin/env bash
# ── COMBINED VMS CORE SYSTEM SETUP SCRIPT ──────────────────────────────────
# Automates PostgreSQL, Redis, MediaMTX, Backend, and Frontend setups.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color
BLUE='\033[0;34m'
YELLOW='\033[0;33m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 1. Root check
if [ "$EUID" -ne 0 ]; then
  log_error "Please run this script as root (using sudo)."
  exit 1
fi

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
log_info "Project Directory: $PROJECT_DIR"

echo "=========================================================="
echo "      STARTING VMS CORE SYSTEM SETUP AND DEPLOYMENT"
echo "=========================================================="

# 2. System dependencies installation
log_info "1. Installing system dependencies..."
apt-get update -y
apt-get install -y python3-pip python3-venv ffmpeg redis-server postgresql postgresql-contrib curl jq wget bc nodejs git

# Install npm separately only if not already bundled (e.g. NodeSource nodejs already bundles npm)
if ! command -v npm &> /dev/null; then
    log_info "npm not found. Installing standalone npm..."
    apt-get install -y npm || log_warn "Failed to install standalone npm, proceeding..."
fi

# 3. PostgreSQL Database Configuration
log_info "2. Setting up PostgreSQL database and role..."
systemctl stop video-backend.service video-frontend.service mediamtx.service || true
systemctl start postgresql
systemctl enable postgresql

# Terminate active connections and drop/recreate database and role for a clean start
sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'vms_db' AND pid <> pg_backend_pid();" || true
sudo -u postgres psql -c "DROP DATABASE IF EXISTS vms_db;"
sudo -u postgres psql -c "DROP USER IF EXISTS vms_admin;"
sudo -u postgres psql -c "CREATE USER vms_admin WITH PASSWORD 'vms_secure_password';"
sudo -u postgres psql -c "CREATE DATABASE vms_db OWNER vms_admin;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE vms_db TO vms_admin;"

# 4. Redis Cache Configuration
log_info "3. Resetting and configuring Redis..."
systemctl start redis-server
systemctl enable redis-server
redis-cli flushall || true

# 5. MediaMTX RTSP Server setup
log_info "4. Installing and configuring MediaMTX..."
MEDIAMTX_DIR="/opt/mediamtx"
if [ ! -f "$MEDIAMTX_DIR/mediamtx" ]; then
    mkdir -p "$MEDIAMTX_DIR"
    log_info "Downloading latest stable MediaMTX release..."
    LATEST_TAG=$(curl -s https://api.github.com/repos/bluenviron/mediamtx/releases/latest | jq -r '.tag_name')
    if [ -z "$LATEST_TAG" ] || [ "$LATEST_TAG" == "null" ]; then
        LATEST_TAG="v1.9.0" # Fallback
    fi
    wget -q "https://github.com/bluenviron/mediamtx/releases/download/${LATEST_TAG}/mediamtx_${LATEST_TAG}_linux_amd64.tar.gz" -O "$MEDIAMTX_DIR/mediamtx.tar.gz"
    cd "$MEDIAMTX_DIR"
    tar -xzf mediamtx.tar.gz
    rm -f mediamtx.tar.gz
    cd "$PROJECT_DIR"
fi

# Write MediaMTX configuration
cat <<EOF > "$MEDIAMTX_DIR/mediamtx.yml"
paths:
  all:
    readUser:
    readPass:
    runOnDemand:
    runOnDemandStartTimeout: 10s
    runOnDemandCloseAfter: 10s
EOF

# Create MediaMTX service
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

# 6. VMS Backend Configuration
log_info "5. Configuring VMS Backend environment and database migrations..."
VENV_PATH="/opt/video-backend-venv"
rm -rf "$VENV_PATH"
python3 -m venv "$VENV_PATH"

"$VENV_PATH/bin/pip" install --upgrade pip
"$VENV_PATH/bin/pip" install -r "$PROJECT_DIR/backend/requirements.txt"

# Recreate .env with PostgreSQL configuration
PRIMARY_IP=$(hostname -I | awk '{print $1}')
cat <<EOF > "$PROJECT_DIR/backend/.env"
DATABASE_URL=postgresql+asyncpg://vms_admin:vms_secure_password@localhost:5432/vms_db
REDIS_URL=redis://localhost:6379/0
MEDIAMTX_API_URL=http://localhost:9997
MEDIAMTX_WEBRTC_URL=http://localhost:8889
UPSTREAM_CAMERA_API_URL=https://iportal-poc.iviscloud.net/api/cameras/camera-videoserver
TURN_SERVER_URL=turn:$PRIMARY_IP:3478
TURN_SERVER_USERNAME=admin
TURN_SERVER_CREDENTIAL=admin123
EOF

# Run database migrations
log_info "Running Alembic migrations..."
cd "$PROJECT_DIR/backend"
"$VENV_PATH/bin/alembic" upgrade head
cd "$PROJECT_DIR"

# Create video-backend systemd service
cat <<EOF > /etc/systemd/system/video-backend.service
[Unit]
Description=Camera Video Platform Backend FastAPI
After=network.target postgresql.target redis-server.target mediamtx.service

[Service]
User=root
WorkingDirectory=$PROJECT_DIR/backend
ExecStart=$VENV_PATH/bin/uvicorn app.main:app --host 0.0.0.0 --port 8005
Restart=always
RestartSec=5
Environment=PATH=$VENV_PATH/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

# 7. VMS Frontend Configuration
log_info "6. Setting up Frontend dependencies..."
cd "$PROJECT_DIR/frontend"
npm install --no-audit --no-fund
cd "$PROJECT_DIR"

# Create video-frontend systemd service
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

# 8. Start Services
log_info "7. Reloading systemd and starting all services..."
systemctl daemon-reload
systemctl enable mediamtx video-backend video-frontend
systemctl restart mediamtx video-backend video-frontend

echo "=========================================================="
log_success "All setups completed successfully!"
log_info "MediaMTX Server Status:  $(systemctl is-active mediamtx)"
log_info "VMS Backend Status:      $(systemctl is-active video-backend)"
log_info "VMS Frontend Status:     $(systemctl is-active video-frontend)"
log_info "UI Access:               http://localhost:5173"
echo "=========================================================="
