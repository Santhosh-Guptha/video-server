# Streaming configuration — 25 September 2026

The fresh `Ubuntu-24.04` installation runs the `develop` branch at `/home/santhosh/video-server`. Current UI: `http://172.22.3.86:5173/`. Camera configuration is synced from `https://monolithic-portal.iviscloud.net/api/cameras/camera-videoserver`. The most recent sync imported 326 cameras, 307 enabled. This is configuration inventory, not a promise that every source is reachable.

Open **Streaming Settings** in the app to edit HD/NORMAL/MOBILE selection, WebRTC retry and HLS fallback policy. These values persist in `backend/app/configs/streaming_overrides.json`. The default grid, live, focus, and playback profiles are HD. The wall prefers the actual MAIN/HD stream and falls back when unavailable. A profile name alone does not prove pixel resolution; use the tile's connection statistics to inspect decoded width and height.

MediaMTX v1.21.0 handles RTSP ingest, WHEP and recording. Coturn is installed and active with browser TURN credentials. WSL exposes HTTP on 5173, WebRTC TCP ICE on 8000, and TURN TCP on 3478 through Windows portproxy. Direct UDP requires a separate route; portproxy is TCP-only. Browser success does not prove a TURN relay was selected. Browser/device codec support, camera keyframe interval, source resolution, uplink capacity and packet loss affect startup and latency. H.265 is passed through when supported or converted to H.264 at the source resolution within the conversion limit. No setting can make an SD source genuine full HD.

Fresh-install validation on 25 September: all five services (`video-backend`, `mediamtx`, `coturn`, `nginx`, `redis-server`) active; `/health`, `/api/policy`, and `/api/settings/streaming` returned HTTP 200; the live wall enumerated 32 online cameras and decoded multiple WebRTC feeds. Recording segments were indexed through successful HTTP 200 webhooks. A new MP4 recording returned HTTP 206 to a Range request and ffprobe identified 1280×720 H.264 video. Many other camera endpoints are currently unreachable (`i/o timeout`), reject credentials (`401`), or contain malformed RTSP URLs. Resolve those issues in the upstream camera configuration and verify camera-network routes/VPN before expecting every feed to play. The first wall page includes streams decoded at 704×480, 704×576 and 1280×720; HD viewing requires a reachable HD source. Full-wall stability, every-device compatibility, and recording playback on this new install have not yet been verified.

For widest browser support, configure each camera's MAIN stream with H.264, a keyframe interval near one second, 15–25 FPS, and a sustainable bitrate. Set resolution to the maximum detail the camera and network actually support. Keep a lower bitrate substream for constrained links. Source URLs and credentials should be corrected in the upstream portal; the installer does not modify cameras.

Useful checks in Ubuntu:

```bash
sudo systemctl status video-backend mediamtx coturn nginx redis-server
curl -fsS http://127.0.0.1:5173/health
curl -fsS http://127.0.0.1:5173/api/settings/streaming
sudo journalctl -u mediamtx -u video-backend -n 100 --no-pager
```

Backend listens on localhost port 8006. The UI and API are served through Nginx port 5173. MediaMTX configuration is `/opt/mediamtx/mediamtx.yml`. Windows startup/port forwarding needs an elevated run of `automated-setup/setup.ps1` on this new WSL distribution. The installed services run while WSL is running; Windows sleep stops access.