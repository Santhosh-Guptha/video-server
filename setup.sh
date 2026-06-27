#!/usr/bin/env bash
# ── AUTOMATED UNIFIED SETUP AND DEPLOYMENT SCRIPT ──────────────────────────
# Supports core (VM 2), transcoder (VM 1), or all (hybrid developer) setups.

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

# Default configurations
ROLE="all"
TRANSCODER_IP="127.0.0.1"
CORE_IP=""

# Parse options
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  --role <core|transcoder|all>   Deploy Core (VM2), Standalone Transcoder (VM1), or All (hybrid/dev). Default: all"
    echo "  --transcoder-ip <IP>           IP address of Transcoder VM (required for 'core' role if VM1 is remote)"
    echo "  --core-ip <IP>                 IP address of VMS Core VM (required for 'transcoder' role to allow RTSP push)"
    echo "  --help                         Show this help message"
    exit 1
}

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --role) ROLE="$2"; shift ;;
        --transcoder-ip) TRANSCODER_IP="$2"; shift ;;
        --core-ip) CORE_IP="$2"; shift ;;
        --help) usage ;;
        *) log_error "Unknown parameter passed: $1"; usage ;;
    esac
    shift
done

# Validate IP addresses
if [ -z "$CORE_IP" ]; then
    # Auto-detect primary network IP
    CORE_IP=$(hostname -I | awk '{print $1}')
fi

echo "=========================================================="
echo "          VMS DEPLOYMENT AUTOMATION - ROLE: ${ROLE^^}"
echo "=========================================================="
log_info "Detected Core VM IP: $CORE_IP"
log_info "Configured Transcoder VM IP: $TRANSCODER_IP"

# ────────────────────────────────────────────────────────
# TRANSCODER DEPLOYMENT (VM 1)
# ────────────────────────────────────────────────────────
setup_transcoder() {
    log_info "Starting Transcoding Service deployment (VM 1)..."
    
    if [ ! -d "$PROJECT_DIR/transcoding-server" ]; then
        log_error "transcoding-server directory not found."
        log_error "Please ensure you have checked out the correct branch: feature/transcoding-server"
        exit 1
    fi

    log_info "1. Installing Transcoder system requirements..."
    apt-get update -y
    apt-get install -y ffmpeg python3-pip python3-venv build-essential netcat-openbsd

    # GPU Driver check
    if command -v nvidia-smi &> /dev/null; then
        log_success "NVIDIA Driver detected. GPU acceleration available."
    else
        log_warn "No NVIDIA driver detected. Operating in CPU fallback mode (libx264)."
    fi

    # Service Directory Setup
    log_info "2. Setting up service directories..."
    mkdir -p /opt/vms-transcoder
    cp -r "$PROJECT_DIR/transcoding-server" /opt/vms-transcoder/
    
    cd /opt/vms-transcoder/transcoding-server
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install fastapi uvicorn httpx prometheus-client pyyaml pydantic pytest pytest-asyncio

    # Generate systemd Service File
    log_info "3. Creating systemd service file..."
    cat <<EOF > /etc/systemd/system/vms-transcoder.service
[Unit]
Description=Hybrid Codec-Aware VMS Transcoding Platform
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/vms-transcoder/transcoding-server
ExecStart=/opt/vms-transcoder/transcoding-server/venv/bin/uvicorn api.app:app --host 0.0.0.0 --port 8500 --workers 2
Restart=always
RestartSec=5
Environment=PYTHONPATH=/opt/vms-transcoder/transcoding-server
Environment=TENANT_ID=tenant_default
Environment=NODE_ID=node_default

[Install]
WantedBy=multi-user.target
EOF

    # Start service
    log_info "4. Starting and enabling vms-transcoder service..."
    systemctl daemon-reload
    systemctl enable vms-transcoder
    systemctl restart vms-transcoder
    
    log_success "Transcoder service started successfully!"
}

