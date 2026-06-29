#!/usr/bin/env bash
# ── VMS RECONFIGURATION & SERVICE RELOAD SCRIPT ──────────────────────────
# Run this script after making configuration changes (.env, cluster_policy.yaml) 
# or pull-updating the repository to reflect updates instantly.

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
FRONTEND_DIR="$PROJECT_DIR/frontend"

log_info "1. Reloading systemd manager configuration..."
systemctl daemon-reload

log_info "2. Rebuilding frontend assets to reflect UI changes..."
if [ -d "$FRONTEND_DIR" ]; then
    cd "$FRONTEND_DIR"
    if [ -d "node_modules" ]; then
        npm run build || log_error "Frontend build failed, proceeding with service restarts..."
    else
        log_info "node_modules not found, running npm install first..."
        npm install --no-audit --no-fund
        npm run build || log_error "Frontend build failed, proceeding with service restarts..."
    fi
    cd "$PROJECT_DIR"
else
    log_warn "Frontend directory not found at $FRONTEND_DIR."
fi

log_info "3. Restarting systemd services..."
systemctl restart mediamtx.service || log_error "Failed to restart MediaMTX."
systemctl restart video-backend.service || log_error "Failed to restart VMS backend."
systemctl restart video-frontend.service || log_error "Failed to restart VMS frontend."

log_info "4. Service Status Verification:"
echo "--------------------------------------------------------"
for service in mediamtx.service video-backend.service video-frontend.service; do
    status=$(systemctl is-active "$service" || true)
    if [ "$status" = "active" ]; then
        echo -e " - ${service}: ${GREEN}ACTIVE (Running)${NC}"
    else
        echo -e " - ${service}: ${RED}INACTIVE (Failed)${NC}"
    fi
done
echo "--------------------------------------------------------"

log_success "All configurations and updates successfully reflected!"
