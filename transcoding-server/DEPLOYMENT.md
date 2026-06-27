# Standalone Transcoder Service Deployment (VM 1)

This document explains how to set up and deploy the high-performance **Hybrid Transcoding Service** on a standalone virtual machine (**VM 1**).

## 1. Prerequisites

Ensure VM 1 has the necessary system libraries and compilers installed:
```bash
sudo apt update
sudo apt install -y ffmpeg python3-venv python3-pip netcat-openbsd
```

### GPU Support (Optional)
If your VM has an NVIDIA GPU and you plan to use hardware-accelerated transcoding (`h264_nvenc`), ensure the CUDA drivers and NVIDIA Container Toolkit are installed:
```bash
# Verify NVIDIA driver is loaded
nvidia-smi
```

---

## 2. Service Installation

1. Copy the `transcoding-server` directory to `/opt/vms-transcoder/transcoding-server` on VM 1:
   ```bash
   sudo mkdir -p /opt/vms-transcoder
   sudo cp -r transcoding-server /opt/vms-transcoder/
   cd /opt/vms-transcoder/transcoding-server
   ```

2. Create a Python virtual environment and install the required dependencies:
   ```bash
   python3 -m venv venv
   ./venv/bin/pip install --upgrade pip
   ./venv/bin/pip install -r requirements.txt
   ```

---

## 3. Systemd Service Setup

To run the transcoder service as a persistent background daemon, create a systemd service file:

1. Create a new service file:
   ```bash
   sudo nano /etc/systemd/system/vms-transcoder.service
   ```

2. Paste the following configuration:
   ```ini
   [Unit]
   Description=Hybrid Codec-Aware VMS Transcoding Platform
   After=network.target

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/opt/vms-transcoder/transcoding-server
   ExecStart=/opt/vms-transcoder/transcoding-server/venv/bin/uvicorn api.app:app --host 0.0.0.0 --port 8500 --workers 2
   Restart=always
   RestartSec=5
   Environment=PYTHONPATH=/opt/vms-transcoder/transcoding-server
   Environment=TENANT_ID=tenant_default
   Environment=NODE_ID=node_default

   [Install]
   WantedBy=multi-user.target
   ```

3. Reload systemd, enable, and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable vms-transcoder.service
   sudo systemctl start vms-transcoder.service
   ```

4. Verify it's active:
   ```bash
   sudo systemctl status vms-transcoder.service
   ```

---

## 4. Port Configuration & Security

The transcoder listens on TCP port `8500`. Ensure that:
- Incoming requests from VM 2 (VMS Core) to Port `8500` are allowed by your firewalls (e.g. UFW or cloud security groups).
- Outgoing RTSP/TCP connections from VM 1 to Port `8554` on VM 2 are allowed so the transcoder can pull H.265 streams and push transcoded H.264 streams back.

---

## 5. Verification

To verify that the service is running and accessible externally:
```bash
curl -i http://localhost:8500/health
```

**Expected Response:**
```json
HTTP/1.1 200 OK
{"status":"healthy","service":"transcoding-server"}
```