# ────────────────────────────────────────────────────────
# VMS CORE DEPLOYMENT (VM 2)
# ────────────────────────────────────────────────────────
setup_core() {
    log_info "Starting VMS Core deployment (VM 2)..."
    
    if [ ! -d "$PROJECT_DIR/backend" ] || [ ! -d "$PROJECT_DIR/frontend" ]; then
        log_error "backend or frontend directory not found."
        log_error "Please ensure you have checked out the correct branch: feature/hybrid-transcoding"
        exit 1
    fi

    log_info "1. Installing VMS Core system dependencies..."
    apt-get update -y
    apt-get install -y python3-pip python3-venv ffmpeg redis-server postgresql postgresql-contrib curl jq wget bc nodejs git
    
    if ! command -v npm &> /dev/null; then
        apt-get install -y npm || log_warn "Failed to install npm, proceeding..."
    fi

    # Database config
    log_info "2. Setting up PostgreSQL database..."
    systemctl stop video-backend.service video-frontend.service mediamtx.service || true
    systemctl start postgresql
    systemctl enable postgresql

    sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'vms_db' AND pid <> pg_backend_pid();" || true
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS vms_db;"
    sudo -u postgres psql -c "DROP USER IF EXISTS vms_admin;"
    sudo -u postgres psql -c "CREATE USER vms_admin WITH PASSWORD 'vms_secure_password';"
    sudo -u postgres psql -c "CREATE DATABASE vms_db OWNER vms_admin;"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE vms_db TO vms_admin;"

    # Redis config
    log_info "3. Configuring Redis..."
    systemctl start redis-server
    systemctl enable redis-server
    redis-cli flushall || true

    # MediaMTX setup
    log_info "4. Configuring MediaMTX..."
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
        cd "$PROJECT_DIR"
    fi

    # Write proper MediaMTX configuration
    cp "$PROJECT_DIR/backend/app/mediamtx.yml" "$MEDIAMTX_DIR/mediamtx.yml"
    
    # Configure MediaMTX API to bind to Core IP
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

    # VMS Backend Config
    log_info "5. Configuring VMS Backend..."
    VENV_PATH="/opt/video-backend-venv"
    rm -rf "$VENV_PATH"
    python3 -m venv "$VENV_PATH"
    "$VENV_PATH/bin/pip" install --upgrade pip
    "$VENV_PATH/bin/pip" install -r "$PROJECT_DIR/backend/requirements.txt"

    # Generate backend environment variables (.env) with unique NODE_ID
    NODE_ID="node_$(hostname | tr '-' '_')_$(echo $CORE_IP | tr '.' '_')"
    cat <<EOF > "$PROJECT_DIR/backend/.env"
DATABASE_URL=postgresql+asyncpg://vms_admin:vms_secure_password@localhost:5432/vms_db
REDIS_URL=redis://localhost:6379/0
MEDIAMTX_API_URL=http://${CORE_IP}:9997
MEDIAMTX_WEBRTC_URL=http://${CORE_IP}:8889
UPSTREAM_CAMERA_API_URL=https://iportal-poc.iviscloud.net/api/cameras/camera-videoserver
TURN_SERVER_URL=turn:${CORE_IP}:3478
TURN_SERVER_USERNAME=admin
TURN_SERVER_CREDENTIAL=admin123
NODE_ID=${NODE_ID}
EOF

    # Configure cluster policy mapping to standalone transcoder
    sed -i "s|cloud_gateway_url:.*|cloud_gateway_url: http://${TRANSCODER_IP}:8500|g" "$PROJECT_DIR/backend/app/configs/cluster_policy.yaml"

    # Alembic migrations
    log_info "Running Alembic migrations..."
    cd "$PROJECT_DIR/backend"
    "$VENV_PATH/bin/alembic" upgrade head
    cd "$PROJECT_DIR"

    # Create backend systemd service
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
Environment=NODE_ID=${NODE_ID}

[Install]
WantedBy=multi-user.target
EOF

    # VMS Frontend Config
    log_info "6. Setting up Frontend dependencies..."
    cd "$PROJECT_DIR/frontend"
    npm install --no-audit --no-fund
    cd "$PROJECT_DIR"

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

    # Restart Services
    log_info "7. Reloading systemd and starting core services..."
    systemctl daemon-reload
    systemctl enable mediamtx video-backend video-frontend
    systemctl restart mediamtx video-backend video-frontend

    log_success "VMS Core deployment completed successfully!"
}

# ────────────────────────────────────────────────────────
# MAIN ROUTER
# ────────────────────────────────────────────────────────
case $ROLE in
    transcoder)
        setup_transcoder
        ;;
    core)
        setup_core
        ;;
    all)
        # Deploy both locally (hybrid mode)
        setup_transcoder
        setup_core
        ;;
    *)
        log_error "Invalid role specified: $ROLE"
        usage
        ;;
esac

echo "=========================================================="
log_success "Automated configuration process finished!"
echo "=========================================================="
