# Business Requirements Document (BRD)
**Project**: Enterprise Video Management System (VMS)  
**Owner**: Senior Business Analyst  

---

## 1. Executive Summary
The Enterprise Video Management System (VMS) is a centralized video streaming, recording, and camera management platform designed to support high-fidelity, real-time security monitoring. It acts as an intelligent layer between IP camera networks and security personnel, allowing seamless browser-based viewing without active plugins.

## 2. Business Problem Statement
Current security operations rely on legacy VMS products that require ActiveX/Internet Explorer plugins, suffer from 5-10s live streaming latency, consume massive storage for useless high-resolution sub-streams, and collapse under network bandwidth congestion on remote WAN cells.

## 3. Existing Challenges
- High bandwidth usage during multi-camera grid views.
- Restrictive corporate firewalls blocking live WebRTC streams.
- Lack of automatic failover for edge device push feeds.
- Poor storage retention control leading to disk full crashes.

## 4. Proposed Solution
A modern, decoupled, REST and WebSockets-driven VMS utilizing MediaMTX, WebRTC WHEP for sub-second viewing latency, LL-HLS fallback, and dynamic profile downscaling for active security wall grids.

## 5. Business Objectives
- Reduce live streaming latency to <1.0 second.
- Reduce WAN bandwidth consumption on camera grids by 50%.
- Maintain 99.9% uptime for safety-critical monitoring environments.

## 6. Stakeholders
- Business Operations (Security personnel)
- Systems Integrators (Deployments)
- Finance (Storage & Bandwidth cost auditing)
- DevOps & IT Support

## 7. Scope
- WebRTC WHEP and HLS egress streaming.
- Dynamic registry synchronization and backup cache fallback.
- Daily timeline generation and playback seeking.
- Edge Push TCP Receiver listening protocols.

## 8. Out of Scope
- AI-based object detection analytics (LPR, Face Matching) on the VMS core.
- Multi-cloud storage segment replication.

## 9. Business Processes
- **Camera Registry Onboarding**: Automated sync from Upstream API to database registry.
- **Archive Retention**: Daily purge of video data matching camera policy retention days.

## 10. Business Workflows
- **Camera Offline Alerting**: Watchdog detects offline state -> pushes websocket alert to UI -> logs event.

## 11. User Types
- **L1 Operator**: Views live wall, seeks timelines, exports clips.
- **System Administrator**: Modifies configuration properties, syncs registries, manages user profiles.
- **DevOps Engineer**: Configures system services, manages storage arrays, monitors logs.

## 12. Customer Journey
1. Operator logs into browser UI.
2. Selects a 2x2 grid layout; cameras load dynamically in NORMAL/SUB profile to save bandwidth.
3. Operator double-clicks a camera; stream upgrades to HD profile for focused inspection.
4. Camera goes offline; operator is alerted and clicks playback to check recordings up to the gap.

## 13. Use Cases
- **Real-time Facility Monitoring**: Security guards watching a live wall.
- **Incident Investigation**: Seeks daily timeline for gap detection and exports continuous MP4 evidence.

## 14. Functional Requirements
- System must synchronize camera metadata from Upstream API.
- Live stream player must automatically fall back to HLS if WebRTC fails.

## 15. Non-Functional Requirements
- **Latency**: WebRTC streaming latency < 1.0 second.
- **Security**: Strict token authorization on all APIs.

## 16. Assumptions
- Upstream camera registry API is reachable during initial setup.
- Target VM has FFmpeg and MediaMTX binaries installed.

## 17. Constraints
- SQLite DB write locks under high concurrent streams.
- Port 3478 (Coturn) must be open for external clients.

## 18. Risks
- Restrictive corporate firewalls blocking WebRTC ports. (Mitigated by Coturn TURN relay and HLS fallback).

## 19. Dependencies
- Coturn Server for ICE candidate resolution.
- Upstream camera endpoint availability.

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
