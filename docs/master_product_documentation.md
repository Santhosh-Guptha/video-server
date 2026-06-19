# Enterprise Video Management System (VMS)
## Master Product Documentation Suite

This document serves as the complete, end-to-end technical, business, functional, and operational manual for the Video Management System (VMS).

---

# Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Business Requirement Document (BRD)](#2-business-requirement-document-brd)
3. [Functional Requirement Specification (FRS)](#3-functional-requirement-specification-frs)
4. [Software Requirement Specification (SRS)](#4-software-requirement-specification-srs)
5. [Solution Architecture Document](#5-solution-architecture-document)
6. [Product Architecture Document](#6-product-architecture-document)
7. [Backend Design Document](#7-backend-design-document)
8. [Frontend Design Document](#8-frontend-design-document)
9. [API Documentation](#9-api-documentation)
10. [Database Design Document](#10-database-design-document)
11. [Streaming Architecture Guide](#11-streaming-architecture-guide)
12. [Recording Architecture Guide](#12-recording-architecture-guide)
13. [Playback Architecture Guide](#13-playback-architecture-guide)
14. [Configuration Guide](#14-configuration-guide)
15. [Environment Variables Reference](#15-environment-variables-reference)
16. [Scenario Documentation](#16-scenario-documentation)
17. [Operational Runbook](#17-operational-runbook)
18. [Troubleshooting Guide](#18-troubleshooting-guide)
19. [Security Documentation](#19-security-documentation)
20. [Performance Tuning Guide](#20-performance-tuning-guide)
21. [DevOps Documentation](#21-devops-documentation)
22. [Test Strategy Document](#22-test-strategy-document)
23. [User Manual](#23-user-manual)
24. [Admin Manual](#24-admin-manual)
25. [Future Roadmap Document](#25-future-roadmap-document)

---

## 1. Executive Summary

### Product Definition
The Enterprise Video Management System (VMS) is a low-latency, high-performance video streaming and recording gateway. It acts as an intelligent middleware between network camera sources (IP cameras, custom edge transceivers) and client interfaces (web browsers, mobile applications).

### Why It Exists (Core Problem)
Traditional VMS products suffer from high latency, proprietary plugin requirements (such as ActiveX), high CPU transcoding costs, and poor support for modern browser standards. This platform solves these problems by utilizing modern streaming protocols (WebRTC WHEP/WHIP, LL-HLS), containerized architectures, and on-demand GPU/CPU transcoding.

### Business Value & Competitive Advantage
- **Ultra-Low Latency**: Real-time camera feeds served with sub-second (<1s) glass-to-glass latency using WebRTC.
- **On-Demand CPU/GPU Transcoding**: HEVC/H.265 video is transcoded only when actively viewed, saving up to 80% CPU overhead.
- **Direct-to-Disk Recording**: Native stream writing without re-encoding preserves 100% video quality and reduces disk write wear.
- **Resilient Edge Sync**: Multi-mode stream connectivity (PULL, PUSH, AUTO) handles remote cell connections over unreliable WAN networks.

---

## 2. Business Requirement Document (BRD)

### Business Goals
- Deliver a unified platform capable of scaling up to 1000+ camera channels per node.
- Lower bandwidth costs for remote monitoring cells by 50% using grid-adaptive downscaling.
- Provide a zero-install browser video wall.

### Stakeholders
- **Operations/Security Teams**: Live wall monitoring and playback exports.
- **Engineering Teams**: API integration for analytics and automation.
- **DevOps/IT Infrastructure**: Service deployment, clustering, and health monitoring.
- **Finance/Management**: Reducing cloud infrastructure and storage hardware costs.

### Scope
- RTSP, WebRTC (WHEP), and LL-HLS video streaming.
- Dynamic camera registry synchronization from Upstream API.
- Fragmented MP4 segment recording, indexing, and Daily Timeline seeking.
- Edge Push TCP Receiver protocol support.

### Out of Scope (Current Phase)
- Native AI Object Analytics (e.g., LPR, face matching) on the central gateway.
- Cloud-hosted archiving (S3 backups).

### Constraints
- Must run on standard Linux VM/Docker environments.
- Browsers require H.264 profiles; on-demand conversion from HEVC/H.265 is required.

---

## 3. Functional Requirement Specification (FRS)

### Camera Management & Sync
- **RTSP Pull**: VMS pulls stream directly from the configured camera RTSP URL.
- **Edge Push**: Camera or gateway pushes raw streams via TCP/RTSP to the VMS.
- **AUTO Detection**: Fallback to RTSP Pull if online; auto-switches to Edge Push upon connection.
- **Strict Validation Mode**: When `STRICT_CAMERA_VALIDATION=true`, only cameras registered on the upstream sync server are allowed to publish.

### Live Streaming & Playback
- **WebRTC WHEP**: Real-time viewer session negotiation via SDP.
- **HLS Fallback**: Fallback to LL-HLS if WebRTC fails or exceeds transcoder capacity.
- **Timeline Seek**: Daily timeline API compiling available dates and gaps (offline periods).
- **Segment Stitching**: Continuous MP4 streaming for multi-file playback requests.

### watchdogs & Recovery
- **Camera Ping Watchdog**: Checks camera network state every 120 seconds.
- **Transcoder Watchdog**: Recovers crashed transcoding processes if viewers are waiting.
- **Safety Net Indexer**: Periodically scans directories to clean database references to deleted files.

---

## 4. Software Requirement Specification (SRS)

### Functional Requirements
- **FR-1**: Backend must sync cameras with Upstream API every N minutes.
- **FR-2**: WebRTC sessions must be authenticated and checked against capacity limits.
- **FR-3**: Storage cleanup must delete video segments older than the retention threshold.

### Non-Functional Requirements
- **Availability**: 99.9% uptime for core media proxying.
- **Latency**: WebRTC live streaming latency must remain under 1.0 second.
- **Performance**: Support up to 10 concurrent H.265 transcoder sessions per node using standard CPU.
- **Scalability**: Support scaling up to 50 concurrent transcoders using GPU acceleration (`h264_nvenc`).

---

## 5. Solution Architecture Document

### High-Level System Flow
```text
  [ Camera Ingress ]               [ Media Server ]             [ Application Layer ]        [ Client Layer ]
    RTSP Camera  ───────(Pull)──────►    MediaMTX    ◄────(REST)───   FastAPI Backend  ◄───────  React UI
    Edge Device  ───────(Push)──────►   (Port 8554)  ◄───(Webhook)─     (Port 8000)             (Nginx)
                                             │                           │   │                     │
                                        (fMP4 Write)                (SQL)│   │(Cache/Locks)        │
                                             ▼                           ▼   ▼                     ▼
                                         [ Storage ]                  [SQLite/DB]  [Redis]   [WHEP Signaling]
```

### Sequence Diagram: Live WebRTC Session Startup
```text
Client Browser            FastAPI Backend            MediaMTX Server           Coturn Server (TURN)
      │                          │                          │                          │
      ├───────1. GET ICE────────►│                          │                          │
      │◄──────2. ICE Server Data─┤                          │                          │
      ├───────3. POST WHEP (Offer)─────────────────────────►│                          │
      │                          ├──────4. Check Codec─────►│                          │
      │                          ├──────5. Resolve Path────►│                          │
      │                          │◄─────6. SDP Answer───────┤                          │
      │◄──────7. 201 Created (Answer)───────────────────────┤                          │
      │                                                     │                          │
      ├───────8. PATCH Trickle ICE Candidate───────────────►│                          │
      │◄─────────────────────9. RTP Video (WHEP)────────────┤                          │
```

---

## 6. Product Architecture Document

- **Frontend (React)**: Modern HTML5 player utilizing WHEP and Hls.js fallback. Manages layout walls and seeks.
- **Backend (FastAPI)**: Controller node hosting REST endpoints, WebSocket status loops, and watchdogs.
- **MediaMTX**: Media server managing RTSP sockets, WebRTC signaling, and HLS muxing.
- **FFmpeg**: Executable spawned on-demand by the backend to transcode HEVC/H.265 source packets to H.264.
- **Redis**: Coordinates distributed session locking, real-time viewer counters, and fast cache state lookups.
- **Database (SQLite/PostgreSQL)**: Persists registry and indexed segments.

---

## 7. Backend Design Document

### Directory Layout
```text
backend/
├── app/
│   ├── config.py           # Unified settings and configuration
│   ├── db.py               # Database connections and session managers
│   ├── indexer.py          # Safety-net directory scanning and file indexing
│   ├── models.py           # SQLAlchemy database tables mapping
│   ├── schemas.py          # Pydantic data schemas
│   ├── upstream.py         # Upstream Camera registry sync client
│   ├── webrtc.py           # WebRTC signaling, ice checks, and resolution
│   ├── transcoder.py       # On-demand FFmpeg transcoders lifecycle
│   ├── stream_manager.py   # AUTO/PULL/PUSH state transitions
│   └── main.py             # FastAPI App, routes, websocket loops
├── alembic/                # DB migrations scripts
├── .env                    # Active production configuration
└── requirements.txt        # Python dependencies
```

- **TranscoderManager**: Monitors active WHEP sessions. If viewer count drops to 0, it initiates a 60-second shutdown grace period.
- **StreamManager**: Manages camera states (ONLINE, OFFLINE, CONNECTING). Implements AUTO detection.

---

## 8. Frontend Design Document

### Directory Layout
```text
frontend/
├── src/
│   ├── components/
│   │   ├── VideoPlayer.tsx     # Unified component supporting WebRTC and HLS fallback
│   │   ├── CameraGrid.tsx      # Video Wall grid layout selector (1x1, 2x2, 3x3)
│   │   └── Timeline.tsx        # SEEK timeline with gaps and date picking
│   ├── hooks/
│   │   └── useWebRTC.ts        # Hook managing PeerConnection and ICE gathering
│   ├── services/
│   │   └── api.ts              # API Client connecting to FastAPI backend
│   └── App.tsx                 # Main layout
├── package.json
└── vite.config.ts
```

- **VideoPlayer**: Attempts WHEP connection with a 10s timer. If timeout expires, it destroys the peer connection and falls back to loading Hls.js.

---

## 9. API Documentation

### Camera Synchronization API
`POST /api/cameras/sync`
- **Purpose**: Force synchronization of cameras from the upstream server.
- **Request**: Empty payload.
- **Response**:
```json
{
  "status": "success",
  "cameras_synced": 45,
  "source": "https://uat1.iviscloud.net/api/cameras/camera-videoserver"
}
```

### WHEP Signaling API
`POST /api/streams/{stream_id}/live/whep?user_id={uuid}`
- **Request Headers**: `Content-Type: application/sdp`
- **Request Body**: Raw SDP Offer.
- **Response Headers**: `Location: /api/streams/{stream_id}/live/whep/{session_id}`
- **Response Body**: Raw SDP Answer (H.264 compatible).

---

## 10. Database Design Document

### ERD Representation
```text
  +------------------+             +----------------------+             +-----------------------+
  |     cameras      |             |    camera_streams    |             |  recording_segments   |
  +------------------+             +----------------------+             +-----------------------+
  | id (PK)          |             | id (PK)              |             | id (PK)               |
  | source_id (UK)   | 1         * | camera_id (FK)       | 1         * | stream_id (FK)        |
  | name             |────────────►| stream_id (UK)       |────────────►| file_path (UK)        |
  | active           |             | stream_url           |             | start_ts              |
  +------------------+             | codec                |             | end_ts                |
                                   +----------------------+             +-----------------------+
```

### Retention Strategy
A cleanup scheduler runs every 10 minutes (`CLEANUP_INTERVAL_SECONDS`), executing:
```sql
DELETE FROM recording_segments WHERE start_ts < (strftime('%s', 'now') - (DEFAULT_RETENTION_DAYS * 86400));
```
It deletes corresponding `.mp4` video files from the storage path.

---

## 11. Streaming Architecture Guide

### Protocol Matrix
- **Ingress**: Camera RTSP Pull (TCP Interleaved to avoid packet loss) or Edge Push (TCP remuxed to RTSP).
- **Processing**: MediaMTX registers path. If H.265 is detected during a WebRTC request, FFmpeg transcoder is spawned.
- **Egress**: Browser WebRTC (WHEP) for real-time play, falling back to Low-Latency HLS (LL-HLS) if network blocks UDP.

---

## 12. Recording Architecture Guide

- MediaMTX writes fMP4 fragments (`60` seconds) directly to `/opt/video-server/backend/data/recordings/{stream_id}/YYYY-MM-DD/`.
- On completion, `segment_hook.sh` POSTs to `/api/recordings/segment-complete`.
- The backend parses timestamps from file name and indexes the segment into the database.
- Gaps are calculated on-the-fly during timeline queries by checking non-contiguous segments.

---

## 13. Playback Architecture Guide

When a client queries playback for a time range (e.g. 10:00 to 10:15):
1. Backend fetches segment rows spanning the timestamps.
2. If multiple files are involved, it creates an FFmpeg concat listing:
   ```text
   file '/opt/video-server/backend/data/recordings/CAM_HD/2026-06-19/file1.mp4'
   file '/opt/video-server/backend/data/recordings/CAM_HD/2026-06-19/file2.mp4'
   ```
3. Backend runs FFmpeg:
   ```bash
   ffmpeg -f concat -safe 0 -i concat_list.txt -c copy -f mp4 -movflags frag_keyframe+empty_moov pipe:1
   ```
4. Piped output is streamed back via HTTP chunked response supporting byte range requests.

---

## 14. Configuration Guide

### MediaMTX Production Config Example (`mediamtx.yml`)
```yaml
webrtc: yes
webrtcAddress: :8889
webrtcEncryption: no
webrtcICEServers2:
  - url: stun:stun.l.google.com:19302
  - url: turn:172.20.100.235:3478?transport=udp
    username: admin
    password: admin123

hls: yes
hlsAddress: :8080
hlsSegmentCount: 8
hlsAllowOrigin: *
```

---

## 15. Environment Variables Reference

| Variable | Purpose | Default | Impact | Recommendations |
| :--- | :--- | :--- | :--- | :--- |
| `DATABASE_URL` | DB Connection String | `sqlite+aiosqlite:///./data/app.db` | Data persistence location | Use Postgres for production scales |
| `STRICT_CAMERA_VALIDATION` | Inbound push validations | `true` | Restricts un-registered edge pushes | Keep true to prevent IP security leaks |
| `ENABLE_H265_TRANSCODING` | HEVC live player support | `true` | Enables CPU/GPU transcoding | Keep true for web viewing support |
| `TRANSCODER_VCODEC` | Transcoding codec engine | `libx264` | Transcoding latency and CPU load | Use `h264_nvenc` if NVIDIA GPU is present |
| `DEFAULT_RETENTION_DAYS` | Storage cleanup limit | `30` | Automatic storage purging | Adjust based on disk size capacity |
| `INDEXER_INTERVAL_SECONDS`| Directory sync scheduler | `600` | Syncs database with deleted files | Set to 600 for quick index pruning |

---

## 16. Scenario Documentation

### Scenario: Camera Pull Success
1. Upstream sync adds camera path `CAM01_HD` to MediaMTX.
2. MediaMTX starts pulling the RTSP feed from the camera.
3. MediaMTX transitions path status to `sourceReady=true`.
4. Backend status loop updates status to `ONLINE`.

### Scenario: Recording Recovery Flow (Safety Net)
1. User deletes 5 files from disk manually.
2. 10 minutes pass; `INDEXER_INTERVAL_SECONDS` triggers the safety watchdog.
3. Watchdog lists directory contents and finds 5 files missing from disk.
4. Watchdog queries DB and deletes corresponding segment rows in bulk.
5. Playback timeline immediately updates, removing the deleted clips and showing them as gaps.

---

## 17. Operational Runbook

### VM Deployment Procedures
1. Clone codebase to `/opt/video-server` and checkout `feature/vms-edge-push`.
2. Configure `.env` settings matching production parameters.
3. Copy `mediamtx_linux.yml` to `/opt/mediamtx/mediamtx.yml` and insert the host candidate IP.
4. Restart services:
   ```bash
   sudo systemctl restart video-backend.service video-frontend.service mediamtx.service
   ```

### Backup & Restore
- **Backup**:
  ```bash
  sqlite3 /opt/video-server/backend/data/app.db ".backup '/opt/backup/app_backup.db'"
  ```
- **Restore**:
  ```bash
  cp /opt/backup/app_backup.db /opt/video-server/backend/data/app.db
  ```

---

## 18. Troubleshooting Guide

### WebRTC Connection Fails (Timeout Fallback Triggered)
- **Symptom**: Player turns black, stays in loading state for 10s, then switches to HLS.
- **Root Cause**: Firewall is blocking UDP ports or TURN credentials are out of sync.
- **Diagnostics**:
  ```bash
  # Check Coturn authentication logs on VM
  sudo journalctl -u coturn -n 100 --no-pager
  ```
- **Resolution**: Ensure TURN credentials in `.env` match Coturn user settings, and verify UDP port `3478` is open.

---

## 19. Security Documentation

- **Authentication**: JWT token authorization on REST API.
- **Secrets Management**: Read credentials from system environment variables; do not hardcode passwords in `config.py`.
- **Network Security**: Keep MediaMTX control API (`9997`) bound to localhost (`127.0.0.1`). Expose only the FastAPI proxy port (`8000`) and the WebRTC port (`8189`) to the public network.

---

## 20. Performance Tuning Guide

- **Low-Latency Streaming**: Enable `zerolatency` tuning on FFmpeg transcoders to eliminate buffer frames.
- **Storage Optimization**: Set `RECORD_HD_ONLY=true` to skip recording sub-streams, reducing disk write IOPS by 50%.
- **Redis timeline Cache**: Keeps timeline queries cached for 60 seconds to prevent heavy database scans.

---

## 21. DevOps Documentation

### systemd Service configuration Example (`video-backend.service`)
```ini
[Unit]
Description=FastAPI Video Management Backend
After=network.target

[Service]
User=root
WorkingDirectory=/opt/video-server/backend
ExecStart=/opt/video-backend-venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 22. Test Strategy Document

- **Unit Testing**: Test `resolve_stream_by_identifier` with mock session datasets.
- **Integration Testing**: Run `test_indexer_pruning.py` to verify directory changes trigger database sync.
- **Stress Testing**: Load test the WHEP signaling endpoint using simulated clients to check concurrent session capacity limits.

---

## 23. User Manual

### How to View Live Wall
1. Open the VMS Web interface (`http://YOUR_SERVER_IP/`).
2. Log in using your credentials.
3. Select Grid layout (e.g. 2x2 grid).
4. Drag cameras from the sidebar into grid cells.
5. The player will automatically negotiate a WebRTC connection.

---

## 24. Admin Manual

### Synchronizing Cameras manually
1. Log in to the Admin Dashboard.
2. Click **Sync Registry** button.
3. Watch the progress indicator; it syncs settings with the Upstream API.
4. Check the system log overlay for any path configuration failures on MediaMTX.

---

## 25. Future Roadmap Document

- **Edge AI Analytics Integration**: Read object metadata frames pushed by edge devices on port `9999` and trigger alerts in the VMS UI.
- **Horizontal Scaling Cluster**: Deploy multiple MediaMTX edge instances synced from a single database master to distribute live streaming egress loads.
