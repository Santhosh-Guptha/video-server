# Functional Requirements Specification (FRS)
**VMS Project Document ID**: VMS-FRS-002  
**Target Audience**: Software Engineers, QA Leads, Tech Leads  
**Owner**: Senior Functional Analyst  

---

## 1. Camera Registry Synchronization
- **Purpose**: Synchronize local camera configurations with the upstream system.
- **Workflow**: 
  1. Scheduler calls `/api/cameras/sync` dynamically.
  2. Sync queries `UPSTREAM_CAMERA_API_URL`.
  3. Returns camera array -> matches database -> upserts camera streams.
  4. Updates path configurations in MediaMTX.
- **Inputs**: Upstream URL, Sync Timeout, Interval Minutes.
- **Outputs**: Synced cameras count, MediaMTX path definitions.
- **Validations**: Check database unique constraint on camera ID.
- **Business Rules**: If `STRICT_CAMERA_VALIDATION=true`, delete any local streams not present in upstream payload.
- **Exception Handling**: Fall back to `backup_cameras.json` if upstream is unreachable.
- **Acceptance Criteria**: Registry updates dynamically without service restart.

## 2. WebRTC Live View (WHEP)
- **Purpose**: Serve low-latency WebRTC streams to client browser players.
- **Workflow**:
  1. Browser sends WHEP POST (SDP Offer) to `/api/streams/{stream_id}/live/whep`.
  2. Backend validates active sessions and increments viewer counts in Redis.
  3. Intercepts HEVC/H.265 codecs -> spawns FFmpeg H.264 transcoder if needed.
  4. Proxies offer to MediaMTX -> receives SDP Answer.
  5. Responds with SDP Answer (201 Created) and session Location header.
  6. Trickle ICE candidates are negotiated via WHEP PATCH.
- **Inputs**: SDP Offer, stream ID, user ID.
- **Outputs**: SDP Answer, Location session ID, RTCPeerConnection active.
- **Validations**: Check viewer limits per stream.
- **Business Rules**: H.265 streams must trigger an on-demand FFmpeg H.264 transcoder process.
- **Exception Handling**: Fall back to HLS proxy if WebRTC session fails.
- **Acceptance Criteria**: Live streaming latency < 1 second.

## 3. Playback Timeline Seek
- **Purpose**: Show available recording segments and gaps for a date.
- **Workflow**: Query DB segments -> Merge contiguous files -> Compile timeline JSON.
- **Inputs**: Stream ID, Target Date.
- **Outputs**: Playback intervals, Gaps arrays, dates list.
- **Validations**: Date format validation (`YYYY-MM-DD`).
- **Business Rules**: Gaps are periods where no recording exists for > 5 seconds.
- **Acceptance Criteria**: Timeline loads in < 500ms.

## 4. HD-Only Recording
- **Purpose**: Write camera feeds directly to disk.
- **Workflow**: MediaMTX writes fMP4 fragments -> fires completed webhook -> indexes segment.
- **Inputs**: Completed segment file path, stream ID.
- **Outputs**: DB recording segment record.
- **Validations**: Verify file exists on disk.
- **Business Rules**: Only MAIN/HD profiles are recorded by default.
- **Acceptance Criteria**: Disk usage matches HD bandwidth footprint.
