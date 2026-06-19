# Database Design Document
**Project**: Enterprise Video Management System (VMS)  
**Owner**: Database Architect  

---

## 1. ERD & Schema
### Tables:
- `cameras`: Core camera identities.
- `camera_streams`: Egress profiles (HD, NORMAL, MOBILE) and RTSP paths.
- `recording_segments`: Fragmented MP4 file database index.
- `webrtc_sessions`: Active and historic WHEP player sessions.

## 2. Indexing Rules
- Unique index on `recording_segments(stream_id, file_path)`.
- Index on `recording_segments(start_ts, end_ts)` to speed up daily timeline queries.
