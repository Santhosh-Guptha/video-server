#!/bin/bash

# VMS Video Server Cleanup & Reset Script
# Deletes SQLite DB, logs, HLS, and recordings, then restarts services.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Root check
if [ "$EUID" -ne 0 ]; then
  log_error "Please run this script as root (using sudo)."
  exit 1
fi

log_info "Stopping video services..."
systemctl stop video-backend || true
systemctl stop video-frontend || true
systemctl stop mediamtx || true

# Target backend directory
BACKEND_DIR="/opt/video-server/backend"
DATA_DIR="$BACKEND_DIR/data"

if [ -d "$DATA_DIR" ]; then
    log_info "Cleaning up SQLite Database..."
    rm -f "$DATA_DIR/app.db"
    
    log_info "Cleaning up logs..."
    rm -f "$DATA_DIR/record_complete.log"
    
    log_info "Cleaning up recordings..."
    if [ -d "$DATA_DIR/recordings" ]; then
        rm -rf "$DATA_DIR/recordings"/*
    fi
    
    log_info "Cleaning up HLS fragments..."
    if [ -d "$DATA_DIR/hls" ]; then
        rm -rf "$DATA_DIR/hls"/*
    fi
    
    log_success "Cleaned up database, logs, and video files successfully."
else
    log_error "Data directory not found at $DATA_DIR"
fi

log_info "Starting video services again..."
systemctl start mediamtx || true
systemctl start video-backend || true
systemctl start video-frontend || true

log_success "Reset and system reboot completed successfully!"
