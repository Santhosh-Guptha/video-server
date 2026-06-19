# Functional Requirements Specification (FRS)
**Project**: Enterprise Video Management System (VMS)  
**Owner**: Senior Functional Analyst  

---

## 1. Camera Registry Sync
- **Purpose**: Synchronize camera definitions from the upstream server.
- **Workflow**: Scheduler calls upstream URL -> parses cameras JSON -> upserts rows -> reconfigures MediaMTX paths.
- **Inputs**: Upstream URL, Timeout, Sync Interval.
- **Outputs**: Synced cameras, logs, database updates.
- **Validations**: Check database unique constraint on camera ID.
- **Business Rules**: If `STRICT_CAMERA_VALIDATION=true`, delete any local streams not present in upstream payload.
- **Exception Handling**: Fall back to `backup_cameras.json` if upstream is unreachable.
- **Acceptance Criteria**: Registry updates dynamically without service restart.

## 2. WebRTC Live View
- **Purpose**: Serve low-latency WebRTC streams to client browser players.
- **Workflow**: Player sends WHEP POST (Offer) -> Backend validates and proxies to MediaMTX -> Returns SDP Answer.
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
