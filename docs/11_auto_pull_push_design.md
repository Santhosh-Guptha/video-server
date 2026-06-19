# AUTO / PULL / PUSH Design Document
**Project**: Enterprise Video Management System (VMS)  
**Owner**: Systems Architect  

---

## 1. Stream Mode Definitions
- **PULL**: Strict RTSP pull from source.
- **PUSH**: Expects incoming edge push.
- **AUTO**: Hybrid fallback. Defaults to RTSP pull; automatically transitions to Edge Push if a device connects, using heartbeats to monitor state.

## 2. State Machine Transitions
```
[OFFLINE] ──► RTSP Pull fails
[CONNECTING] ──► RTSP Pull succeeds ──► [ONLINE_PULL]
[ONLINE_PULL] ──► Edge Device Connects ──► [ONLINE_PUSH]
[ONLINE_PUSH] ──► Heartbeat Timeout ──► [CONNECTING] (RTSP Pull Retry)
```
