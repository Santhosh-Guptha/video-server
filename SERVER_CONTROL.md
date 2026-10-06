# Server Control

Open **Server Control** in the sidebar. This screen groups operations, camera sources/configuration, storage deletion, and streaming defaults.

- **Live** permits viewing. Stopping it disconnects WebRTC viewers and rejects new WebRTC/HLS requests. Recording can continue independently.
- **Recording** permits MediaMTX recording under the existing profile policy and background gap recovery. Stopping it cancels recovery jobs; live can continue.
- **Ignore camera** blocks both, removes its media paths, and skips health probes. Upstream synchronization cannot reset this choice. Unignore restores that camera's saved live/recording choices.
- **Pause entire server** turns off global live and recording permissions without changing individual camera preferences. The API/UI stays available to re-enable them.
- **Retention** accepts 1–365 days per camera; blank inherits the server default. The cleanup worker applies it to completed recordings. Changing retention does not alter camera hardware archive settings.
- **Delete recordings** requires recording to be stopped for the selected cameras, a cutoff time, a preview, and explicit confirmation. Recent segments remain protected. A persisted deletion cutoff prevents recovery from fetching this history again. Failed filesystem deletions remain indexed and are reported.
- **Camera sources & configuration** allows changing the upstream HTTP(S) URL and reuses the existing manual camera editor. Press Sync Cameras after changing the URL. Cached upstream inventories are isolated by URL, so a failed new source cannot import the old source's cache.
- **Streaming & retention defaults** contains WebRTC buffering, profile selection, RTSP limits, global retention and recording quota. Quota remains opt-in.

Operator policy is stored atomically in `backend/app/configs/server_controls.json`, excluded from Git. Keep this file in deployment backups. Camera IDs and stream aliases bind policies to all profiles of a camera. This implementation uses the application's single backend process; multiple independent backend writers are not supported.

Turning a camera off does not change that camera's firmware or affect another VMS outside this server. Deleting Linux files frees space inside WSL; shrinking the Windows VHD requires separate offline compaction.

The one-file installer includes the same implementation in `automated-setup/patch-src`. No additional dependency or manual database migration is required.

## Streaming stability

## Camera archive playback (initial adapter)

Playback now has separate **Server recordings** and **Camera / NVR archive** screens. Camera mode bypasses the server recording lookup, relays a bounded device archive request without saving video, and offers play, stop and clip download. Select a past start time in the browser's local timezone and 1–15 minutes. Epoch timestamps are sent to the UNV adapter. Closing the camera screen stops its video request.

This initial camera-only adapter supports UNV/Uniview URL structure with an identifiable channel. Unknown channels are rejected instead of guessing channel 1. If upstream manufacturer metadata is missing, choose UNV explicitly only for a compatible device; save the adapter in that camera's archive configuration; the backend uses the saved choice. Other manufacturers, ONVIF archive discovery/calendar, audio, arbitrary timeline seeking and browser codec conversion remain pending. Manufacturer identity or a constructed URL is not proof that footage exists.

The existing download endpoint accepts `source=camera|server|auto`, `disposition=inline|attachment` and `adapter=configured|unv`. Camera-only requests never fall back to local recordings; server-only requests never connect to a camera. Automatic mode preserves existing fallback selection. All requests now reject invalid intervals and clips longer than 15 minutes. First data has a 20-second deadline; subsequent reads have a 30-second idle timeout. RTSP capacity limits apply, and failures before the first data produce an HTTP error. Receiving MP4 headers is not proof of decoded video. Video is copied without re-encoding; unsupported browser codecs may require clip download.

Profile paths now use the same stream ID across registration and health workers. This prevents parent-camera aliases from being repeatedly recreated/removed. Active H.264 compatibility paths survive unrelated YAML updates. A player receiving an operator-stop response stops retrying instead of falling back to HLS.


## Fleet operations release

- Select cameras across pages, review a bulk action, then apply live/recording/ignore/retention changes. Each batch is validated before changes are saved; unknown camera IDs reject the whole batch. A maximum of 500 cameras is supported per batch.
- Organize cameras using sites, tags, favorites and notes. Search includes sites/tags. Filters cover source, ignored cameras, favorites and recording permission. Lists show 25 cameras per page; selection persists across pages.
- Export the filtered inventory as CSV. Formula-like cell values are escaped for spreadsheet safety.
- Control writes carry a policy revision. Stale browser changes are rejected with a refresh instruction. Failed filesystem writes do not publish unsaved policy in memory.
- Diagnostics report MediaMTX readiness, Redis connectivity, conversion/recovery workload, TURN configuration and storage quota. These checks do not prove every camera's video is decodable.
- Activity history retains the latest 500 control events locally. It is not a tamper-proof, user-attributed security audit. Runtime reconciliation failures remain visible and can be retried.
- Export and restore versioned policy backups with preview and explicit confirmation. Restore requires matching camera IDs, preserves current credentials, source URLs, notes and recording deletion cutoffs, and does not restore video or recreate cameras.
- Initial UI JavaScript is split by screen. HLS loads only when needed; a crash recovery view offers reload without affecting backend recording. WebRTC reconnect backoff includes jitter to reduce simultaneous retries.

