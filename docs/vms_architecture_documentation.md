# Enterprise Video Management System (VMS)
## Complete Architecture & Data Flow Documentation

This document serves as the comprehensive, end-to-end technical architecture and data flow specification for the Video Management System (VMS). It details the system's design, request flows, media routing, background operations, database schema, and failover behaviors.

---

## 1. Executive Summary
The VMS is an enterprise-grade, high-performance, and low-latency video streaming and recording platform. It is designed to interface with traditional IP cameras (via RTSP) and custom edge devices (via a custom TCP receiver). The system implements hybrid media management:
- **Low-Latency Live View**: Served via WebRTC (WHEP) for real-time monitoring (<1 second latency).
- **Native Recordings**: Saved as high-fidelity MP4 segments directly from RTSP sources to optimize storage and maintain quality.
- **On-Demand Transcoding**: Translates HEVC/H.265 feeds to H.264 on-demand for browser playback compatibility, dynamically spawning and terminating transcoders to optimize CPU utilization.

---

## 2. System Architecture Overview

The system architecture divides responsibilities across the frontend (React), FastAPI backend, MediaMTX media server, Redis caching/coordination layer, and a PostgreSQL/SQLite persistent database.

```mermaid
graph TD
    subgraph Client Layer
        React[React Frontend]
        WebRTC[WebRTC Player]
    end

    subgraph Application & Control Layer
        FastAPI[FastAPI Backend]
        Edge[TCP Edge Receiver :9999]
        Sched[Background Schedulers]
    end

    subgraph Media Infrastructure
        MTX[MediaMTX Media Server]
        FFmpeg[FFmpeg Transcoders]
    end

    subgraph Data & Caching Layer
        DB[(PostgreSQL / SQLite)]
        Redis[(Redis Cache & Pub/Sub)]
    end

    subgraph Ingress Sources
        Cam264[H.264 RTSP Camera]
        Cam265[H.265 RTSP Camera]
        EdgeDev[Edge Device Push]
    end

    %% Ingress Flows
    Cam264 -->|RTSP Pull| MTX
    Cam265 -->|RTSP Pull| MTX
    EdgeDev -->|Proprietary TCP| Edge
    Edge -->|Transcoded RTSP Push| MTX

    %% Control & API Flows
    React -->|HTTP/WS| FastAPI
    FastAPI -->|REST API| MTX
    FastAPI -->|Query/Update| DB
    FastAPI -->|Cache/Locks| Redis
    Sched -->|Cron Jobs| FastAPI

    %% Live Streaming Flows
    WebRTC -->|WHEP Signaling| FastAPI
    FastAPI -->|Signaling Proxy| MTX
    MTX -->|WebRTC Media| WebRTC
    
    %% Transcoding Flows
    MTX -->|Raw H.265 RTSP| FFmpeg
    FFmpeg -->|Transcoded H.264 RTSP| MTX
```

---

## 3. Component Responsibilities

### 3.1 Backend (FastAPI)
- **REST APIs**: Manages camera registration, playback schedules, live stream tokens, and system settings.
- **WebRTC Signaling Proxy**: Handles WHEP/WHIP SDP negotiation and proxies requests between clients and MediaMTX.
- **Transcoder Manager**: Dynamically manages FFmpeg transcoding processes for H.265 streams based on active client sessions.
- **Background Schedulers**: Performs periodic camera status updates, recording gap recovery, archive retention cleanup, and session audits.

### 3.2 Media Server (MediaMTX)
- Acts as the primary RTSP ingress gateway and WebRTC publisher.
- Segment-records streams natively to local storage as MP4 files.
- Generates Low-Latency HLS (LL-HLS) manifests as a secondary fallback.
- Triggers webhooks to the backend when a recording segment is finalized.

### 3.3 TCP Edge Receiver
- Listens on port `9999` for inbound proprietary TCP streams.
- Parses headers containing camera credentials and frame boundaries.
- Remuxes incoming raw payloads via FFmpeg and pushes them to MediaMTX using RTSP.

### 3.4 Redis & Database Layer
- **Redis**: Maintains live session states, active viewer counts, rate-limiting locks, and timeline lookup caches.
- **Relational DB**: Houses schema definitions for Cameras, Streams, Recording Segments, active WebRTC Sessions, and Transcoder instances.

---

## 4. Camera Synchronization & Validation

### 4.1 Sync Flow
The system synchronizes cameras from the upstream **Video Server API** periodically.

