#!/usr/bin/env bash
# ── PRODUCTION DEPLOYMENT SCRIPT ──────────────────────────────────────────
# Copies files to the target deploy directory and updates service daemon.

set -e

TARGET_DIR=${1:-"/opt/vms-transcoder"}
echo "=== Deploying VMS Transcoding Platform ==="
echo "Target Directory: $TARGET_DIR"

# 1. Create target directories
sudo mkdir -p "$TARGET_DIR"
sudo mkdir -p "$TARGET_DIR/transcoding-server"
sudo mkdir -p "$TARGET_DIR/logs"

# 2. Copy code files
echo "Copying repository files..."
sudo cp -r ../transcoding-server/* "$TARGET_DIR/transcoding-server/"
sudo chmod -R 755 "$TARGET_DIR"

# 3. Trigger restart to load new code
if systemctl list-units --type=service | grep -q "vms-transcoder.service"; then
    echo "Restarting vms-transcoder service..."
    sudo systemctl restart vms-transcoder
fi

echo "=========================================================="
echo "Deployment completed successfully to $TARGET_DIR"
echo "=========================================================="