## Commercial release gates still open

Server Control → Diagnostics now includes **Deployment readiness**, with customer-installed and hosted-instance reports. Reports are read-only and exclude credentials and private endpoint addresses. A configured setting is not proof of network reachability, security or video quality. Download the JSON report to track the open release requirements.

From the backend directory, run `venv/bin/python -m app.deployment_readiness --mode onprem` (or `--mode hosted`). Exit code **2** means release requirements remain unmet; it does not mean the camera service is down. The existing installation defaults to `DEPLOYMENT_MODE=onprem`. Setting `DEPLOYMENT_MODE=hosted` intentionally refuses backend startup until hosted release gates are implemented and verified. There is no environment-variable override that claims identity or tenant isolation is complete.

Both deployment models are planned. The hosted design is one isolated instance per customer; this release does not provide shared-database tenant isolation. Sign-in, server-enforced user roles and protected direct media delivery are **still pending**, and the readiness report explicitly marks them as blockers. Keep this installation on a trusted network in the meantime.

This release improves the existing single-server application; it does not certify production readiness. Before selling deployments, finish identity and role permissions, HTTPS/certificate provisioning, signed upgrade/rollback procedures, retention/audit requirements for the target customer, restore drills, and sustained camera/device/network compatibility tests. Multi-tenant hosting also requires isolated tenants, storage and credentials. Never describe configured paths or successful signaling as proof of uninterrupted decoded video.


## Per-camera configuration alignment

Each Server Control camera row now includes archive configuration, live/recording/ignore switches, retention override, organization, effective retention, and profile metadata (resolution, FPS, bitrate, codec, always-on and conversion flags). Local cameras link directly to their existing source/encoder editor. Upstream-managed source and encoder fields remain read-only; local operator overrides are independent of upstream synchronization.

Archive configuration is also editable from Playback for the selected camera. Saved fields are access enabled, adapter, archive stream profile, maximum clip length (1–15 minutes), first-data timeout (5–60 seconds) and idle timeout (5–60 seconds). The backend validates and enforces these values; request parameters cannot override the saved adapter. A selected stream must belong to the camera. The UI reports effective access separately from the saved switch, including the server archive feature gate. Disabling a camera archive setting blocks new requests; existing archive transfers finish or can be stopped in the player.

Writes require a matching policy revision; stale edits return 409. Archive edits do not restart live streams. Settings are included in policy backup/restore; restoring an older backup without archive fields preserves current archive settings. A missing saved profile is rejected at playback rather than silently selecting another camera. These settings do not claim to configure device SD-card retention, audio, firmware or unsupported manufacturer's archive APIs. Global RTSP capacity, TURN, database and server disk quota remain server settings.


## Hikvision archive adapter and request diagnostics

The camera archive adapter now accepts Hikvision-compatible `/Streaming/Channels/<track>` sources (including the ISAPI prefix) and constructs `/Streaming/tracks/<track>` with UTC start/end timestamps. Live-only query arguments are removed. This follows Hikvision's published RTSP playback format: https://www.hikvision.com/content/dam/hikvision/vn/webinar/Thang3_Hikvision_Tich_Hop_He_Thong_Overview-of-3rd-Party-Integration.pdf

Choose Hikvision in saved camera archive settings for compatible devices. Configuration diagnostics validate the adapter against the saved stream path before enabling playback. This is URL validation, not proof of archive access. Device authorization errors are classified without exposing RTSP credentials, logged with camera ID and interval, and retained in memory for 15 minutes (at most 500 cameras). The player retrieves the matching failed interval's diagnostic after a media error, without opening another camera connection. Archive permission may differ from live-view permission; a working live feed does not prove archive access.

Archive access is now independent of individual live/recording switches and of a global live-only stop. Archive must be enabled, the camera active and not ignored, and the global archive feature enabled. A full server pause (both global live and recording off) still blocks archive access.
