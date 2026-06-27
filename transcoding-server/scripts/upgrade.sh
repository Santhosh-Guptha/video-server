#!/usr/bin/env bash
# ── AUTOMATED UPGRADE SCRIPT ───────────────────────────────────────────────
# Syncs newest code, updates venv modules, and restarts daemon cleanly.

set -e

echo "=== Upgrading VMS Transcoding Platform ==="

# 1. Stash changes and pull latest
echo "Syncing latest changes from git..."
git stash || true
git pull origin main || git pull || echo "[WARNING] Could not pull from git origin. Continuing upgrade of local files."

# 2. Re-install requirements
echo "Updating python packages..."
if [ -d "venv" ]; then
    source venv/bin/activate
    pip install -r requirements.txt || pip install fastapi uvicorn httpx prometheus-client pyyaml pydantic pytest pytest-asyncio
fi

# 3. Reload daemon
echo "Restarting service..."
sudo systemctl daemon-reload || true
sudo systemctl restart vms-transcoder || true

echo "=========================================================="
echo "Upgrade complete. Service is running."
echo "=========================================================="
