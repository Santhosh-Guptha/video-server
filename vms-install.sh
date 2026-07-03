#!/usr/bin/env bash
# ==============================================================================
# Enterprise VMS Stack - Automated Installation & Deployment Script
# Target Platform: Ubuntu 22.04 LTS (Fresh VM)
# Design: Idempotent, Production-Grade, Resilient
# Owner: Senior Linux DevOps, Video Streaming Architect & SRE
# ==============================================================================

# Exit immediately if a command exits with a non-zero status
# Treat unset variables as an error
# Prevent errors in a pipeline from being masked
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────────
# 1. CONSTANTS & DEFAULT CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────
INSTALL_DIR="/opt/video-server"
LOG_DIR="/opt/video-server/logs"
DATA_DIR="/opt/video-server/data"
if [[ -d "/mnt/storage" ]]; then
    REC_DIR="/mnt/storage"
else
    REC_DIR="/opt/video-server/data/recordings"
fi
VENV_DIR="/opt/video-backend-venv"
INSTALL_LOG="/var/log/vms-install.log"

DB_NAME="video_server"
DB_USER="video_user"
DB_PASS="video_pass_123"

TURN_PORT=3478
TURN_USER="admin"
TURN_PASS="admin123"

# Source code repository URL and branch
REPO_URL="https://github.com/Santhosh-Guptha/video-server.git"
BRANCH_NAME="feature/vms-streaming-redesign"

# Redirect stdout and stderr to both a log file and the console
# We check if we are running under sudo/root first to ensure we have permission to write to /var/log
if [[ "$EUID" -ne 0 ]]; then
    echo -e "\e[31m[FAIL] This installation script must be executed as root (sudo).\e[0m" >&2
    exit 1
fi

# Ensure log directory for installation exists
touch "$INSTALL_LOG"
exec > >(tee -ia "$INSTALL_LOG") 2>&1

# ──────────────────────────────────────────────────────────────────────────────
# 2. COLORIZED OUTPUT HELPERS
# ──────────────────────────────────────────────────────────────────────────────
print_ok() {
    echo -e "\e[32m[OK] $1\e[0m"
}

print_warn() {
    echo -e "\e[33m[WARN] $1\e[0m"
}

print_fail() {
    echo -e "\e[31m[FAIL] $1\e[0m" >&2
}

# ──────────────────────────────────────────────────────────────────────────────
# 3. PRE-INSTALLATION CHECKS
# ──────────────────────────────────────────────────────────────────────────────
echo "========================================================================"
echo " Starting Enterprise VMS Installation on Ubuntu 22.04 LTS"
echo " Log file: $INSTALL_LOG"
echo "========================================================================"

# Check OS version
if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    if [[ "$ID" != "ubuntu" || "$VERSION_ID" != "22.04" ]]; then
        print_warn "Target OS is $NAME $VERSION_ID. This script was designed for Ubuntu 22.04 LTS."
    else
        print_ok "Operating System verified: Ubuntu 22.04 LTS"
    fi
else
    print_warn "Could not verify operating system version."
fi

# ──────────────────────────────────────────────────────────────────────────────
# 4. SYSTEM UPDATES & REQUIRED PACKAGES
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n--- [1/10] System Updates & Packages ---"
export DEBIAN_FRONTEND=noninteractive

echo "Updating apt repositories..."
apt-get update -y

echo "Upgrading system packages (non-interactive)..."
apt-get upgrade -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold"

echo "Installing required dependencies..."
apt-get install -y \
    curl \
    wget \
    git \
    jq \
    net-tools \
    unzip \
    python3 \
    python3-pip \
    python3-venv \
    build-essential \
    ffmpeg

print_ok "Required packages installed successfully."

# Verify Video Stack
echo -e "\n--- [2/10] Verifying Video Stack ---"
if command -v ffmpeg &>/dev/null && command -v ffprobe &>/dev/null; then
    FFMPEG_VER=$(ffmpeg -version | head -n 1)
    FFPROBE_VER=$(ffprobe -version | head -n 1)
    print_ok "FFmpeg verified: $FFMPEG_VER"
    print_ok "FFprobe verified: $FFPROBE_VER"
