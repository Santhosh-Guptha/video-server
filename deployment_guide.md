# Camera Video Platform - Server Setup & Deployment Guide

This guide details how to deploy and configure the fullstack video platform (React frontend, FastAPI backend, MediaMTX, Redis, SQLite/PostgreSQL) on a target Linux server (Ubuntu 20.04 / 22.04 LTS recommended).

---

## 1. System Ports & Firewall Configuration

Before starting, ensure the following ports are allowed on your server's firewall (e.g. `ufw`):

| Port | Protocol | Service / Component | Description |
|---|---|---|---|
| **5173** | TCP | Vite UI (Dev Server) | Web Interface (if running in dev mode) |
| **80** / **443** | TCP | Nginx Web Server | Web Interface (production reverse proxy - *Recommended*) |
| **8000** | TCP | FastAPI Backend | REST API and Websockets endpoint |
| **9999** | TCP | Custom TCP Edge Receiver | Receives incoming video streams from edge devices |
| **8554** | TCP/UDP | MediaMTX RTSP | RTSP ingress/egress stream connections |
| **8889** | TCP | MediaMTX HTTP WebRTC | Signaling and WHEP/WHIP browser streaming |
| **8189** | TCP | MediaMTX WebRTC Data | WebRTC TCP multiplexer port |

To open these ports on Ubuntu using UFW:
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8000/tcp
sudo ufw allow 9999/tcp
sudo ufw allow 8554/tcp
sudo ufw allow 8554/udp
sudo ufw allow 8889/tcp
sudo ufw allow 8189/tcp
sudo ufw allow 5173/tcp
sudo ufw enable
```

---

## 2. Step-by-Step Installation

### Step 2.1: Install System Dependencies
Install git, python, nodejs, redis-server, ffmpeg, and sqlite3:
```bash
sudo apt update
# NOTE: If using NodeSource for Node.js (recommended), npm is already bundled.
# Do not specify npm in the apt command as it causes dependency conflicts.
sudo apt install -y git python3-pip python3-venv nodejs redis-server ffmpeg sqlite3

# If Node.js was installed from default Ubuntu repositories (not NodeSource), you may need npm:
# sudo apt install -y npm
```
Ensure Redis is running:
```bash
sudo systemctl enable redis-server
sudo systemctl restart redis-server
```

### Step 2.2: Clone the Codebase
Clone the repository to a standard directory (e.g. `/opt/video-server`) and check out the correct branch:
```bash
sudo git clone https://github.com/Santhosh-Guptha/video-server.git /opt/video-server
cd /opt/video-server
sudo git checkout feature/vms-edge-push
```

### Step 2.3: Install & Configure MediaMTX
1. Create directory and download the MediaMTX binary:
   ```bash
   sudo mkdir -p /opt/mediamtx
   cd /opt/mediamtx
   # Download MediaMTX v1.9.0 (or adjust to your preferred version)
   sudo wget https://github.com/bluenviron/mediamtx/releases/download/v1.9.0/mediamtx_v1.9.0_linux_amd64.tar.gz
   sudo tar -xvzf mediamtx_v1.9.0_linux_amd64.tar.gz
   ```

2. Copy the platform's customized configuration to `/opt/mediamtx/mediamtx.yml`:
   ```bash
   sudo cp /opt/video-server/mediamtx_linux.yml /opt/mediamtx/mediamtx.yml
   ```

3. Configure server IP for WebRTC & HLS fallback (CRITICAL):
   Open `/opt/mediamtx/mediamtx.yml` and configure the following parameters:
   - **`webrtcAdditionalHosts`**: Add the server's external IP (e.g. `[172.20.100.235]`) under the `webrtc:` block. This advertises the correct host candidate to WebRTC clients.
   - **`hlsSegmentCount`**: Ensure it is set to `8` or higher. Low-Latency HLS requires at least 7 segments; setting it lower (e.g., the default of 3) causes the HLS muxer to fail and break streaming fallback for H265 cameras.
   
   To apply these automatically via sed:
   ```bash
   # Set HLS segment count to 8
   sudo sed -i 's/hlsSegmentCount: 3/hlsSegmentCount: 8/g' /opt/mediamtx/mediamtx.yml
   
   # Add your server IP to the WebRTC host candidates list (replace 172.20.100.235 with your VM IP)
   sudo sed -i '/webrtcAddress: :8889/a webrtcAdditionalHosts: [172.20.100.235]' /opt/mediamtx/mediamtx.yml
   ```

4. Setup MediaMTX as a systemd service:
   ```bash
   sudo cp /opt/video-server/mediamtx.service /etc/systemd/system/mediamtx.service
   sudo systemctl daemon-reload
   sudo systemctl enable mediamtx.service
   sudo systemctl start mediamtx.service
   ```

### Step 2.4: Run Automated Setup Script
Run the project's automated setup script as root. This script installs NPM packages, creates the Python virtual environment, registers systemd services, and starts them:
```bash
cd /opt/video-server
sudo chmod +x setup.sh backend/setup_backend.sh frontend/setup_frontend.sh
sudo ./setup.sh
```

---

## 3. Verify Deployment

Check that all three services are running properly:

```bash
# Check MediaMTX
sudo systemctl status mediamtx

# Check Backend FastAPI
sudo systemctl status video-backend

