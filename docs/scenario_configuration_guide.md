# Camera Video Platform - Scenario Configuration Guide

This guide details the VMS runtime policies (Live, Playback, Recording, and Transcoding) and provides copy-paste `.env` templates tailored for various hardware and network deployment scenarios.

---

## 1. Core Policy Dimensions

The VMS operates on four core policy axes:
1. **Live Stream Profile (`LIVE_STREAM_PROFILE`)**: Determines which stream (HD/MAIN vs Normal/SUB vs Mobile) is served for live view.
2. **Adaptive Profile Switcher (`ENABLE_ADAPTIVE_PROFILE`)**: Dynamically downscales resolution in grid views to protect client decoders and save bandwidth.
3. **Playback Profile (`PLAYBACK_PROFILE`)**: Governs the default resolution for recorded playback requests.
4. **Recording Policy (`RECORD_HD_ONLY`)**: Restricts file writes to high-definition streams to preserve storage capacity, or allows recording sub-streams.

---

## 2. Scenario Templates

### Scenario A: High-Fidelity Local LAN Deployment
* **Scenario**: Server and viewing clients are on the same local network (e.g. security office on a gigabit LAN switch). Egress bandwidth is practically unlimited, and maximum video detail is required.
* **Goal**: Always stream and record in HD resolution. Disable all adaptive downscaling.
* **CPU Profile**: Moderate to High (due to HD streams, especially if transcoding HEVC/H.265 on CPU).

#### `.env` Configuration Template:
```env
# ── Core System ──
DATABASE_URL=sqlite+aiosqlite:///./data/app.db
REDIS_URL=redis://127.0.0.1:6379/0

# ── Live Streaming policy (Always Force HD) ──
LIVE_STREAM_PROFILE=HD
ENABLE_ADAPTIVE_PROFILE=false   # Disable grid downscaling
FOCUS_VIEW_PROFILE=HD
GRID_VIEW_PROFILE=HD
MOBILE_VIEW_PROFILE=NORMAL

# ── Playback policy ──
PLAYBACK_PROFILE=HD
PLAYBACK_ALLOW_NORMAL_FALLBACK=true

# ── Recording policy (Record HD and Sub-stream as backup) ──
ENABLE_RECORDING=true
RECORD_HD_ONLY=false
RECORD_NORMAL=true              # Record normal profile too
RECORD_MOBILE=false

# ── Transcoder (CPU) ──
ENABLE_H265_TRANSCODING=true
MAX_ACTIVE_TRANSCODERS=15       # Can run more transcoders on local LAN
TRANSCODER_VCODEC=libx264
TRANSCODER_PRESET=ultrafast
TRANSCODER_TUNE=zerolatency
TRANSCODER_GRACE_PERIOD_SECONDS=60
```

---

### Scenario B: Low-Bandwidth / Remote WAN Cell
* **Scenario**: Server is located at a remote site connected via a cellular gateway (4G/5G) or a low-speed VPN tunnel. Bandwidth charges are high, and connection drops can occur.
* **Goal**: Minimize network egress. Use adaptive streaming aggressively. Enable mobile fallback.
* **CPU Profile**: Low (lower resolution streams require minimal CPU load).

#### `.env` Configuration Template:
```env
# ── Core System ──
DATABASE_URL=sqlite+aiosqlite:///./data/app.db
REDIS_URL=redis://127.0.0.1:6379/0

# ── Live Streaming policy (Strict Bandwidth Protection) ──
LIVE_STREAM_PROFILE=NORMAL      # Default to normal
ENABLE_ADAPTIVE_PROFILE=true     # Enable grid downscaling
FOCUS_VIEW_PROFILE=NORMAL       # Cap single-camera view at NORMAL
GRID_VIEW_PROFILE=MOBILE        # Drop grid cams to MOBILE resolution
MOBILE_VIEW_PROFILE=MOBILE

# ── Playback policy (Allow low-res fallback) ──
PLAYBACK_PROFILE=NORMAL
PLAYBACK_ALLOW_NORMAL_FALLBACK=true
PLAYBACK_ALLOW_MOBILE_FALLBACK=true

# ── Recording policy (Only save HD locally to conserve disk writes) ──
ENABLE_RECORDING=true
RECORD_HD_ONLY=true
RECORD_NORMAL=false
RECORD_MOBILE=false

# ── Upstream Sync (Slower sync interval to save traffic) ──
UPSTREAM_SYNC_INTERVAL_MINUTES=10
UPSTREAM_TIMEOUT_SECONDS=20.0

# ── Transcoder Cooldown ──
TRANSCODER_GRACE_PERIOD_SECONDS=15 # Kill idle transcoders faster to save resources
```

