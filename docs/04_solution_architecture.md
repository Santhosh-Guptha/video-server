# Solution Architecture Document
**VMS Project Document ID**: VMS-SAD-004  
**Target Audience**: Systems Engineers, Developers, Deployments  
**Owner**: Enterprise Solution Architect  

---

## 1. High-Level Architecture
The system consists of decoupled client players, an API controller layer, a media engine, and caching databases.

```
+-----------------------------------------------------------+
|                      React Frontend                       |
+-----------------------------------------------------------+
                              │ (HTTP / WS / WebRTC WHEP)
                              ▼
+-----------------------------------------------------------+
|                      FastAPI Backend                      |
+-----------------------------------------------------------+
       │                      │                      │
       ▼                      ▼                      ▼
+──────────────+      +──────────────+      +───────────────+
|   MediaMTX   |      |    Redis     |      | SQLite/Postgr |
+──────────────+      +──────────────+      +───────────────+
       │                      │
       ▼                      ▼
+──────────────+      +──────────────+
|  FFmpeg (Tx) |      | Edge TCP Rec |
+──────────────+      +──────────────+
```

## 2. Low-Level Architecture Components
- **Frontend**: React-based UI wall mapping streams dynamically.
- **Backend**: FastAPI App hosting REST routes, websocket handlers, and schedulers.
- **MediaMTX**: Egress proxy for RTSP, WebRTC, and HLS.
- **Redis**: Rate limiting, viewer count, and timeline cache.
- **FFmpeg**: On-demand transcoders for H.265 streams.

## 3. Deployment Architecture
The platform is deployed inside standard Linux VMs (Ubuntu 20.04/22.04 LTS) using systemd service configurations.

## 4. Sequence Diagram: Edge Device Push Stream Ingress
```
Edge Device               Edge TCP Receiver               MediaMTX               FastAPI DB
    │                             │                          │                       │
    ├──────1. Connect TCP :9999──►│                          │                       │
    │                             ├──────2. Authenticate────►│                       │
    │                             │◄─────3. Auth Result──────┤                       │
    ├──────4. Send Video Frames──►│                          │                       │
    │                             ├──────5. FFmpeg RTSP─────►│                       │
    │                             │                          ├────6. Sync Registry──►│
```
