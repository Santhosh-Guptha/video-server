# Camera Sync Architecture Document
**VMS Project Document ID**: VMS-CSD-010  
**Target Audience**: Integration Architects, Software Engineers  
**Owner**: Integration Architect  

---

## 1. Sync Process
1. Query `UPSTREAM_CAMERA_API_URL`.
2. Parse JSON response array.
3. Match local database rows (upsert metadata).
4. If camera is deactivated, remove path from MediaMTX.
5. If camera is newly activated, add path to MediaMTX.

## 2. Backup Caching Fallback
- If the HTTP call to the Upstream API fails, load cached data from `backend/app/backup_cameras.json` to prevent server downtime.
