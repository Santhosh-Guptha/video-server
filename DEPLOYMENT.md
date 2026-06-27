# VMS Core & MediaMTX Deployment (VM 2)

This document explains how to configure and deploy the **VMS Core Backend & MediaMTX** on the primary VMS core machine (**VM 2**).

## 1. Prerequisites

Install python, postgresql, redis, and system dependencies:
```bash
sudo apt update
sudo apt install -y python3-venv python3-pip postgresql redis-server
```

---

## 2. MediaMTX Configuration

MediaMTX acts as the main RTSP ingest/egress server.

1. Ensure the MediaMTX configuration file `/opt/mediamtx/mediamtx.yml` allows remote connections:
   ```yaml
   # Enable Control API
   api: yes
   apiAddress: :9997

   # Enable Protocols
   rtsp: yes
   rtspAddress: :8554
   protocols: [udp, tcp]
   ```

2. Restart the MediaMTX service:
   ```bash
   sudo systemctl restart mediamtx
   ```

---

## 3. VMS Core Configuration

1. Update your `.env` configuration file in `/opt/video-server/backend/.env` to configure network-reachable URLs instead of localhost:
   ```bash
   # Database & Redis Configuration
   DATABASE_URL=postgresql+asyncpg://vms_admin:vms_secure_password@localhost:5432/vms_db
   REDIS_URL=redis://localhost:6379/0

   # MediaMTX Configuration
   # Use the VM 2 IP instead of localhost/127.0.0.1
   MEDIAMTX_API_URL=http://<VM2_IP>:9997
   MEDIAMTX_WEBRTC_URL=http://<VM2_IP>:8889

   # External upstream camera API
   UPSTREAM_CAMERA_API_URL=https://iportal-poc.iviscloud.net/api/cameras/camera-videoserver
   ```

2. Update `/opt/video-server/backend/app/configs/cluster_policy.yaml` to point to the standalone transcoder running on VM 1:
   ```yaml
   # Standalone transcoder server running on VM 1
   cloud_gateway_url: http://<VM1_IP>:8500
   cloud_enabled: true
   ```

3. Restart VMS Core Services:
   ```bash
   sudo systemctl restart video-backend.service
   sudo systemctl restart video-frontend.service
   ```

---

## 4. Troubleshooting & Logging

Monitor connection attempts to VM 1 and incoming connections from VM 1:
```bash
# Check if backend successfully contacts VM 1
journalctl -u video-backend.service -f
```
Ensure you do not see the local fallback logs:
`[decision_engine] Cloud transcoder is unhealthy/offline. Selecting local fallback.`
If you do, verify that Port `8500` is open on VM 1 and that VM 2 has network routing to it.
