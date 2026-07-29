#!/bin/bash

# ==============================================================================
# VMS ALL-IN-ONE STANDALONE DEPLOYER & CONFIGURATOR
# ==============================================================================
# Usage:
#   1. Configure parameters in Section 1 & 2 below in this single file.
#   2. Run: sudo bash deploy_vms.sh
# ==============================================================================

# --- [ 1. CONFIGURATION PROPERTIES ] -----------------------------------------
APP_NAME="camera-video-platform"
DATABASE_URL="sqlite+aiosqlite:///./data/app.db"
REDIS_URL="redis://127.0.0.1:6379/0"

UPSTREAM_CAMERA_API_URL="https://iportal.iviscloud.net/api/cameras/camera-videoserver"
UPSTREAM_TIMEOUT_SECONDS=10.0
UPSTREAM_SYNC_INTERVAL_MINUTES=5

MEDIAMTX_API_URL="http://127.0.0.1:9997"
MEDIAMTX_WEBRTC_URL="http://127.0.0.1:8889"
STUN_SERVERS='["stun:stun.l.google.com:19302"]'
TURN_SERVER_URL=""                       # Auto-detects system IP if blank (turn:IP:3478)
TURN_SERVER_USERNAME="admin"
TURN_SERVER_CREDENTIAL="admin123"
MEDIAMTX_PATCH_ONLY=true
ALLOW_DELETE_ADD_RECONFIGURATION=false

FFMPEG_PATH="ffmpeg"
RECORDING_DIR="./data/recordings"        # Set custom path e.g. "/mnt/storage"
HLS_DIR="./data/hls"
SEGMENT_TIME_SECONDS=60

MAX_SUBSCRIBERS_PER_STREAM=200
MAX_WEBRTC_SESSIONS_PER_CAMERA=100
ENABLE_WEBRTC=true
ENABLE_HLS_FALLBACK=true
WEBRTC_CONNECTION_TIMEOUT_SECONDS=10

UI_POLL_SECONDS=5
SCHEDULER_INTERVAL_SECONDS=10
RECOVERY_INTERVAL_SECONDS=300
CLEANUP_INTERVAL_SECONDS=600
INDEXER_INTERVAL_SECONDS=600

EDGE_RECEIVER_HOST="0.0.0.0"
EDGE_RECEIVER_PORT=9999
EDGE_RECEIVER_ENABLED=true
ALLOW_UNKNOWN_EDGE_DEVICES=false
STRICT_CAMERA_VALIDATION=true
ENABLE_EDGE_PUSH=true
EDGE_PUSH_PRIORITY=true
EDGE_PUSH_HEARTBEAT_TIMEOUT_SECONDS=120
EDGE_PUSH_CHECK_INTERVAL_SECONDS=30

ENABLE_RTSP_HEALTH_CHECK=true
CAMERA_PING_INTERVAL_SECONDS=120
CAMERA_PING_TIMEOUT_SECONDS=5
CAMERA_PING_MAX_CONCURRENT=10

ENABLE_H265_TRANSCODING=true
MAX_ACTIVE_TRANSCODERS=10
TRANSCODER_VCODEC="libx264"
TRANSCODER_PRESET="ultrafast"
TRANSCODER_TUNE="zerolatency"
TRANSCODER_GRACE_PERIOD_SECONDS=60

ENABLE_RECORDING=true
RECORD_FALLBACK_TO_NORMAL=true
RECORD_MOBILE=false

PREFERRED_PROFILE="HD"
LIVE_STREAM_FALLBACK=true
ENABLE_ADAPTIVE_PROFILE=true
FOCUS_VIEW_PROFILE="HD"
GRID_VIEW_PROFILE="NORMAL"
MOBILE_VIEW_PROFILE="MOBILE"

PLAYBACK_ALLOW_NORMAL_FALLBACK=true
PLAYBACK_ALLOW_MOBILE_FALLBACK=false
PLAYBACK_SPEEDS='[0.5, 1.0, 2.0, 4.0, 8.0]'
ENABLE_RETENTION=true
DEFAULT_RETENTION_DAYS=30
ENABLE_LOW_DISK_EVICTION=true
LOW_DISK_SPACE_THRESHOLD_GB=5.0
TARGET_FREE_SPACE_GB=10.0

TIMELINE_CACHE_SECONDS=60
TIMELINE_MERGE_THRESHOLD_SECONDS=5
TIMELINE_DEFAULT_ZOOM="24h"

