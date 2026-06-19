# Streaming Architecture Document
**VMS Project Document ID**: VMS-SAD-007  
**Target Audience**: Streaming Specialists, Infrastructure Engineers  
**Owner**: Streaming Media Architect  

---

## 1. Ingress Stream Lifecycle
- **RTSP Pull**: VMS pulls feed from source URL -> mounts path in MediaMTX.
- **Edge Push**: Device connects to port `9999` -> parsed to RTSP -> publishes to MediaMTX.
- **AUTO Detection**: Scheduler attempts RTSP pull. If edge device pushes stream, VMS suspends PULL loop and serves PUSH feed.

## 2. Egress Protocols
- **WebRTC WHEP**: Real-time viewing (<1s latency).
- **LL-HLS**: Fallback streaming using fragmented MP4 chunks.

## 3. Codec Handling (H.264 vs H.265)
- **H.264**: Passed directly to WHEP socket.
- **H.265**: Spawns an on-demand FFmpeg process to transcode video packets to H.264.