---

### Scenario C: Maximum Storage & Archive Retention
* **Scenario**: Server has limited storage capacity (e.g. 500GB SSD), but company policy mandates **90 days** of retention.
* **Goal**: Optimize storage writes. Record only HD streams. Keep segment durations tight.
* **CPU Profile**: Low.

#### `.env` Configuration Template:
```env
# ── Core System ──
DATABASE_URL=sqlite+aiosqlite:///./data/app.db
REDIS_URL=redis://127.0.0.1:6379/0

# ── Storage & Archiving Policy ──
ENABLE_RECORDING=true
RECORD_HD_ONLY=true             # Do NOT write normal or mobile streams (saves ~50%)
RECORD_NORMAL=false
RECORD_MOBILE=false
SEGMENT_TIME_SECONDS=60          # 60s is optimal for storage alignment

# ── Retention Engine (Daily Cleanup) ──
ENABLE_RETENTION=true
DEFAULT_RETENTION_DAYS=90       # Enforce 90-day delete loop
CLEANUP_INTERVAL_SECONDS=600    # Run cleanup loop every 10 minutes

# ── Fast Filesystem Indexing ──
INDEXER_INTERVAL_SECONDS=300    # Quick safety-net index reconciliation
```

---

### Scenario D: High-Density GPU-Accelerated Node (NVIDIA)
* **Scenario**: Deploying on a server equipped with an NVIDIA GPU (e.g., Tesla T4, RTX 4090). Managing 100+ cameras with a high proportion of H.265 feeds.
* **Goal**: Offload HEVC/H.265 decoding/encoding to NVIDIA hardware (NVENC) to scale concurrent transcoders without burning CPU cores.
* **CPU Profile**: Very Low (GPU handles the encoding workload).

#### `.env` Configuration Template:
```env
# ── Core System ──
DATABASE_URL=postgresql+asyncpg://vms_admin:vms_secure_password@localhost:5432/vms_db
REDIS_URL=redis://127.0.0.1:6379/0

# ── GPU Transcoder Settings ──
ENABLE_H265_TRANSCODING=true
MAX_ACTIVE_TRANSCODERS=50       # NVIDIA NVENC supports high concurrent sessions
TRANSCODER_VCODEC=h264_nvenc    # Offloads encoding to GPU
TRANSCODER_PRESET=p1            # NVIDIA preset p1 (lowest latency/fastest)
TRANSCODER_TUNE=ull             # Ultra Low Latency tuning
TRANSCODER_GRACE_PERIOD_SECONDS=60

# ── Egress limits ──
MAX_SUBSCRIBERS_PER_STREAM=500
MAX_WEBRTC_SESSIONS_PER_CAMERA=200
```

---

### Scenario E: Mobile Edge-Push & Hybrid Deployment
* **Scenario**: Deployment with a mix of stationary IP cameras (where the VMS pulls feeds) and mobile edge devices (which push streams dynamically over 4G/5G when active).
* **Goal**: Enable edge push receiver, prioritize incoming pushes, and manage connection dropouts seamlessly.
* **CPU Profile**: Moderate.

#### `.env` Configuration Template:
```env
# ── Core System ──
DATABASE_URL=sqlite+aiosqlite:///./data/app.db
REDIS_URL=redis://127.0.0.1:6379/0

# ── Edge Receiver ──
EDGE_RECEIVER_ENABLED=true
EDGE_RECEIVER_HOST=0.0.0.0
EDGE_RECEIVER_PORT=9999
ALLOW_UNKNOWN_EDGE_DEVICES=false # Match DB registry for security
STRICT_CAMERA_VALIDATION=true

# ── Auto-Mode & Watchdogs ──
ENABLE_EDGE_PUSH=true
EDGE_PUSH_PRIORITY=true         # Switch to PUSH automatically when device connects
EDGE_PUSH_HEARTBEAT_TIMEOUT_SECONDS=60 # Detect disconnect in 60s and fallback to PULL
EDGE_PUSH_CHECK_INTERVAL_SECONDS=15    # Frequent watchdog sweeps
```
