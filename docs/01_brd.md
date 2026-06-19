# Business Requirements Document (BRD)
**VMS Project Document ID**: VMS-BRD-001  
**Target Audience**: Executive Board, Customer Project Managers, Systems Architects  
**Owner**: Senior Business Analyst  

---

## 1. Executive Summary
The Enterprise Video Management System (VMS) is a centralized, high-throughput video streaming, recording, and camera monitoring middleware. It bridges legacy or modern IP camera networks (via RTSP and proprietary Edge TCP push) with standard HTML5 browser clients using sub-second WebRTC (WHEP) live streaming and fragmented MP4 seekable playbacks.

## 2. Business Problem Statement
Legacy VMS products suffer from significant operational and commercial bottlenecks:
- **ActiveX Dependencies**: Require outdated Internet Explorer environments or insecure custom client installs.
- **Latency**: High live streaming latency (5-10 seconds) compromises real-time security response.
- **Bandwidth Waste**: Streaming high-resolution feeds for multi-camera grids leads to grid congestion.
- **Storage Instability**: Lack of automated data cleanup causes disk-full server crashes.

## 3. Existing Challenges
- High egress bandwidth consumption over cellular or remote WAN connections.
- UDP streaming packets blocked by corporate firewalls.
- Dynamic camera registry configuration sync gaps.
- Manual file index mismatches after storage drive recovery.

## 4. Proposed Solution
A centralized FastAPI and MediaMTX web gateway providing plugin-free browser viewing.
- **WebRTC WHEP**: Real-time viewing (<1 second latency).
- **Adaptive downscaling**: Automatically serves Normal/Mobile profiles in camera grids.
- **Safety Net Indexer**: Reconciles database records against physical storage files automatically.
- **On-Demand Transcoding**: Shared transcoder processes convert H.265 feeds to H.264 only when viewed.

## 5. Business Objectives
- Establish sub-second video latency on standard web browsers.
- Save up to 50% network bandwidth on multi-camera security walls.
- Reduce storage hardware footprint by 30-50% via HD-only recording policies.

## 6. Stakeholders
- **Security Operations**: Monitor live walls and export clips.
- **Deployments Team**: Configure camera connections and VM services.
- **Financial Auditors**: Optimize cloud and storage capacity expenses.

## 7. Scope
- WebRTC WHEP/WHIP signaling proxies.
- Low-Latency HLS (LL-HLS) backup fallback.
- Daily timeline generation, recording gap identification, and concat video playback.
- Custom TCP Edge push stream remuxing.

## 8. Out of Scope
- AI-based video analytics (Face recognition, ANPR) on the central VMS server.
- Cloud bucket replication or external block storage integration.

## 9. Business Processes
- **Registry Sync**: Periodic cron queries upstream registries to map local database states.
- **Storage Pruning**: Storage retention watchdogs purge data exceeding camera archive days.

## 10. Business Workflows
- **Offline Recovery**: Camera disconnects -> logs offline state -> suspends recording hooks -> triggers alert -> restarts loop on recovery.

## 11. User Types
- **Security Guard (L1)**: Live monitoring, timeline seekers, exports evidence.
- **Super Administrator (L2)**: System configurations, sync settings, user roles.
- **System Engineer (L3)**: Hardware deployments, database maintenance, network setup.

## 12. Customer Journey
1. Log in securely via HTTPS.
2. Load 3x3 layout; cameras load dynamically in `NORMAL` (SUB) profile to save network bandwidth.
3. Switch single camera to focused view; backend upgrades stream to `HD` (MAIN) profile.
4. If WebRTC is blocked by firewall, player falls back to LL-HLS fallback.
5. If incident occurred, seeks playback timeline and exports evidence.

## 13. Use Cases
- **Industrial Facility Monitoring**: Real-time security walls.
- **Evidence Retrieval**: Stitching multi-file recording segments for legal compliance.

## 14. Functional Requirements
- System must synchronize camera metadata from Upstream URL.
- Codec transcoding must trigger automatically and clean up on zero active viewers.

## 15. Non-Functional Requirements
- **Latency**: WebRTC streaming latency < 1.0 second.
- **Security**: Token-based REST authorization.

## 16. Assumptions
- Server VM is configured with public STUN/TURN (Coturn) servers.
- Upstream Camera registry follows the defined JSON format.

## 17. Constraints
- High database write loads require proper WAL journaling.
- GPU limits concurrent transcoder processes.

## 18. Risks
- Restrictive corporate firewalls blocking UDP/TURN ports. (Mitigated by Coturn TURN relay and HLS fallback).

## 19. Dependencies
- Redis server availability for viewer counters.
- Upstream camera registry endpoint.

## 20. Success Criteria
- Deployment on production VM runs without import errors.
- Active latency overlay displays <1.0 second.

## 21. Business Benefits
- Lower network subscription costs on remote WAN cells.
- Zero client installation footprint.

## 22. ROI Analysis
- Replaces hardware-intensive heavy-client VMS systems.
- Average storage savings of $120/camera/year due to HD-only recording policies.

## 23. Future Enhancements
- Integration with local edge AI processing units.
