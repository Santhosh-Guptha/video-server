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

This release improves the existing single-server application; it does not certify production readiness. Before selling deployments, finish identity and role permissions, HTTPS/certificate provisioning, signed upgrade/rollback procedures, retention/audit requirements for the target customer, restore drills, and sustained camera/device/network compatibility tests. Multi-tenant hosting also requires isolated tenants, storage and credentials. Never describe configured paths or successful signaling as proof of uninterrupted decoded video.