# Check Frontend Vite UI
sudo systemctl status video-frontend
```

---

## 4. Production Option: Serving Frontend via Nginx (Recommended)

Running Vite in development mode (`npm run dev`) on a production server is not recommended. For a faster, stable deployment, serve the frontend statically using Nginx.

### Step 4.1: Build the Frontend
Compile and bundle the production assets:
```bash
cd /opt/video-server/frontend
npm run build
```
This outputs production files to `/opt/video-server/frontend/dist`.

### Step 4.2: Install and Configure Nginx
1. Install Nginx:
   ```bash
   sudo apt install -y nginx
   ```

2. Disable the default site and create a configuration for our platform:
   ```bash
   sudo rm /etc/nginx/sites-enabled/default
   sudo nano /etc/nginx/sites-available/video-server
   ```

3. Paste the following configuration:
   ```nginx
   server {
       listen 80;
       server_name _; # Or your domain/IP address

       # Root directory containing the built Vite UI
       root /opt/video-server/frontend/dist;
       index index.html;

       location / {
           try_files $uri $uri/ /index.html;
       }

       # Proxy API requests to FastAPI
       location /api {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }

       # Proxy WebSockets requests to FastAPI
       location /ws {
           proxy_pass http://127.0.0.1:8000;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_set_header Host $host;
       }
   }
   ```

4. Enable the site and restart Nginx:
   ```bash
   sudo ln -s /etc/nginx/sites-available/video-server /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl restart nginx
   ```

5. Stop the Vite development systemd service (since Nginx now serves the UI):
   ```bash
   sudo systemctl stop video-frontend.service
   sudo systemctl disable video-frontend.service
   ```

Colleagues and edge devices can now access the platform directly on standard HTTP port **80** (e.g. `http://YOUR_SERVER_IP/`).

---

## 5. Monitoring & Troubleshooting

To monitor real-time logs for backend or streaming operations:

```bash
# View live backend logs
sudo journalctl -u video-backend -f

# View live MediaMTX logs
sudo journalctl -u mediamtx -f

# View live frontend console logs (if running dev server)
sudo journalctl -u video-frontend -f
```

---

## 6. How Live Streaming Works & H.265 Transcoding

The platform supports ultra-low latency **WebRTC (WHEP)** playback for both H.264 and H.265 camera streams, with an automated fallback to **Low-Latency HLS (LL-HLS)**:

### Step 6.1: WebRTC (H264/H265 Cameras)
- **H.264 Streams**: Played directly via WebRTC using MediaMTX.
- **H.265 Streams**: Since web browsers do not natively support H.265 playback over WebRTC, the platform implements an **On-Demand Transcoding Engine**.
  - When a viewer requests playback of an H.265 camera stream, the backend intercepts the WebRTC WHEP signaling.
  - It automatically spawns a shared, on-demand FFmpeg process to transcode the stream from H.265 to H.264.
  - The transcoded stream is published to a temporary path in MediaMTX (`{stream_id}_h264`), and the client is transparently routed to this path.
  - **Viewer-Based Lifecycle**: If additional viewers watch the same stream, they share the single running FFmpeg transcoder. When the last viewer disconnects, a 60-second grace period is triggered. If no new viewers connect, the transcoder process is terminated to save CPU resources.
  - **Failover & Watchdog**: A background scheduler watchdog monitors the transcoders and automatically restarts any crashed processes if active viewers are still waiting.
  - **Capacity Protection**: To protect the server CPU, the backend limits the maximum number of concurrent transcoders (default: 10).
  - **Untouched Recordings**: Raw H.265 video is recorded directly from the camera stream to save storage and disk write IO; only live view utilizes the transcoder.
- The backend API (`/api/webrtc/ice-servers`) dynamically resolves the correct TURN candidate IP for the client browser. It inspects browser headers (`Referer`, `Origin`, and `X-Forwarded-Host`) to automatically retrieve the server's public IP address, bypassing any localhost/loopback proxy issues.
- MediaMTX serves WebRTC traffic on UDP port `8189`.

### Step 6.2: H.265 Transcoding Configuration
You can configure the H.265 transcoding settings in the `.env` file or environment variables:
- `MAX_ACTIVE_TRANSCODERS`: Maximum number of concurrent transcoder processes (default: `10`).
- `TRANSCODER_VCODEC`: Video codec to use for transcoding. Set to `libx264` (default, CPU-based) or a hardware-accelerated encoder such as `h264_nvenc` (NVIDIA GPUs) or `h264_qsv` (Intel QuickSync).
- `TRANSCODER_PRESET`: Preset for encoding speed/compression (default: `ultrafast`).
- `TRANSCODER_GRACE_PERIOD_SECONDS`: Time in seconds to wait before stopping a transcoder after the last viewer disconnects (default: `60`).

### Step 6.3: LL-HLS Fallback
- If WebRTC signaling fails or the transcoding capacity limit is hit, the player automatically falls back to **LL-HLS**.
- The HLS playlist (`index.m3u8`) is served by the MediaMTX HLS muxer on port `8080` and proxied through the FastAPI backend.
- **Troubleshooting Muxer Destruction**: If HLS playback returns a `404 Not Found` in your logs, ensure that `hlsSegmentCount` is set to `8` or higher in `/opt/mediamtx/mediamtx.yml`.