```mermaid
sequenceDiagram
    participant Upstream as Video Server API
    participant Sched as Sync Scheduler
    participant DB as Relational Database
    participant Manager as Stream Manager
    participant MTX as MediaMTX

    Sched->>Upstream: GET /api/cameras/camera-videoserver
    Upstream-->>Sched: JSON Camera Configurations
    loop Each Camera
        Sched->>DB: Upsert Camera & CameraStream
        Note over Sched,DB: Sync parameters: name, stream_url, active, make
        alt Camera is active
            Sched->>Manager: add_stream(stream_id)
            Manager->>MTX: POST /v3/config/paths/add/{stream_id}
            MTX-->>Manager: 200 OK / 201 Created
        else Camera is inactive
            Sched->>Manager: remove_stream(stream_id)
            Manager->>MTX: DELETE /v3/config/paths/delete/{stream_id}
        end
    end
```

### 4.2 Validation Rule Matrix
The system enforces validation rules governed by the environment variable `STRICT_CAMERA_VALIDATION`.

| STRICT_CAMERA_VALIDATION | Inbound Camera Source | Validation Criteria | Action |
| :--- | :--- | :--- | :--- |
| **`true`** | Upstream API Camera | `active == true` and `synced_from_api == true` | **ALLOW** (Registered and active) |
| **`true`** | Upstream API Camera | `active == false` or `synced_from_api == false` | **REJECT** (Deactivated/Unsynced) |
| **`true`** | Unknown Edge Push | Credentials / Stream ID absent in DB | **REJECT** (Strict security match) |
| **`false`** | Any Camera Stream | Basic structure match | **ALLOW** (Auto-creates missing rows) |

---

## 5. Stream Source Management & AUTO Mode

Streams can operate in **PULL**, **PUSH**, or **AUTO** modes:
- **PULL**: Backend pulls media from the camera's RTSP URL. Edge pushes are rejected.
- **PUSH**: The stream expects an edge push. RTSP pulls are never initiated.
- **AUTO**: Hybrid fallback. Defaults to RTSP pull if URL is configured; automatically transitions to Edge Push if a stream connects, using watchdogs to manage states.

### 5.1 Mode Transition State Machine
```mermaid
stateDiagram-v2
    [*] --> REGISTERED
    
    state AUTO_MODE {
        REGISTERED --> CONNECTING: Add Path (RTSP Pull)
        CONNECTING --> ONLINE_PULL: RTSP Stream Active
        CONNECTING --> OFFLINE: RTSP Fails / Timeout
        OFFLINE --> CONNECTING: Retry Pull
        
        ONLINE_PULL --> ONLINE_PUSH: Edge Device Connects
        OFFLINE --> ONLINE_PUSH: Edge Device Connects
        
        ONLINE_PUSH --> CONNECTING: Edge Disconnects (Watchdog Timeout)
    }
    
    state PULL_MODE {
        REGISTERED --> PULL_ACTIVE: Pull Configured
        PULL_ACTIVE --> PULL_FAILED: RTSP Timeout
        PULL_FAILED --> PULL_ACTIVE: Watchdog Retry
    }
    
    state PUSH_MODE {
        REGISTERED --> PUSH_WAITING: Wait for Publisher
        PUSH_WAITING --> PUSH_ACTIVE: Edge Push Starts
        PUSH_ACTIVE --> PUSH_WAITING: Edge Push Disconnects
    }
```

---

## 6. Live Viewing Flows & Signaling

### 6.1 WHEP Signaling & WebRTC Connection
WebRTC connections are negotiated using the WHEP (WebRTC HTTP Egress Protocol) standard. The backend proxies signaling messages to shield MediaMTX.

```mermaid
sequenceDiagram
    actor Client as Browser Player
    participant API as FastAPI Backend
    participant Redis as Redis Viewer Tracker
    participant MTX as MediaMTX

    Client->>API: POST /api/streams/{stream_id}/live/whep (SDP Offer)
    API->>API: Validate viewer capacity limits
    API->>Redis: Increment vms:viewers:{stream_id}
    API->>MTX: POST /v3/config/paths/get/{stream_id} (Check Codec)
    
    alt H.264
        API->>MTX: POST /whip_whep_endpoint/{stream_id} (SDP Offer)
    else H.265 (HEVC)
        API->>API: TranscoderManager.ensure_transcoder(stream_id)
        Note over API: FFmpeg starts transcoding to {stream_id}_h264
        API->>MTX: POST /whip_whep_endpoint/{stream_id}_h264 (SDP Offer)
    end

    MTX-->>API: 201 Created (SDP Answer + Location Header)
    API-->>Client: 201 Created (SDP Answer + Masked Location Header)
```

### 6.2 Viewer Disconnect and Delayed Shutdown
When a viewer closes the WebRTC player:
1. A `DELETE` request is sent to the signaling endpoint, or the watchdog detects the session timeout.
2. The active session count in Redis is decremented.
3. If the stream codec is H.265 and the active viewer count reaches **0**:
   - A **60-second delayed shutdown timer** is initiated.
   - If a new viewer connects within 60 seconds, the timer is cancelled and the transcoder remains active.
   - If the timer expires with no active viewers, FFmpeg is terminated and the temporary MediaMTX path `{stream_id}_h264` is removed.

