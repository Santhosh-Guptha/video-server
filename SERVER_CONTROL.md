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