ENABLE_DEVICE_CONFIG=false
ENABLE_LOCAL_TRANSCODE=false

ENABLE_SD_CARD_ON_DEMAND=true
SD_CARD_ON_DEMAND_RETENTION_SECONDS=3600

# --- [ 2. DEPLOYMENT & RESET TOGGLES ] ---------------------------------------
ENABLE_ADMIN_PASSWORD_PROTECTION=true     # Set true to enforce hashed password authentication
CLEAN_DATABASE=true                      # Wipe SQLite database on deploy
CLEAN_RECORDINGS=true                    # Wipe video recordings & HLS on deploy
FLUSH_REDIS=true                         # Flush Redis cache on deploy
REINSTALL_VENV=true                      # Recreate Python venv
BRANCH_NAME="develop"                    # Git branch to clone/pull
GITHUB_TOKEN=""                          # (Optional) GitHub Personal Access Token for private repos

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

# 1b. Admin Password Security Authentication Gate
HASH_FILE="/etc/vms_admin.hash"
if [ "$ENABLE_ADMIN_PASSWORD_PROTECTION" = true ]; then
    if [ ! -f "$HASH_FILE" ]; then
        log_warn "No Admin Password configured. Initializing Admin Security Password..."
        read -s -p "Set New VMS Admin Deployment Password: " PASS1
        echo ""
        read -s -p "Confirm New VMS Admin Deployment Password: " PASS2
        echo ""

        if [ "$PASS1" != "$PASS2" ] || [ -z "$PASS1" ]; then
            log_error "Passwords do not match or are empty. Aborting deployment."
            exit 1
        fi

        echo -n "$PASS1" | sha256sum | awk '{print $1}' > "$HASH_FILE"
        chmod 600 "$HASH_FILE"
        log_success "Admin Password successfully initialized and stored as SHA-256 in $HASH_FILE."
    fi

    read -s -p "Enter VMS Deployment Admin Password: " ENTERED_PASS
    echo ""

    ENTERED_HASH=$(echo -n "$ENTERED_PASS" | sha256sum | awk '{print $1}')
    STORED_HASH=$(cat "$HASH_FILE" | tr -d ' \n\r')

    if [ "$ENTERED_HASH" != "$STORED_HASH" ]; then
        log_error "Access Denied: Incorrect Admin Password."
        exit 1
    fi

    log_success "Admin Password verified successfully."
fi

CURRENT_DIR="$(pwd)"
log_info "Deployment initiated from: $CURRENT_DIR"

# Auto-detect TURN server URL if not explicitly set
if [ -z "$TURN_SERVER_URL" ]; then
    PRIMARY_IP=$(hostname -I | awk '{print $1}')
    TURN_SERVER_URL="turn:$PRIMARY_IP:3478"
fi

# 2. Generate Complete 15-Section .env File from Script Properties
log_info "Generating 15-section .env configuration from script properties..."
cat <<EOF > "$CURRENT_DIR/.env"
# ==============================================================================
# Camera Video Platform - Active Environment Configurations
# ==============================================================================

# ──────────────────────────────────────────────────────────────────────────────
# 1. CORE SYSTEM PARAMETERS
# ──────────────────────────────────────────────────────────────────────────────
APP_NAME=$APP_NAME
DATABASE_URL=$DATABASE_URL
REDIS_URL=$REDIS_URL

# ──────────────────────────────────────────────────────────────────────────────
# 2. UPSTREAM CAMERA CONFIGURATION REGISTRY
# ──────────────────────────────────────────────────────────────────────────────
UPSTREAM_CAMERA_API_URL=$UPSTREAM_CAMERA_API_URL
UPSTREAM_TIMEOUT_SECONDS=$UPSTREAM_TIMEOUT_SECONDS
UPSTREAM_SYNC_INTERVAL_MINUTES=$UPSTREAM_SYNC_INTERVAL_MINUTES

# ──────────────────────────────────────────────────────────────────────────────
# 3. MEDIAMTX PROXY & SIGNALING ENGINE
# ──────────────────────────────────────────────────────────────────────────────
MEDIAMTX_API_URL=$MEDIAMTX_API_URL
MEDIAMTX_WEBRTC_URL=$MEDIAMTX_WEBRTC_URL
STUN_SERVERS=$STUN_SERVERS
TURN_SERVER_URL=$TURN_SERVER_URL
TURN_SERVER_USERNAME=$TURN_SERVER_USERNAME
TURN_SERVER_CREDENTIAL=$TURN_SERVER_CREDENTIAL
MEDIAMTX_PATCH_ONLY=$MEDIAMTX_PATCH_ONLY
ALLOW_DELETE_ADD_RECONFIGURATION=$ALLOW_DELETE_ADD_RECONFIGURATION

