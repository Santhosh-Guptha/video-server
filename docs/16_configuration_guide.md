# Configuration Guide
**VMS Project Document ID**: VMS-CFG-016  
**Target Audience**: Operations Teams, Installers  
**Owner**: Deployments Team  

---

## 1. MediaMTX Configuration
Production settings in `/opt/mediamtx/mediamtx.yml`:
```yaml
webrtcAddress: :8889
webrtcICEServers2:
  - url: stun:stun.l.google.com:19302
  - url: turn:172.20.100.235:3478?transport=udp
    username: admin
    password: admin123
hlsSegmentCount: 8
```

## 2. Storage Setup
- Mount the video storage array to `/opt/video-server/backend/data/recordings`.
- Ensure directory permissions allow reading and writing by the backend process.
