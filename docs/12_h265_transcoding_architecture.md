# H.265 Transcoding Architecture Document
**Project**: Enterprise Video Management System (VMS)  
**Owner**: Transcoding Architect  

---

## 1. HEVC Browser Limitations
Modern browsers do not support native playback of H.265 (HEVC) streams over WebRTC. The VMS resolves this with an **On-Demand Transcoding Engine**.

## 2. Transcoder Lifecycle
- **Startup**: Triggered when a browser requests WHEP signaling for an H.265 stream. The backend spawns a shared FFmpeg process transcoding the source stream to `{stream_id}_h264`.
- **Viewer Tracking**: Active viewers are registered in Redis.
- **Cooldown & Shutdown**: When active viewers drop to 0, a 60-second grace timer is initiated. If no new viewer connects, the FFmpeg process is terminated.