# ──────────────────────────────────────────────────────────────────────────────
# 4. PATHS AND FILE SYSTEM DIRECTORIES
# ──────────────────────────────────────────────────────────────────────────────
FFMPEG_PATH=$FFMPEG_PATH
RECORDING_DIR=$RECORDING_DIR
HLS_DIR=$HLS_DIR
SEGMENT_TIME_SECONDS=$SEGMENT_TIME_SECONDS

# ──────────────────────────────────────────────────────────────────────────────
# 5. LIVE EGRESS SESSION LIMITS
# ──────────────────────────────────────────────────────────────────────────────
MAX_SUBSCRIBERS_PER_STREAM=$MAX_SUBSCRIBERS_PER_STREAM
MAX_WEBRTC_SESSIONS_PER_CAMERA=$MAX_WEBRTC_SESSIONS_PER_CAMERA
ENABLE_WEBRTC=$ENABLE_WEBRTC
ENABLE_HLS_FALLBACK=$ENABLE_HLS_FALLBACK
WEBRTC_CONNECTION_TIMEOUT_SECONDS=$WEBRTC_CONNECTION_TIMEOUT_SECONDS

# ──────────────────────────────────────────────────────────────────────────────
# 6. WATCHDOG AND SCHEDULER INTERVALS
# ──────────────────────────────────────────────────────────────────────────────
UI_POLL_SECONDS=$UI_POLL_SECONDS
SCHEDULER_INTERVAL_SECONDS=$SCHEDULER_INTERVAL_SECONDS
RECOVERY_INTERVAL_SECONDS=$RECOVERY_INTERVAL_SECONDS
CLEANUP_INTERVAL_SECONDS=$CLEANUP_INTERVAL_SECONDS
INDEXER_INTERVAL_SECONDS=$INDEXER_INTERVAL_SECONDS

# ──────────────────────────────────────────────────────────────────────────────
# 7. EDGE PUSH & AUTO-MODE CONFIGURATIONS
# ──────────────────────────────────────────────────────────────────────────────
EDGE_RECEIVER_HOST=$EDGE_RECEIVER_HOST
EDGE_RECEIVER_PORT=$EDGE_RECEIVER_PORT
EDGE_RECEIVER_ENABLED=$EDGE_RECEIVER_ENABLED
ALLOW_UNKNOWN_EDGE_DEVICES=$ALLOW_UNKNOWN_EDGE_DEVICES
STRICT_CAMERA_VALIDATION=$STRICT_CAMERA_VALIDATION
ENABLE_EDGE_PUSH=$ENABLE_EDGE_PUSH
EDGE_PUSH_PRIORITY=$EDGE_PUSH_PRIORITY
EDGE_PUSH_HEARTBEAT_TIMEOUT_SECONDS=$EDGE_PUSH_HEARTBEAT_TIMEOUT_SECONDS
EDGE_PUSH_CHECK_INTERVAL_SECONDS=$EDGE_PUSH_CHECK_INTERVAL_SECONDS

# ──────────────────────────────────────────────────────────────────────────────
# 8. HEALTH AND TELEMETRY WATCHDOGS
# ──────────────────────────────────────────────────────────────────────────────
ENABLE_RTSP_HEALTH_CHECK=$ENABLE_RTSP_HEALTH_CHECK
CAMERA_PING_INTERVAL_SECONDS=$CAMERA_PING_INTERVAL_SECONDS
CAMERA_PING_TIMEOUT_SECONDS=$CAMERA_PING_TIMEOUT_SECONDS
CAMERA_PING_MAX_CONCURRENT=$CAMERA_PING_MAX_CONCURRENT

# ──────────────────────────────────────────────────────────────────────────────
# 9. H.265 ON-DEMAND TRANSCODER (HEVC COMPATIBILITY LAYER)
# ──────────────────────────────────────────────────────────────────────────────
ENABLE_H265_TRANSCODING=$ENABLE_H265_TRANSCODING
MAX_ACTIVE_TRANSCODERS=$MAX_ACTIVE_TRANSCODERS
TRANSCODER_VCODEC=$TRANSCODER_VCODEC
TRANSCODER_PRESET=$TRANSCODER_PRESET
TRANSCODER_TUNE=$TRANSCODER_TUNE
TRANSCODER_GRACE_PERIOD_SECONDS=$TRANSCODER_GRACE_PERIOD_SECONDS

