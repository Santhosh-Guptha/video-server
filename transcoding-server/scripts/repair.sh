#!/usr/bin/env bash
# ── AUTOMATED REPAIR SCRIPT ───────────────────────────────────────────────
# Fixes python environments, executable permissions, and systemd service failures.

set -e

echo "=== Commencing Auto-Repair of VMS Transcoding Platform ==="

# 1. Check permissions
echo "1. Checking script permissions..."
chmod +x install.sh diagnostics.sh benchmark.sh deploy.sh rollback.sh upgrade.sh backup.sh repair.sh || true

# 2. Repair Python Venv
echo "2. Validating virtual environment..."
if [ ! -d "venv" ]; then
    echo "[REPAIR] Virtual environment 'venv' not found. Creating a fresh one..."
    python3 -m venv venv
fi

source venv/bin/activate
echo "Reinstalling/repairing python dependencies..."
pip install --upgrade pip
pip install fastapi uvicorn httpx prometheus-client pyyaml pydantic pytest pytest-asyncio

# 3. Check FFmpeg link
echo "3. Verifying FFmpeg links..."
if ! command -v ffmpeg &> /dev/null; then
    echo "[REPAIR] ffmpeg is missing from PATH. Attempting to repair via apt..."
    sudo apt-get update && sudo apt-get install -y ffmpeg
fi

# 4. Restart Daemon
echo "4. Reloading and restarting vms-transcoder service..."
sudo systemctl daemon-reload || true
sudo systemctl restart vms-transcoder || true
sudo systemctl status vms-transcoder --no-pager || true

echo "=========================================================="
echo "Auto-repair complete! Check diagnostics.sh for confirmation."
echo "=========================================================="