---

## 7. Edge Push TCP Receiver Architecture

Custom edge devices push video over a proprietary protocol on TCP Port `9999`.

```mermaid
graph LR
    Edge[Edge Device] -->|1. Header + Frame Payloads| Receiver[Edge TCP Receiver :9999]
    Receiver -->|2. Validate Credentials| DB[(Database)]
    Receiver -->|3. Extract NAL Units| Parser[Protocol Parser]
    Parser -->|4. Pipe Raw Stream| FF[FFmpeg Remuxer]
    FF -->|5. RTSP Publish| MTX[MediaMTX Path]
```

### 7.1 Protocol Frame Parsing
- **Config Packet**: Contains device authentication details, camera serial number, stream profile, resolution, and codec information (H.264/H.265).
- **Frame Packet**: Contains timestamps and raw NAL units. The parser separates keyframes (I-frames) and delta frames (P/B frames) before piping them directly to FFmpeg.

---

## 8. Recording and Safety Net Recovery

### 8.1 Recording Flow
MediaMTX writes files directly to storage and notifies the backend upon completion.

```mermaid
sequenceDiagram
    participant Cam as Camera Stream
    participant MTX as MediaMTX
    participant Webhook as FastAPI webhook
    participant DB as Relational Database

    Cam->>MTX: RTP H.264 / H.265 Video Stream
    Note over MTX: Writes segments locally (e.g. 60s)
    MTX->>Webhook: POST /api/recordings/segment-complete (File Path + stream_id)
    Webhook->>Webhook: Run ffprobe to extract actual duration and keyframes
    Webhook->>DB: Insert into recording_segments (idempotency check)
    Webhook-->>MTX: 200 OK
```

### 8.2 Safety Net Recovery (Watchdog)
To prevent gaps in case of missed webhooks or server restarts, a background loop runs dynamically based on the `INDEXER_INTERVAL_SECONDS` setting:
1. Scans the local recording directory for MP4 files.
2. Reconciles directory listings with the database `recording_segments` table.
3. Indexes missing files by parsing file timestamps and extracting media metadata using `ffprobe`.
4. Deletes database references pointing to files that no longer exist on disk.

---

## 9. Playback & Timeline Services

### 9.1 Timeline API
The timeline api provides contiguous playback blocks from database segments.

```mermaid
graph TD
    Segments[Raw Database Segments] --> Sort[Sort by start_ts]
    Sort --> Merge[Merge Overlapping/Adjacent Segments]
    Note over Merge: Merge threshold = 5 seconds
    Merge --> Timeline[Compute Playable Time Intervals & Gaps]
    Timeline --> Cache[Cache in Redis for 60s]
```

### 9.2 Playback Seeking Strategy
- **Single Segment Queries**: If the requested playback range falls entirely within a single MP4 segment, the file is streamed directly to the browser (using native HTTP Range requests).
- **Multi-Segment Queries**: If the range spans across multiple files, the backend dynamically constructs a concat list and invokes FFmpeg on-the-fly to stream a continuous concat MP4 to the client, avoiding player buffering gaps.

---

## 10. Database Schema (ERD)

The relational database houses configuration metadata, segment indices, session states, and active transcoders.

```mermaid
erDiagram
    cameras {
        uuid id PK
        int source_camera_id UK
        string name
        string make
        boolean active
        boolean synced_from_api
        datetime created_at
    }

    camera_streams {
        uuid id PK
        uuid camera_id FK
        string stream_id UK
        string profile_type
        string resolution
        int fps
        string codec
        string stream_url
        string stream_mode
        string stream_source
        datetime last_push_seen
        datetime pull_failed_since
        string status
        boolean always_on
    }

    recording_segments {
        int id PK
        string stream_id FK
        string file_path UK
        float start_ts
        float end_ts
        datetime created_at
    }

    webrtc_sessions {
        uuid id PK
        string session_id UK
        string stream_id FK
        uuid user_id
        string status
        string protocol
        string client_ip
        datetime created_at
        datetime ended_at
    }

    stream_transcoders {
        string stream_id PK, FK
        int pid
        string status
        int viewer_count
        datetime started_at
        datetime stopped_at
        string error_message
    }

    cameras ||--o{ camera_streams : "owns"
    camera_streams ||--o{ recording_segments : "stores"
    camera_streams ||--o{ webrtc_sessions : "tracks"
    camera_streams ||--o| stream_transcoders : "manages"
```

---

## 11. Redis Key Registry