# ──────────────────────────────────────────────────────────────────────────────
# 10. STORAGE AND ARCHIVING POLICY
# ──────────────────────────────────────────────────────────────────────────────
ENABLE_RECORDING=$ENABLE_RECORDING
RECORD_FALLBACK_TO_NORMAL=$RECORD_FALLBACK_TO_NORMAL
RECORD_MOBILE=$RECORD_MOBILE

# ──────────────────────────────────────────────────────────────────────────────
# 11. STREAM SELECTION POLICY
# ──────────────────────────────────────────────────────────────────────────────
PREFERRED_PROFILE=$PREFERRED_PROFILE
LIVE_STREAM_FALLBACK=$LIVE_STREAM_FALLBACK
ENABLE_ADAPTIVE_PROFILE=$ENABLE_ADAPTIVE_PROFILE
FOCUS_VIEW_PROFILE=$FOCUS_VIEW_PROFILE
GRID_VIEW_PROFILE=$GRID_VIEW_PROFILE
MOBILE_VIEW_PROFILE=$MOBILE_VIEW_PROFILE

# ──────────────────────────────────────────────────────────────────────────────
# 12. PLAYBACK & STORAGE RETENTION POLICY
# ──────────────────────────────────────────────────────────────────────────────
PLAYBACK_ALLOW_NORMAL_FALLBACK=$PLAYBACK_ALLOW_NORMAL_FALLBACK
PLAYBACK_ALLOW_MOBILE_FALLBACK=$PLAYBACK_ALLOW_MOBILE_FALLBACK
PLAYBACK_SPEEDS=$PLAYBACK_SPEEDS
ENABLE_RETENTION=$ENABLE_RETENTION
DEFAULT_RETENTION_DAYS=$DEFAULT_RETENTION_DAYS
ENABLE_LOW_DISK_EVICTION=$ENABLE_LOW_DISK_EVICTION
LOW_DISK_SPACE_THRESHOLD_GB=$LOW_DISK_SPACE_THRESHOLD_GB
TARGET_FREE_SPACE_GB=$TARGET_FREE_SPACE_GB

# ──────────────────────────────────────────────────────────────────────────────
# 13. PLAYBACK TIMELINE POLICY
# ──────────────────────────────────────────────────────────────────────────────
TIMELINE_CACHE_SECONDS=$TIMELINE_CACHE_SECONDS
TIMELINE_MERGE_THRESHOLD_SECONDS=$TIMELINE_MERGE_THRESHOLD_SECONDS
TIMELINE_DEFAULT_ZOOM=$TIMELINE_DEFAULT_ZOOM

# ──────────────────────────────────────────────────────────────────────────────
# 14. DEVICE CONFIGURATION & LOCAL TRANSCODE TOGGLES
# ──────────────────────────────────────────────────────────────────────────────
ENABLE_DEVICE_CONFIG=$ENABLE_DEVICE_CONFIG
ENABLE_LOCAL_TRANSCODE=$ENABLE_LOCAL_TRANSCODE

# ──────────────────────────────────────────────────────────────────────────────
# 15. SD CARD ON-DEMAND RETRIEVAL POLICY
# ──────────────────────────────────────────────────────────────────────────────
ENABLE_SD_CARD_ON_DEMAND=$ENABLE_SD_CARD_ON_DEMAND
SD_CARD_ON_DEMAND_RETENTION_SECONDS=$SD_CARD_ON_DEMAND_RETENTION_SECONDS
EOF
log_info "Generated complete 15-section .env configuration file successfully."

# 3. Stop Existing Services (if any)
log_info "Stopping active VMS services..."
systemctl stop video-backend.service || true
systemctl stop mediamtx.service || true
systemctl stop vms-monitor.service || true

# 4. Clone or Pull Latest Project Source
INSTALL_DIR="/opt/video-server"
REPO_URL="https://github.com/Santhosh-Guptha/video-server.git"
if [ -n "$GITHUB_TOKEN" ]; then
    REPO_URL="https://${GITHUB_TOKEN}@github.com/Santhosh-Guptha/video-server.git"
fi

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
