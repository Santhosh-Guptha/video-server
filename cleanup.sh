#!/usr/bin/env bash
# ==============================================================================
# VMS STACK - COMPLETE UNINSTALL / WIPE CLEANUP SCRIPT
# Design: Stops, disables, and deletes all VMS systemd services, drops PostgreSQL
#         databases/roles, flushes Redis, and completely deletes all installation directories.
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

# Root check
if [[ "$EUID" -ne 0 ]]; then
    log_error "This cleanup script must be executed as root (using sudo)."
    exit 1
fi

echo "=========================================================="
echo "      WARNING: THIS WILL COMPLETELY UNINSTALL VMS"
echo "      AND WIPE ALL SYSTEM DATABASES, LOGS, AND MEDIA!"
echo "=========================================================="
read -p "Are you sure you want to proceed? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Wipe cancelled by user."
    exit 0
fi

# 1. Stop and Disable all VMS systemd services
log_info "1. Stopping and disabling VMS systemd services..."
VMS_SERVICES=("video-backend" "video-frontend" "mediamtx" "vms-transcoder")

for service in "${VMS_SERVICES[@]}"; do
    if systemctl is-active --quiet "${service}.service"; then
        log_info "Stopping active service: ${service}..."
        systemctl stop "${service}.service" || true
    fi
    if systemctl is-enabled --quiet "${service}.service" &>/dev/null; then
        log_info "Disabling service: ${service}..."
        systemctl disable "${service}.service" || true
    fi
    # Remove systemd service files
    if [ -f "/etc/systemd/system/${service}.service" ]; then
        log_info "Removing systemd file: /etc/systemd/system/${service}.service"
        rm -f "/etc/systemd/system/${service}.service"
    fi
done

# Reload systemd configuration to apply changes
log_info "Reloading systemd daemon..."
systemctl daemon-reload
systemctl reset-failed

# 2. Reset/Wipe PostgreSQL Databases and Roles
log_info "2. Resetting PostgreSQL database configurations..."
if systemctl is-active --quiet postgresql; then
    DB_NAME="vms_db"
    DB_USER="vms_admin"
    
    log_info "Terminating active connections and dropping database '$DB_NAME'..."
    sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" || true
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;" || true
    sudo -u postgres psql -c "DROP USER IF EXISTS $DB_USER;" || true
    log_success "PostgreSQL database and role removed."
else
    log_warn "PostgreSQL is not running. Skipping database reset."
fi

# 3. Flush Redis Cache
log_info "3. Flushing Redis cache..."
if systemctl is-active --quiet redis-server; then
    redis-cli flushall || true
    log_success "Redis cache flushed."
else
    log_warn "Redis server is not running. Skipping cache flush."
fi

# 4. Remove all VMS installation directories
log_info "4. Deleting VMS codebases, virtual environments, and media files..."
DIRECTORIES=(
    "/opt/video-server"
    "/opt/vms-transcoder"
    "/opt/mediamtx"
    "/opt/video-backend-venv"
)

for dir in "${DIRECTORIES[@]}"; do
    if [ -d "$dir" ]; then
        log_info "Deleting directory: $dir..."
        rm -rf "$dir"
    fi
done

# 5. Clean up log files
log_info "5. Cleaning up installation log files..."
rm -f /var/log/vms-install.log || true

log_success "=========================================================="
log_success "      VMS WIPE AND UNINSTALL COMPLETED SUCCESSFULLY!"
log_success "=========================================================="
