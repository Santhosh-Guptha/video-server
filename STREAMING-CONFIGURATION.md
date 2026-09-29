# Streaming configuration — 25 September 2026

## Smooth live viewing — 28 September 2026

Full Wall reuses the existing video elements and WebRTC sessions. It no longer opens a duplicate grid in the background. The selected source profile remains unchanged, including HD. The default four-camera layout limits simultaneous browser decoding; increase the tile count only while measured FPS remains close to the camera's output.

Streaming Settings includes a live smoothing buffer target, defaulting to 100 ms and adjustable from 0–1000 ms. Supported browsers receive this value through `RTCRtpReceiver.jitterBufferTarget`; other browsers retain their automatic buffer. A larger target trades more delay for tolerance of uneven arrival. It is a hint, not a maximum latency guarantee. It neither changes resolution nor modifies recordings. Changes apply when streams next open.

The statistics overlay reports recent packet loss over the sampling interval, RTT from the selected ICE candidate pair, and measured receiver buffer delay. Receiver buffer delay is calculated from the changes in `jitterBufferDelay` and `jitterBufferEmittedCount`, following the [W3C WebRTC specification](https://www.w3.org/TR/webrtc/). This excludes camera encoding, upstream transit and server delay; it must not be interpreted as end-to-end latency.

On 28 September, the first four wall feeds decoded at 1920×1080. A five-minute MediaMTX log sample also contained many source timeouts and RTP packet-loss events across the deployment. UI improvements cannot repair missing upstream packets or unreachable camera endpoints; those feeds require source/network correction before uninterrupted playback is possible.

The fresh `Ubuntu-24.04` installation runs the `develop` branch at `/home/santhosh/video-server`. Current UI: `http://172.22.3.86:5173/`. Camera configuration is synced from `https://monolithic-portal.iviscloud.net/api/cameras/camera-videoserver`. The most recent sync imported 326 cameras, 307 enabled. This is configuration inventory, not a promise that every source is reachable.

Open **Streaming Settings** in the app to edit HD/NORMAL/MOBILE selection, WebRTC retry and HLS fallback policy. These values persist in `backend/app/configs/streaming_overrides.json`. The default grid, live, focus, and playback profiles are HD. The wall prefers the actual MAIN/HD stream and falls back when unavailable. A profile name alone does not prove pixel resolution; use the tile's connection statistics to inspect decoded width and height.

MediaMTX v1.21.0 handles RTSP ingest, WHEP and recording. Coturn is installed and active with browser TURN credentials. WSL exposes HTTP on 5173, WebRTC TCP ICE on 8000, and TURN TCP on 3478 through Windows portproxy. Direct UDP requires a separate route; portproxy is TCP-only. Browser success does not prove a TURN relay was selected. Browser/device codec support, camera keyframe interval, source resolution, uplink capacity and packet loss affect startup and latency. H.265 is passed through when supported or converted to H.264 at the source resolution within the conversion limit. No setting can make an SD source genuine full HD.

Fresh-install validation on 25 September: all five services (`video-backend`, `mediamtx`, `coturn`, `nginx`, `redis-server`) active; `/health`, `/api/policy`, and `/api/settings/streaming` returned HTTP 200; the live wall enumerated 32 online cameras and decoded multiple WebRTC feeds. Recording segments were indexed through successful HTTP 200 webhooks. A new MP4 recording returned HTTP 206 to a Range request and ffprobe identified 1280×720 H.264 video. Many other camera endpoints are currently unreachable (`i/o timeout`), reject credentials (`401`), or contain malformed RTSP URLs. Resolve those issues in the upstream camera configuration and verify camera-network routes/VPN before expecting every feed to play. The first wall page includes streams decoded at 704×480, 704×576 and 1280×720; HD viewing requires a reachable HD source. Full-wall stability, every-device compatibility, and recording playback on this new install have not yet been verified.

For widest browser support, configure each camera's MAIN stream with H.264, a keyframe interval near one second, 15–25 FPS, and a sustainable bitrate. Set resolution to the maximum detail the camera and network actually support. Keep a lower bitrate substream for constrained links. Source URLs and credentials should be corrected in the upstream portal; the installer does not modify cameras.

Recording storage uses the camera's already-compressed video without re-encoding it, preserving the source quality and avoiding CPU load from hundreds of simultaneous encoders. In **Streaming Settings**, set **Maximum recording retention** to limit local disk use without reducing picture quality. The cap is 30 days by default and a camera's shorter archive period still applies; cleanup runs periodically and removes both expired files and their index entries. Changing the cap can delete older recordings, so choose it according to the required history. A 4 Mb/s camera uses roughly 43 GB per day before small container overhead; fewer retention days reduce total storage but not the write rate. To lower the write rate while retaining HD detail, adjust the camera's own main-stream bitrate or supported smart encoding in the upstream camera configuration, then check motion detail and WebRTC compatibility. The server does not mass-change camera encoder settings.

On 25 September, the first four live-wall tiles all decoded WebRTC video during a spot check (one at 1280×720, three at 704×576), and a sampled 1280×720 H.264 recording decoded cleanly. MediaMTX also reported substantial RTP packet loss, recorder timestamp resets, timeouts and authentication failures on other camera paths. These source/network faults can cause live stutter and recording gaps; retention tuning does not repair them.

Useful checks in Ubuntu:

```bash
sudo systemctl status video-backend mediamtx coturn nginx redis-server
curl -fsS http://127.0.0.1:5173/health
curl -fsS http://127.0.0.1:5173/api/settings/streaming
sudo journalctl -u mediamtx -u video-backend -n 100 --no-pager
```

Backend listens on localhost port 8006. The UI and API are served through Nginx port 5173. MediaMTX configuration is `/opt/mediamtx/mediamtx.yml`. Windows startup/port forwarding needs an elevated run of `automated-setup/setup.ps1` on this new WSL distribution. The installed services run while WSL is running; Windows sleep stops access.
## Current source audit and startup fixes

Run `python3 scripts/camera_source_audit.py` from the repository root for a credential-free list of invalid stream IDs. On 25 September, 42 of 570 configured stream URLs were malformed (41 missing a host, one invalid numeric host). The server now excludes these from startup and background re-registration rather than repeatedly sending them to MediaMTX. Upstream portal records must supply real URLs; the application cannot infer missing camera addresses. Separate MediaMTX logs show camera network timeouts and HTTP 401 responses. Those require a route/VPN and valid camera credentials respectively.

H.265-to-H.264 startup now allows different camera conversions to start concurrently within the configured capacity, and each checks only its own MediaMTX path for readiness. If HD conversion cannot publish, the server selects a ready H.264 stream from the same camera when available. The frontend monitors decoded-frame progress and reconnects a stalled receiver. The wall opens with four maximum-quality streams by default to reduce simultaneous decoding pressure; the operator can select 9–36 tiles, and the chosen grid size persists in the browser. These changes reduce avoidable startup delay; they do not eliminate source outages or browser decode limits when many high-resolution feeds play simultaneously.

## Shared RTSP ingest and connection reservations

Streaming Settings exposes **RTSP connections per endpoint**, default 6 (1�128), and a capacity table. The endpoint is the RTSP hostname and port, not a server-wide limit. Choose a value supported by the camera/NVR and leave headroom for external clients. DNS aliases are not merged.

Identical source URLs share one MediaMTX `_ingest_` path; live viewing, recording and matching probes consume that local relay. Distinct main/substream URLs reserve separate slots. Helpers do not record; existing logical paths retain their recording policies and resolution. The reservation remains while an ingest is idle/reconnecting so background work cannot steal its slot. This is a conservative configured-source budget, not a measurement of camera firmware capacity.

Existing sources above the configured limit are retained during migration or a limit reduction. Additional sources are rejected with HTTP 429 until capacity is available. Fresh endpoints admit HD/MAIN profiles first. Camera playback and other temporary RTSP processes share the endpoint budget and a global two-connection budget. Recovery work is serialized per stream with two concurrent jobs; timed-out processes are killed and reaped. Local recording playback needs no camera slot.

The controls apply to this deployment's single backend process. They cannot lock the camera against other applications or coordinate multiple video-server instances. Enforce exclusivity in camera/NVR accounts or network access controls if needed. All viewers should connect to this server. No universal six-session camera limit is assumed.

The one-file installer includes these changes through its bundled patch sources. Existing installations receive a one-time MediaMTX configuration migration/restart. The capacity API is `/api/settings/streaming/rtsp-capacity`; it reports reservations and blocked paths without source credentials. Camera codec, keyframe timing, upstream packet loss and device decoding still determine startup and smoothness.
