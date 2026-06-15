#!/bin/bash

# Combined Camera Video Platform Setup Script
# Sequentially triggers backend and frontend setup scripts.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color
BLUE='\033[0;34m'

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

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

log_info "Running combined VMS setup from root..."

# Run Backend setup
log_info "--------------------------------------------------"
log_info "Launching Backend Setup..."
log_info "--------------------------------------------------"
chmod +x "$PROJECT_DIR/backend/setup_backend.sh"
"$PROJECT_DIR/backend/setup_backend.sh"

# Run Frontend setup
log_info "--------------------------------------------------"
log_info "Launching Frontend Setup..."
log_info "--------------------------------------------------"
chmod +x "$PROJECT_DIR/frontend/setup_frontend.sh"
"$PROJECT_DIR/frontend/setup_frontend.sh"

log_success "All setups completed successfully!"
