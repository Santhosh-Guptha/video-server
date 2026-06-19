# Performance Tuning Guide
**VMS Project Document ID**: VMS-PTG-022  
**Target Audience**: Systems Engineers, Performance Architects  
**Owner**: Performance Team  

---

## 1. WebRTC Latency Reduction
- Enable `zerolatency` tuning parameter on FFmpeg H.265 transcoders.
- Use `ultrafast` preset to reduce processing delays.

## 2. Storage Bandwidth Tuning
- Enforce `RECORD_HD_ONLY=true` to skip recording low-resolution feeds.
- Align segment durations to 60 seconds to decrease disk write wear.
