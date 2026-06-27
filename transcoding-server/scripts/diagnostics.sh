#!/usr/bin/env bash
# ── SYSTEM DIAGNOSTICS SCRIPT ───────────────────────────────────────────────
# Scans drivers, checks FFmpeg path, nvidia-smi status, system config, and network ports.

echo "=========================================================="
echo "      VMS TRANSCODING GATEWAY DIAGNOSTIC SYSTEM"
echo "=========================================================="
echo "Timestamp: $(date)"
echo ""

# 1. System Info
echo "1. System Information:"
uname -a
echo "Python: $(python3 --version 2>&1 || echo 'Not Found')"
echo ""

# 2. Check FFmpeg
echo "2. FFmpeg & Codecs:"
FFMPEG_PATH=$(which ffmpeg)
if [ -z "$FFMPEG_PATH" ]; then
    echo "[ERROR] FFmpeg is NOT installed or not in PATH!"
else
    echo "FFmpeg path: $FFMPEG_PATH"
    echo "FFmpeg version: $(ffmpeg -version | head -n 1)"
    echo "NVENC H.264 Encoder Support: $(ffmpeg -encoders | grep nvenc || echo 'No NVENC support found')"
fi
echo ""

# 3. Check NVIDIA Drivers
echo "3. NVIDIA Driver & GPU Status:"
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi
else
    echo "[WARNING] nvidia-smi is not found. GPU transcoding is not available (running in CPU fallback)."
fi
echo ""

# 4. Check Port Sockets
echo "4. Network Socket Connections:"
echo "Checking ports (8500 = API, 8080 = MediaMTX, 8554 = RTSP)..."
netstat -tuln | grep -E '8500|8080|8554' || echo "No active listener sockets on VMS transcoding ports."
echo ""

# 5. Service Status
echo "5. systemd Service Status:"
systemctl status vms-transcoder.service --no-pager || echo "Service not registered as systemd daemon."
echo ""
echo "=========================================================="
echo "Diagnostics complete."
