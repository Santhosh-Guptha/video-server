#!/usr/bin/env bash
# ── AUTOMATED INSTALLATION SCRIPT ──────────────────────────────────────────
# Sets up virtual environment, installs dependencies, and registers systemd.

set -e

echo "=== Installing VMS Transcoding Platform ==="

# 1. Install system requirements
echo "1. Installing system requirements..."
sudo apt-get update
sudo apt-get install -y ffmpeg python3-pip python3-venv build-essential

# 2. Check GPU driver presence
if command -v nvidia-smi &> /dev/null; then
    echo "NVIDIA Driver detected. GPU acceleration will be available."
else
    echo "[WARNING] No NVIDIA driver detected. The platform will run in CPU fallback mode."
fi

# 3. Virtual Environment Setup
echo "2. Setting up python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install fastapi uvicorn httpx prometheus-client pyyaml pydantic

# 4. Generate systemd Service file
echo "3. Creating systemd service file..."
CUR_DIR=$(pwd)
cat <<EOF | sudo tee /etc/systemd/system/vms-transcoder.service
[Unit]
Description=Hybrid Codec-Aware VMS Transcoding Platform
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$CUR_DIR
ExecStart=$CUR_DIR/venv/bin/uvicorn transcoding-server.api.app:app --host 0.0.0.0 --port 8500 --workers 2
Restart=always
RestartSec=5
Environment=PYTHONPATH=$CUR_DIR
Environment=TENANT_ID=tenant_default
Environment=NODE_ID=node_default

[Install]
WantedBy=multi-user.target
EOF

# 5. Start Service
echo "4. Starting and enabling vms-transcoder service..."
sudo systemctl daemon-reload
sudo systemctl enable vms-transcoder
sudo systemctl start vms-transcoder
sudo systemctl status vms-transcoder --no-pager

echo "=========================================================="
echo "Installation complete! Transcoding Server is active on port 8500."
echo "=========================================================="
