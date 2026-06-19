# Troubleshooting Guide
**VMS Project Document ID**: VMS-TSG-020  
**Target Audience**: Customer Support Engineers, SysAdmins  
**Owner**: L2/L3 Support Team  

---

## 1. WebRTC Signaling Fails
- **Symptom**: WHEP request returns `503 Service Unavailable` or player stays black.
- **Root Cause**: Transcoder limit hit, or TURN credentials out of sync.
- **Resolution**: Check Coturn logs; restart the `video-backend` service.

## 2. Disk Space Full
- **Symptom**: Backend fails with `No space left on device`.
- **Root Cause**: Recordings folder filled up local partition.
- **Resolution**: Run segment pruning manually:
  ```bash
  find /opt/video-server/backend/data/recordings -name "*.mp4" -mtime +15 -delete
  ```
