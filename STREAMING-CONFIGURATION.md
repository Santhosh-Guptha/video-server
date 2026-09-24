# Streaming configuration — 24 September 2026

## Running deployment

- UI: http://172.16.2.243:5173/
- Ubuntu distribution: `Ubuntu-22.04`
- Checkout: `/home/santhosh/video-server`
- Branch: `develop`, base commit `7937d80` plus local repairs (not pushed).
- MediaMTX: `v1.21.0`.
- Camera configuration upstream: https://monolithic-portal.iviscloud.net/api/cameras/camera-videoserver

## Quality policy currently applied

The systemd override `/etc/systemd/system/video-backend.service.d/quality.conf` contains:

```ini
[Service]
Environment="GRID_VIEW_PROFILE=HD"
Environment="LIVE_STREAM_PROFILE=HD"
Environment="FOCUS_VIEW_PROFILE=HD"
Environment="PLAYBACK_PROFILE=HD"
```

The wall selects the available MAIN/HD source. If that source is offline, it uses an online source from the same camera and labels the lower-quality fallback. A profile called HD is not proof of its actual resolution: observed sources range from 704×480 to 2688×1520. The browser connection statistics show decoded resolution.

H.265 passes through when the browser explicitly offers it. Otherwise, an H.264 stream of the same profile or an on-demand H.264 conversion is used. Conversion preserves pixel dimensions; it does not invent detail. The configured limit is 10 simultaneous conversion processes, shared among viewers of each source. Native-compatible streams do not consume that conversion capacity.

Additional backend settings in `/home/santhosh/video-server/backend/.env`:

```dotenv
ENABLE_WEBRTC=true
ENABLE_H265_TRANSCODING=true
ENABLE_HLS_FALLBACK=true
MAX_ACTIVE_TRANSCODERS=10
TRANSCODER_VCODEC=libx264
TRANSCODER_PRESET=ultrafast
TRANSCODER_TUNE=zerolatency
TRANSCODER_GRACE_PERIOD_SECONDS=60
RECORD_HD_ONLY=true
ENABLE_RECORDING=true
SEGMENT_TIME_SECONDS=60
DEFAULT_RETENTION_DAYS=30
```

These are the observed effective settings, not an instruction to overwrite the entire `.env`. Preserve database, upstream and TURN credentials. Systemd environment overrides take precedence over `.env`.

## Media and network configuration

The active file is `/opt/mediamtx/mediamtx.yml`:

```yaml
webrtcLocalUDPAddress: 0.0.0.0:8189
webrtcLocalTCPAddress: 0.0.0.0:8000
webrtcAdditionalHosts: [172.27.154.190, 172.16.2.243, localhost, 127.0.0.1]
webrtcICEServers2: []
```

Browser ICE settings include the existing coturn service at `turn:172.16.2.243:3478?transport=tcp`. TURN credentials are supplied to the browser for authenticated relay access. Coturn is running; a successful direct connection does not mean TURN carried that session. No coturn `server-relay` bypass is enabled.

WSL and Windows addresses can change after restart. TCP portproxy forwarding does not forward UDP. A direct UDP route must exist for remote clients to use UDP 8189; otherwise TCP ICE or TURN is needed. Separate-device network validation is still required.

## Playback and freeze recovery

- Successful signaling does not mark a tile LIVE; decoded video is required.
- A connected receiver with no decoded-frame progress for 8 seconds reconnects, except while deliberately paused or while the tab is hidden.
- Connection attempts have a 20-second timeout; bounded retries use backoff before HLS fallback.
- HD MP4 recordings are retained in `backend/data/recordings`. One 1920×1080 H.265 recording was verified in the UI, including progression across segments and seeking. This does not prove all cameras or all device decoders work.
- Source outages, long keyframe intervals, packet loss, device decoding limits and server conversion capacity can still cause delay. Zero lag on every device is not guaranteed.

## Camera encoder settings to review

For broad browser support, configure a usable MAIN stream at the camera's actual maximum supported resolution and an H.264 baseline-compatible output without B-frames. H.265 is useful where the viewing device supports it; conversion is needed elsewhere. See [MediaMTX codec guidance](https://github.com/bluenviron/mediamtx/blob/main/docs/2-features/26-webrtc-specific-features.md).

As a starting point, use a one-second keyframe interval, 15–25 FPS and a bitrate the camera uplink and viewer network can sustain. These are tuning recommendations, not changes made to the remote cameras. Test image detail and motion before increasing bitrate. Do not upscale SD sources merely to display a 1080p label.

## Operations

```bash
sudo systemctl status video-backend mediamtx coturn nginx
curl http://127.0.0.1:8005/api/policy
sudo systemctl daemon-reload
sudo systemctl restart video-backend
```

Frontend changes require `npm run build` in `frontend`, then publishing `dist` into `/var/www/video-server`. Restarting MediaMTX disconnects current viewers; avoid it for backend-only changes.

Rollback copies are under `/var/backups/video-server`. WSL must remain running and Windows must remain awake. The bundled Windows setup registers a logon task; it has not yet been run with Administrator rights on this host.

## Editable settings and unattended setup

Use Streaming Settings in the app for HD/NORMAL/MOBILE quality and recovery settings. Values persist in backend/app/configs/streaming_overrides.json and override the corresponding environment defaults.

The automated-setup/README.md contains the one-command entry points. The complete Linux installer successfully ran on this existing host on 24 September; clean-machine installation and Windows elevated networking remain unverified.

Ubuntu currently lacks its /var/lib/dpkg package database. Existing runtime dependencies work, but package installation or upgrades requiring apt are blocked until the distribution is repaired. The installer reports this instead of creating a false package database.
