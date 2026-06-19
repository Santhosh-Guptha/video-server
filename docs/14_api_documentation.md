# API Documentation
**VMS Project Document ID**: VMS-API-014  
**Target Audience**: Integrators, UI Developers  
**Owner**: Backend Team  

---

## 1. Live Signaling (WHEP)
- **Endpoint**: `POST /api/streams/{stream_id}/live/whep?user_id={uuid}`
- **Purpose**: Negotiate WebRTC connection.
- **Headers**: `Content-Type: application/sdp`
- **Response**: SDP Answer string with status `201 Created`.

## 2. Playback Available Dates
- **Endpoint**: `GET /api/playback/{stream_id}/available-dates`
- **Purpose**: Get dates containing recordings.
- **Response**: `["2026-06-18", "2026-06-19"]`

## 3. Playback Timeline
- **Endpoint**: `GET /api/playback/{stream_id}/timeline?date={YYYY-MM-DD}`
- **Purpose**: FetchDaily timeline seek ranges and offline gaps.
