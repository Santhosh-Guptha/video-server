# Backend Architecture Document
**Project**: Enterprise Video Management System (VMS)  
**Owner**: Senior Backend Architect  

---

## 1. Folder Structure
The backend is structured into domain-specific modules:
- `app/config.py`: Single configuration class.
- `app/db.py`: Database engine and session handlers.
- `app/models.py`: Database schemas (Camera, Stream, Segment).
- `app/webrtc.py`: WebRTC session management.
- `app/transcoder.py`: FFmpeg transcoder lifecycle.
- `app/stream_manager.py`: State transition engine.
- `app/main.py`: Endpoint routes and background loops.

## 2. Layered Architecture
```
    [ API Controller Layer ]
               │
               ▼
    [ Service & Watchdog Layer ]
               │
               ▼
    [ Repository & Model Layer ]
               │
               ▼
       [ Database (SQL) ]
```

## 3. Data Flow Diagram: Segment Webhook Indexing
```
MediaMTX (Segment Finished) -> Webhook Post -> Check DB -> Query Stats via FFprobe -> Save Segment -> Clear Timeline Cache
```
