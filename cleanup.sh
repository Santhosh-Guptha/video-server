#!/usr/bin/env bash
# ── VMS SYSTEM CLEANUP AND DATABASE RESET SCRIPT ───────────────────────────
# Stops services, wipes recordings/HLS, resets PostgreSQL & Redis, and rebuilds schema.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Root check
if [ "$EUID" -ne 0 ]; then
  log_error "Please run this script as root (using sudo)."
  exit 1
fi

PROJECT_DIR="/opt/video-server"
BACKEND_DIR="$PROJECT_DIR/backend"
DATA_DIR="$BACKEND_DIR/data"
VENV_PATH="/opt/video-backend-venv"

log_info "Stopping VMS services..."
systemctl stop video-backend.service || true
systemctl stop video-frontend.service || true
systemctl stop mediamtx.service || true

# 1. Wiping physical media and cache
log_info "Wiping recordings and HLS cache..."
if [ -d "$DATA_DIR/recordings" ]; then
    rm -rf "$DATA_DIR/recordings"/*
    log_info "Recordings directory wiped."
fi
if [ -d "$DATA_DIR/hls" ]; then
    rm -rf "$DATA_DIR/hls"/*
    log_info "HLS cache wiped."
fi
rm -f "$DATA_DIR"/record_complete.log || true

# 2. Resetting PostgreSQL Database
log_info "Resetting PostgreSQL database 'vms_db'..."
systemctl start postgresql
# Terminate any active connections to the database to prevent locking
sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'vms_db' AND pid <> pg_backend_pid();" || true
sudo -u postgres psql -c "DROP DATABASE IF EXISTS vms_db;"
sudo -u postgres psql -c "CREATE DATABASE vms_db OWNER vms_admin;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE vms_db TO vms_admin;"
log_success "PostgreSQL database recreated."

# 3. Flashing Redis
log_info "Flushing Redis cache..."
systemctl start redis-server
redis-cli flushall || true
log_success "Redis cache flushed."

# 4. Running Alembic migrations to build fresh schema
log_info "Running Alembic migrations to recreate database schema..."
cd "$BACKEND_DIR"
if [ -f "$VENV_PATH/bin/alembic" ]; then
    "$VENV_PATH/bin/alembic" upgrade head
    log_success "Database schema rebuilt successfully."
else
    log_error "Alembic not found in virtual environment. Cannot rebuild schema."
fi
cd "$PROJECT_DIR"

# 5. Starting VMS Core services
log_info "Restarting VMS Core services..."
systemctl start mediamtx.service || true
systemctl start video-backend.service || true
systemctl start video-frontend.service || true

log_success "VMS Cleanup and Database Reset completed successfully!"