else
    print_fail "FFmpeg or FFprobe installation check failed."
    exit 1
fi

# ──────────────────────────────────────────────────────────────────────────────
# 5. STORAGE DIRECTORIES & PERMISSIONS
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n--- [3/10] Creating Storage Structure ---"
mkdir -p "$INSTALL_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$DATA_DIR"
mkdir -p "$REC_DIR"

chown -R root:root "$INSTALL_DIR"
chmod -R 777 "$DATA_DIR"
chmod -R 777 "$LOG_DIR"
print_ok "Storage directories created and permissions applied."

# ──────────────────────────────────────────────────────────────────────────────
# 6. MEDIAMTX INSTALLATION & CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n--- [4/10] Installing MediaMTX ---"
MEDIAMTX_DIR="/opt/mediamtx"

if [[ ! -f "$MEDIAMTX_DIR/mediamtx" ]]; then
    mkdir -p "$MEDIAMTX_DIR"
    echo "Fetching latest stable MediaMTX release tag..."
    LATEST_TAG=$(curl -s https://api.github.com/repos/bluenviron/mediamtx/releases/latest | jq -r '.tag_name')
    if [[ -z "$LATEST_TAG" || "$LATEST_TAG" == "null" ]]; then
        LATEST_TAG="v1.9.0"
        print_warn "Could not fetch latest release dynamically, falling back to $LATEST_TAG"
    else
        print_ok "Latest MediaMTX release found: $LATEST_TAG"
    fi
    
    echo "Downloading MediaMTX..."
    wget -q "https://github.com/bluenviron/mediamtx/releases/download/${LATEST_TAG}/mediamtx_${LATEST_TAG}_linux_amd64.tar.gz" -O "$MEDIAMTX_DIR/mediamtx.tar.gz"
    cd "$MEDIAMTX_DIR"
    tar -xzf mediamtx.tar.gz
    rm -f mediamtx.tar.gz
    cd - >/dev/null
    print_ok "MediaMTX downloaded and extracted."
else
    print_ok "MediaMTX binary already exists at $MEDIAMTX_DIR/mediamtx."
fi

# Configure MediaMTX
echo "Writing MediaMTX configuration..."
cat <<EOF > "$MEDIAMTX_DIR/mediamtx.yml"
# MediaMTX Configuration - Production Optimized
api: yes
apiAddress: :9997
logLevel: warn

metrics: yes
metricsAddress: :9998

rtsp: yes
rtspAddress: :8554
protocols: [udp, tcp]

rtmp: yes
rtmpAddress: :1935

webrtc: yes
webrtcAddress: :8889
webrtcLocalUDPAddress: :8189
webrtcLocalTCPAddress: :8189
webrtcICEServers2:
  - url: stun:stun.l.google.com:19302

hls: yes
hlsAddress: :8080
hlsVariant: lowLatency
hlsSegmentCount: 8
hlsSegmentDuration: 1s
hlsPartDuration: 200ms
hlsAllowOrigin: "*"

pathDefaults:
  sourceProtocol: tcp
  record: yes
  recordPath: $REC_DIR/%path/%Y-%m-%d/%Y%m%d_%H%M%S_live
  recordFormat: fmp4
  recordPartDuration: 1s
  recordSegmentDuration: 60s
  runOnRecordSegmentComplete: /bin/bash $INSTALL_DIR/backend/app/segment_hook.sh "\$MTX_PATH" "\$MTX_SEGMENT_PATH"

paths:
  all_others:
    source: publisher
    record: yes
EOF

# Create MediaMTX systemd service
cat <<EOF > /etc/systemd/system/mediamtx.service
[Unit]
Description=MediaMTX RTSP WebRTC Media Server
After=network.target

[Service]
WorkingDirectory=$MEDIAMTX_DIR
ExecStart=$MEDIAMTX_DIR/mediamtx
Restart=always
RestartSec=5
User=root
Environment=BACKEND_WEBHOOK_URL=http://localhost:8005

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable mediamtx
systemctl restart mediamtx
print_ok "MediaMTX service configured and started."

# ──────────────────────────────────────────────────────────────────────────────
# 7. REDIS INSTALLATION & CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n--- [5/10] Installing Redis Server ---"
apt-get install -y redis-server
systemctl enable redis-server

# Configure persistence in redis.conf if not already enabled
if grep -q "^appendonly no" /etc/redis/redis.conf; then
    sed -i 's/^appendonly no/appendonly yes/g' /etc/redis/redis.conf
    systemctl restart redis-server
    print_ok "Redis persistence enabled (AOF)."
elif grep -q "^appendonly yes" /etc/redis/redis.conf; then
    print_ok "Redis persistence already enabled."
else
    # Append if not present at all
    echo "appendonly yes" >> /etc/redis/redis.conf
    systemctl restart redis-server
    print_ok "Redis persistence added."
fi

# Ensure Redis is running
echo "Waiting for Redis to start..."
for i in {1..10}; do
    if redis-cli ping | grep -q "PONG"; then
        print_ok "Redis service is active and responsive."
        break
    fi
    sleep 1
done

# ──────────────────────────────────────────────────────────────────────────────
# 8. POSTGRESQL INSTALLATION & DATABASE CREATION
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n--- [6/10] Installing PostgreSQL ---"
apt-get install -y postgresql postgresql-contrib
systemctl enable postgresql
systemctl start postgresql

# Wait for PostgreSQL to start
echo "Waiting for PostgreSQL to start..."
for i in {1..10}; do
    if pg_isready &>/dev/null; then
        break
    fi
    sleep 1
done

# Create Database and User (Idempotent)
echo "Configuring database..."
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
    print_ok "Database user $DB_USER created."
else
    # Update password in case of rerun/change
    sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASS';"
    print_ok "Database user $DB_USER already exists (password verified)."
fi

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
    print_ok "Database $DB_NAME created with owner $DB_USER."
else
    sudo -u postgres psql -c "ALTER DATABASE $DB_NAME OWNER TO $DB_USER;"
    print_ok "Database $DB_NAME already exists (owner verified)."
fi

# Ensure public schema privileges are set for migrations (PG 15+ compatibility)
sudo -u postgres psql -d "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER;" &>/dev/null || true
print_ok "Database permissions granted."

# ──────────────────────────────────────────────────────────────────────────────
# 9. COTURN INSTALLATION & CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n--- [7/10] Installing Coturn TURN Server ---"
apt-get install -y coturn

# Enable service in /etc/default/coturn
sed -i 's/TURNSERVER_ENABLED=0/TURNSERVER_ENABLED=1/g' /etc/default/coturn || true
echo "TURNSERVER_ENABLED=1" > /etc/default/coturn

# Idempotent TURN credentials recovery or generation
if [[ -f /etc/turnserver.conf ]]; then
    EXISTING_USER=$(grep -E "^user=" /etc/turnserver.conf | cut -d= -f2 | cut -d: -f1 || true)
    EXISTING_PASS=$(grep -E "^user=" /etc/turnserver.conf | cut -d= -f2 | cut -d: -f2 || true)
    if [[ -n "$EXISTING_USER" && -n "$EXISTING_PASS" ]]; then
        TURN_USER="$EXISTING_USER"
        TURN_PASS="$EXISTING_PASS"
        print_ok "Retained existing Coturn credentials from turnserver.conf"
    fi
fi

# Generate custom secure credentials if using default config
if [[ "$TURN_USER" == "admin" ]]; then
    TURN_USER="vms_user_$(openssl rand -hex 3)"
fi
if [[ "$TURN_PASS" == "admin123" ]]; then
    TURN_PASS=$(openssl rand -hex 8)
fi

# Write turnserver.conf
cat <<EOF > /etc/turnserver.conf
listening-port=$TURN_PORT
fingerprint
lt-cred-mech
user=$TURN_USER:$TURN_PASS
realm=vms-realm
simple-log
EOF

systemctl daemon-reload
systemctl enable coturn
systemctl restart coturn
print_ok "Coturn TURN server started on port $TURN_PORT (STUN/TURN active)."

# ──────────────────────────────────────────────────────────────────────────────
# 10. BACKEND DEPLOYMENT
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n--- [8/10] Deploying Backend Service ---"

# Deploy codebase from current folder (if script run in git clone) or clone from git
if [[ -f "./backend/app/main.py" && -f "./frontend/package.json" ]]; then
    print_ok "Detected script running inside source codebase. Copying to $INSTALL_DIR..."
    mkdir -p "$INSTALL_DIR"
    if command -v rsync &>/dev/null; then
        rsync -a --delete --exclude="venv" --exclude="venv_win" --exclude="node_modules" --exclude=".git" --exclude="data/recordings" ./ "$INSTALL_DIR/"
    else
        cp -r ./ "$INSTALL_DIR/"
    fi
elif [[ -d "$INSTALL_DIR/.git" ]]; then
    print_ok "Existing git repository detected at $INSTALL_DIR. Pulling latest updates..."
    cd "$INSTALL_DIR"
    git fetch --all
    git reset --hard "origin/$BRANCH_NAME" || git reset --hard "$BRANCH_NAME"
    cd - >/dev/null
fi

# Ensure storage directories are restored/available after codebase deployment
mkdir -p "$LOG_DIR"
mkdir -p "$DATA_DIR"
mkdir -p "$REC_DIR"
chown -R root:root "$INSTALL_DIR"
chmod -R 777 "$DATA_DIR"
chmod -R 777 "$LOG_DIR"


# Setup Virtual Environment
if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt"

# Read existing .env values if they exist to maintain configuration across runs
UPSTREAM_URL="https://iportal-poc.iviscloud.net/api/cameras/camera-videoserver"
TURN_SERVER_URL_VAL=""
if [[ -f "$INSTALL_DIR/backend/.env" ]]; then
    EXISTING_UPSTREAM=$(grep -E "^UPSTREAM_CAMERA_API_URL=" "$INSTALL_DIR/backend/.env" | cut -d'=' -f2- || true)
    if [[ -n "$EXISTING_UPSTREAM" ]]; then
        UPSTREAM_URL="$EXISTING_UPSTREAM"
    fi

    EXISTING_TURN_URL=$(grep -E "^TURN_SERVER_URL=" "$INSTALL_DIR/backend/.env" | cut -d'=' -f2- || true)
    if [[ -n "$EXISTING_TURN_URL" ]]; then
        TURN_SERVER_URL_VAL="$EXISTING_TURN_URL"
    fi

    EXISTING_TURN_USER=$(grep -E "^TURN_SERVER_USERNAME=" "$INSTALL_DIR/backend/.env" | cut -d'=' -f2- || true)
    if [[ -n "$EXISTING_TURN_USER" ]]; then
        TURN_USER="$EXISTING_TURN_USER"
    fi

    EXISTING_TURN_PASS=$(grep -E "^TURN_SERVER_CREDENTIAL=" "$INSTALL_DIR/backend/.env" | cut -d'=' -f2- || true)
    if [[ -n "$EXISTING_TURN_PASS" ]]; then
        TURN_PASS="$EXISTING_TURN_PASS"
    fi
fi

# Auto-detect IP for new installs to avoid client-side localhost resolution errors
if [[ -z "$TURN_SERVER_URL_VAL" ]]; then
    SERVER_IP=$(hostname -I | awk '{print $1}')
    if [[ -z "$SERVER_IP" ]]; then
        SERVER_IP="127.0.0.1"
    fi
    TURN_SERVER_URL_VAL="turn:$SERVER_IP:$TURN_PORT"
fi

# Write Production .env File
cat <<EOF > "$INSTALL_DIR/backend/.env"
DATABASE_URL=postgresql+asyncpg://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME
REDIS_URL=redis://127.0.0.1:6379/0
MEDIAMTX_API_URL=http://127.0.0.1:9997
MEDIAMTX_WEBRTC_URL=http://127.0.0.1:8889
STUN_SERVERS=["stun:stun.l.google.com:19302"]
TURN_SERVER_URL=$TURN_SERVER_URL_VAL
TURN_SERVER_USERNAME=$TURN_USER
TURN_SERVER_CREDENTIAL=$TURN_PASS
UPSTREAM_CAMERA_API_URL=$UPSTREAM_URL
LIVE_STREAM_PROFILE=HD
ENABLE_ADAPTIVE_PROFILE=false
PLAYBACK_PROFILE=HD
INDEXER_INTERVAL_SECONDS=600
RECORDING_DIR=$REC_DIR
EOF

# Run database migrations
cd "$INSTALL_DIR/backend"
if [[ -f "alembic.ini" ]]; then
    echo "Running Alembic database migrations..."
    "$VENV_DIR/bin/alembic" upgrade head || print_warn "Alembic migrations failed. Relying on startup schema auto-generation."
fi

# Find system paths for systemd service file
UVICORN_BIN="$VENV_DIR/bin/uvicorn"

# Create Backend Systemd Service
cat <<EOF > /etc/systemd/system/video-backend.service
[Unit]
Description=VMS Backend FastAPI Service
After=network.target postgresql.service redis-server.service

[Service]
WorkingDirectory=$INSTALL_DIR/backend
ExecStart=$UVICORN_BIN app.main:app --host 0.0.0.0 --port 8005
Restart=always
RestartSec=5
User=root
Environment=PATH=$VENV_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable video-backend
systemctl restart video-backend
print_ok "Backend FastAPI service configured and started."

# ──────────────────────────────────────────────────────────────────────────────
# 11. FRONTEND DEPLOYMENT
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n--- [9/10] Deploying Frontend Service ---"

# Install NodeSource Node.js 18
if ! command -v node &>/dev/null; then
    echo "Installing Node.js 18..."
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - || true
    apt-get install -y nodejs || {
        print_warn "NodeSource installation failed, falling back to distro nodejs/npm..."
        apt-get install -y nodejs npm
    }
fi

NODE_VER=$(node -v)
print_ok "Node.js verified: $NODE_VER"

# Build Frontend React application
cd "$INSTALL_DIR/frontend"
echo "Installing npm packages..."
npm install --no-audit --no-fund

echo "Building React application for production..."
npm run build || {
    print_warn "npm run build failed. Retrying with type check bypass..."
    npx vite build || print_fail "Vite production compilation failed."
}

# Discover npm path for service file
NPM_BIN=$(command -v npm)

# Write Frontend systemd preview service
cat <<EOF > /etc/systemd/system/video-frontend.service
[Unit]
Description=VMS Frontend Preview Service
After=network.target video-backend.service

[Service]
WorkingDirectory=$INSTALL_DIR/frontend
ExecStart=$NPM_BIN run preview -- --host 0.0.0.0 --port 5173
Restart=always
RestartSec=5
User=root
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable video-frontend
systemctl restart video-frontend
print_ok "Frontend Vite server configured and started."

# ──────────────────────────────────────────────────────────────────────────────
# 12. INTEGRATION VALIDATION & STATUS REPORTS
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n--- [10/10] Verifying Stack Integration ---"
echo "Allowing services 5 seconds to warm up..."
sleep 5

STATUS_BACKEND="FAIL"
STATUS_MEDIAMTX="FAIL"
STATUS_REDIS="FAIL"
STATUS_DB="FAIL"
STATUS_COTURN="FAIL"
STATUS_STORAGE="FAIL"

# 1. Validate Backend API
if curl -s -f http://127.0.0.1:8005/health &>/dev/null; then
    STATUS_BACKEND="OK"
fi

# 2. Validate MediaMTX API
if curl -s -f http://127.0.0.1:9997/v3/config/paths/list &>/dev/null; then
    STATUS_MEDIAMTX="OK"
fi

# 3. Validate Redis
if redis-cli ping | grep -q "PONG"; then
    STATUS_REDIS="OK"
fi

# 4. Validate PostgreSQL
if PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" &>/dev/null; then
    STATUS_DB="OK"
fi

# 5. Validate Coturn (checking both TCP and UDP ports)
if ss -tulun | grep -E ":$TURN_PORT\b" &>/dev/null; then
    STATUS_COTURN="OK"
fi

# 6. Validate Storage
if [[ -d "$REC_DIR" ]]; then
    STATUS_STORAGE="OK"
fi

# Generate reports
REPORT_PATH="$INSTALL_DIR/install-report.txt"
SUMMARY_PATH="$INSTALL_DIR/deployment-summary.txt"

# Get current server IP address
SERVER_IP=$(hostname -I | awk '{print $1}')
if [[ -z "$SERVER_IP" ]]; then
    SERVER_IP="YOUR_SERVER_IP"
fi

cat <<EOF > "$REPORT_PATH"
======================================================================
                 VMS INSTALLATION VERIFICATION REPORT
======================================================================
Generated on: $(date)
Target Node : $SERVER_IP
----------------------------------------------------------------------
Backend API Proxy      : [$STATUS_BACKEND]
MediaMTX Config API    : [$STATUS_MEDIAMTX]
Redis Cache Service    : [$STATUS_REDIS]
PostgreSQL Database    : [$STATUS_DB]
Coturn TURN Server     : [$STATUS_COTURN]
Storage Structure      : [$STATUS_STORAGE]
----------------------------------------------------------------------
Overall Status         : $([[ "$STATUS_BACKEND" == "OK" && "$STATUS_MEDIAMTX" == "OK" && "$STATUS_REDIS" == "OK" && "$STATUS_DB" == "OK" ]] && echo "OK" || echo "DEGRADED")
======================================================================
EOF

cat <<EOF > "$SUMMARY_PATH"
======================================================================
                        VMS DEPLOYMENT SUMMARY
======================================================================
Admin Panel UI         : http://$SERVER_IP:5173/
Backend REST API       : http://$SERVER_IP:8005/
Backend Docs           : http://$SERVER_IP:8005/docs
MediaMTX API           : http://$SERVER_IP:9997/v3/config/global
MediaMTX Metrics       : http://$SERVER_IP:9998/metrics
TURN Server Endpoint   : turn:$SERVER_IP:$TURN_PORT
TURN Credentials       : User: $TURN_USER | Pass: $TURN_PASS
Database Connection    : postgresql://$DB_USER:***@localhost:5432/$DB_NAME
Storage Directory      : $DATA_DIR
Recordings Directory   : $REC_DIR
======================================================================
EOF

# Copy reports to local execution directory for easy visibility
cp "$REPORT_PATH" ./install-report.txt || true
cp "$SUMMARY_PATH" ./deployment-summary.txt || true

# Print Validation Results to Screen
echo -e "\n========================================================================"
if [[ "$STATUS_BACKEND" == "OK" && "$STATUS_MEDIAMTX" == "OK" && "$STATUS_REDIS" == "OK" && "$STATUS_DB" == "OK" ]]; then
    print_ok "VMS STACK INSTALLED AND VERIFIED SUCCESSFULLY!"
else
    print_warn "VMS STACK INSTALLED WITH DEGRADED STATUS. PLEASE CHECK LOGS."
fi
echo "========================================================================"
cat "$REPORT_PATH"
echo "========================================================================"
echo "Detailed installation log written to: $INSTALL_LOG"
echo "Deployment summary report written to : ./deployment-summary.txt"
echo "========================================================================"
