# Software Requirements Specification (SRS)
**Project**: Enterprise Video Management System (VMS)  
**Owner**: Software Architect  

---

## 1. System Overview
The VMS backend is written in FastAPI, using SQLAlchemy for database operations, and Redis for distributed caching and signaling states. The media server is MediaMTX, supported by FFmpeg for transcoding.

## 2. Architecture Goals
- High concurrency: Support up to 500 camera sync pathways.
- Low footprint: Minimize idle CPU utilization.

## 3. Functional Requirements
- **FR-1**: Backend must sync cameras with Upstream API.
- **FR-2**: Media WebRTC signaling must proxy via standard HTTP/SDP formats.
- **FR-3**: Daily timeline must list available seek blocks and offline gaps.

## 4. Non-Functional Requirements
- **Availability**: 99.9% availability for API gateways.
- **Scalability**: Support scaling transcoders horizontally using hardware acceleration.
- **Performance**: API responses must return in < 200ms.
- **Latency**: WebRTC streaming latency must remain under 1.0 second.
- **Reliability**: Crashed transcoder processes must recover within 15 seconds.
- **Maintainability**: Unified single configuration source of truth (`config.py`).
- **Security**: Token-based authentication and strict CORS headers.
- **Auditability**: SQLite/Postgres logs for all session creations and terminations.
