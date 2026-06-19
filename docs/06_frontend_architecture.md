# Frontend Architecture Document
**Project**: Enterprise Video Management System (VMS)  
**Owner**: Senior Frontend Architect  

---

## 1. React Architecture & Component Hierarchy
```
App.tsx
├── Header (Status Indicators)
├── Sidebar (Camera Registry list)
└── GridWall (Live Grid View)
    └── VideoPlayer (WHEP/Hls.js Player)
        ├── WebRTC Hook (Connection management)
        └── StatsOverlay (HUD Display)
```

## 2. WebRTC Player & HLS Fallback Layer
- **Player Flow**: Creates RTCPeerConnection -> fetches STUN/TURN -> posts local SDP Offer -> receives Answer.
- **Failover Timer**: 10-second connection watchdog. If `connectionState` does not reach `connected`, the player destroys WebRTC socket resources and loads the HLS stream URL fallback.

## 3. WebSocket Status Layer
- Persists state connection to `ws://YOUR_SERVER_IP:8000/ws/status`.
- Receives JSON payload updates describing camera connectivity states (ONLINE, OFFLINE, CONNECTING) and active viewer metrics.