| Redis Key Template | Data Type | Purpose | TTL |
| :--- | :--- | :--- | :--- |
| **`vms:stats:realtime:{stream_id}:{sess_id}`** | String (JSON) | Caches browser WebRTC player statistics (FPS, bitrate, packet loss) | 30 seconds |
| **`vms:lock:stream:{stream_id}`** | String | Prevents concurrent API actions (like path re-registration) | 30 seconds |
| **`vms:timeline:{stream_id}:{date}`** | String (JSON) | Caches computed timeline intervals to optimize DB query performance | 60 seconds |
| **`vms:push:heartbeat:{stream_id}`** | String | Tracks edge device active push status | 15 seconds |

---

## 12. Background Schedulers & Watchdogs

All background loops run inside the FastAPI service lifecycle.

```mermaid
gantt
    title Background Loop Intervals
    dateFormat  X
    axisFormat %s
    
    section Schedulers
    Sync upstream cameras (10s)         :active, s1, 0, 10
    Transcoder watchdog checks (15s)    :active, s2, 0, 15
    WebRTC session checks (10s)         :active, s3, 0, 10
    Health monitor loop (10s)           :active, s4, 0, 10
    Gap recovery cron (300s)            :active, s5, 0, 300
    Archive retention cleanup (600s)    :active, s6, 0, 600
```

- **Upstream Sync Scheduler (10s)**: Queries Video Server API to dynamically add or delete paths.
- **Transcoder Watchdog (15s)**: Scans active transcoders. If an FFmpeg process crashed but active viewers exist, it auto-replaces the process.
- **WebRTC Session Watchdog (10s)**: Compares database session IDs against active MediaMTX connections, pruning dead sessions.
- **Health Monitor (10s)**: Performs TCP health checks on coturn (TURN) and cameras to update system statuses.
- **Gap Recovery Loop (300s / Configurable)**: Audits directories for missing files to index (Safety Net). Controlled by `INDEXER_INTERVAL_SECONDS`.
- **Archive Retention Loop (600s)**: Purges records and deletes MP4 files older than the camera's configured `archiveDays`.

---

## 13. Failure Scenarios and Recovery Paths

### 13.1 RTSP Camera Pull Fails
- **Detection**: MediaMTX logs connection errors; health monitor detects TCP timeout.
- **Action**: Stream transitions to `CONNECTING` or `OFFLINE`.
- **Recovery**: The stream manager attempts retries. The web interface displays a loading state and falls back to LL-HLS segments.

### 13.2 Edge Device Disconnects
- **Detection**: The Edge Receiver socket closes, or the Redis heartbeat (`vms:push:heartbeat:{stream_id}`) expires.
- **Action**: FFmpeg remuxer terminates; path source becomes unpublishable.
- **Recovery**: If in `AUTO` mode, the stream manager waits for the timeout before falling back to `RTSP Pull` if a URL is available.

### 13.3 MediaMTX Restarts
- **Detection**: Backend connection to MediaMTX API fails.
- **Action**: System enters degraded mode; live streams stall.
- **Recovery**: Upon reconnection, the backend re-registers all paths configured in the DB.

### 13.4 Duplicate Recording Webhooks
- **Detection**: Segment completed webhook fires multiple times for the same file.
- **Action**: Unique constraint on `(stream_id, file_path)` intercepts insertion.
- **Recovery**: Duplicate notifications are discarded, preventing database index pollution.

### 13.5 H.265 Transcoding FFmpeg Crashes
- **Detection**: Transcoder watchdog detects an exited process (`returncode is not None`) while `active_viewers > 0`.
- **Action**: The watchdog restarts the FFmpeg transcoder instantly.
- **Recovery**: Stream is restored without client disconnects.

---

## 14. Scaling and Performance Estimation

### 14.1 Stream Scaling Metrics

| Metric | 100 Cameras (10% H.265) | 500 Cameras (20% H.265) | 1000 Cameras (30% H.265) |
| :--- | :--- | :--- | :--- |
| **Active Transcoders (Peak)** | 10 | 100 | 300 |
| **CPU Load (Cores)** | 8 Cores | 64 Cores | 192 Cores |
| **RAM Utilization** | 16 GB | 64 GB | 128 GB |
| **Storage Write Rate** | 50 MB/s | 250 MB/s | 500 MB/s |
| **Redis Memory** | 10 MB | 50 MB | 100 MB |
| **Database IOPS** | 50 | 250 | 500 |

### 14.2 Media Stream Resource Usage
- **H.264 Raw Stream**: Negligible CPU impact on VMS server (straight write-to-disk and WebRTC proxying).
- **H.265 Transcoded Stream**: Requires transcoding. Spawning **1** libx264 transcoder process uses approximately **0.5 CPU cores** (at 1080p, 15fps, `ultrafast` preset).
- **Optimization Strategy**: NVIDIA NVENC (GPU-accelerated) or Intel QSV should be enabled in production environments to scale beyond 20 concurrent transcoders.
