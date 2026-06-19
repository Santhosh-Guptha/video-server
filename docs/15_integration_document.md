# Integration Document
**VMS Project Document ID**: VMS-INT-015  
**Target Audience**: Systems Integrators, Deployments  
**Owner**: Systems Integrator  

---

## 1. System Integration Mapping
```
React Frontend ◄───(WS Status / HTTP APIs)───► FastAPI Backend
FastAPI Backend ◄──(JSON REST Config APIs)───► MediaMTX Server
FastAPI Backend ◄──(Locks / Stats / Cache)───► Redis Cache
FastAPI Backend ◄──(FFmpeg Sub-processes)───► MediaMTX (Publish)
```

## 2. Signaling Integration Sequence
1. UI initiates WHEP call.
2. Backend intercepts, validates against limits, and queries MediaMTX path configuration.
3. MediaMTX returns candidate endpoints.
4. Backend responds to UI player.
