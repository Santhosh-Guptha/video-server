# Recording Architecture Document
**VMS Project Document ID**: VMS-RAD-008  
**Target Audience**: Storage Engineers, Operations Leads  
**Owner**: Storage Architect  

---

## 1. Direct-to-Disk Recording
- MediaMTX segment recorder writes raw source streams as fragmented MP4 files (`.mp4`) directly to `/opt/video-server/backend/data/recordings/{stream_id}/YYYY-MM-DD/`.
- This ensures 100% fidelity without consuming transcoding CPU cycles during writes.

## 2. Safety-Net Indexer
- A background scheduler loop runs periodically based on the `INDEXER_INTERVAL_SECONDS` setting.
- Scans files on disk -> reconciles differences with database -> registers missing segments -> deletes references to manually removed files.

## 3. Storage Retention & Purging
- Daily cleanup loop evaluates segment ages against camera `archiveDays`.
- Executes disk delete calls and removes orphaned database entries.
