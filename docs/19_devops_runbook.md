# DevOps Operations Runbook
**VMS Project Document ID**: VMS-DVR-019  
**Target Audience**: SREs, Systems Administrators  
**Owner**: DevOps Operations Team  

---

## 1. Monitoring & Logs
- Backend Logs: `sudo journalctl -u video-backend.service -f`
- MediaMTX Logs: `sudo journalctl -u mediamtx.service -f`

## 2. Backups
- Database: Backup SQLite db dynamically using the `sqlite3` CLI tool.
- Configuration: Store backup copies of `.env` and `mediamtx.yml`.

## 3. Disaster Recovery
- If disk space is full, run cleanups manually or delete old camera directories.
