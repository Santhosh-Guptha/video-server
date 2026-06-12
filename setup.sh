#!/bin/bash

# ==============================================================================
# Automated Setup Script for Camera Video Platform
# Supported OS: Debian/Ubuntu Linux (tested on root@explore)
# ==============================================================================

# Exit immediately if a command exits with a non-zero status
set -e

# Get the directory where the script is located
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

echo "======================================================================"
echo "Starting Automated Setup for Camera Video Platform..."
echo "Install Directory: $SCRIPT_DIR"
echo "======================================================================"

# 1. Install System Dependencies (Apt-get auto-install if root/sudo on Debian/Ubuntu)
if [ -f /etc/debian_version ]; then
    echo "[1/4] Installing system dependencies via apt-get..."
    if [ "$EUID" -ne 0 ]; then
        echo "Please run as root or using sudo to automatically install system dependencies."
        exit 1
    fi
    apt-get update -y
    apt-get install -y python3 python3-pip python3-venv ffmpeg curl

    # Install nodejs if not already present; NodeSource nodejs automatically includes npm
    if ! command -v node &> /dev/null; then
        echo "Node.js not found, installing nodejs..."
        apt-get install -y nodejs
    fi

    # Check if npm is available; only attempt standalone npm install if not present
    if ! command -v npm &> /dev/null; then
        echo "npm not found, attempting to install standalone npm..."
        apt-get install -y npm || echo "Warning: npm package installation failed, but proceeding anyway."
    fi
else
    echo "Warning: Non-Debian based Linux detected. Please ensure python3, pip, venv, nodejs, npm, and ffmpeg are installed."
fi

# 2. Setup Backend Environment
echo "[2/4] Setting up Backend environment..."
cd "$SCRIPT_DIR/backend"

# Avoid recreating venv if it already exists
if [ ! -d "venv" ]; then
    echo "Creating backend virtual environment..."
    python3 -m venv venv
else
    echo "Existing backend venv found. Reusing virtual environment..."
fi

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# 3. Setup Frontend Environment
echo "[3/4] Setting up Frontend environment..."
cd "$SCRIPT_DIR/frontend"

# Clean install node_modules only if not present, otherwise incremental npm install
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
else
    echo "Existing node_modules found. Updating dependencies incrementally..."
fi
npm install
npm run build

# 4. Generate Systemd Service Files
echo "[4/4] Generating Systemd Service Files..."

NPM_PATH=$(which npm || echo "/usr/bin/npm")
PYTHON_PATH="$SCRIPT_DIR/backend/venv/bin/python"
UVICORN_PATH="$SCRIPT_DIR/backend/venv/bin/uvicorn"

# Define backend service
cat <<EOF > /etc/systemd/system/video-backend.service
[Unit]
Description=Camera Video Platform Backend FastAPI
After=network.target

[Service]
User=root
WorkingDirectory=$SCRIPT_DIR/backend
ExecStart=$UVICORN_PATH app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
Environment=PATH=$SCRIPT_DIR/backend/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

# Define frontend service (Runs Vite dev server serving build/proxy mapping)
cat <<EOF > /etc/systemd/system/video-frontend.service
[Unit]
Description=Camera Video Platform Frontend Vite Server
After=network.target video-backend.service

[Service]
User=root
WorkingDirectory=$SCRIPT_DIR/frontend
ExecStart=$NPM_PATH run dev -- --host 0.0.0.0
Restart=always
RestartSec=5
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

# Reload and enable services
echo "Registering and starting systemd services..."
systemctl daemon-reload

systemctl enable video-backend.service
systemctl enable video-frontend.service

systemctl restart video-backend.service
systemctl restart video-frontend.service

echo "======================================================================"
echo "Setup Complete! Both services have been registered and started."
echo "======================================================================"
echo "Verify backend service status:"
echo "  systemctl status video-backend.service"
echo ""
echo "Verify frontend service status:"
echo "  systemctl status video-frontend.service"
echo ""
echo "Access Platform:"
echo "  Frontend Web UI: http://localhost:5173"
echo "  Backend API:     http://localhost:8000"
echo "======================================================================"
