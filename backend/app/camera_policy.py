"""
camera_policy.py — Centralized Runtime Policy Controller

All tuneable parameters for VMS behavior live here.
Operators can override most settings via environment variables in .env
(values are read from `settings` in config.py where env-override is supported).

To change any policy:
    - Edit this file for code-level defaults
    - Use .env for production overrides without code changes

NEVER hardcode these constants in other modules. Always import from here.
"""

from .config import settings

# ── Source Validation ──────────────────────────────────────────────────────────
# When True: only cameras synced from UPSTREAM_CAMERA_API_URL are allowed.
# Rejects unknown edge pushes, uploads, playback, and RTSP pulls.
# Read from settings so it can be toggled via .env (STRICT_CAMERA_VALIDATION=false).
STRICT_CAMERA_VALIDATION: bool = settings.strict_camera_validation

# When True: unknown edge push devices are auto-registered (dev/test mode).
# Only active when STRICT_CAMERA_VALIDATION=false.
ALLOW_UNKNOWN_EDGE_DEVICES: bool = settings.allow_unknown_edge_devices

# ── Recording ─────────────────────────────────────────────────────────────────
# When True: only MAIN (HD) profile streams have record=true in MediaMTX.
# NORMAL/SUB streams get record=false — they remain available for live viewing only.
# Benefits: ~50% storage reduction, lower I/O, faster timeline generation.
RECORD_HD_ONLY: bool = settings.record_hd_only

# ── Upstream Sync ──────────────────────────────────────────────────────────────
# How often to re-sync camera list from upstream Video Server API (in hours).
UPSTREAM_SYNC_INTERVAL_HOURS: int = 1

# ── Camera Health Watchdog ─────────────────────────────────────────────────────
# Interval between full health check cycles (seconds).
# Cameras are pinged via ffprobe ONLY when MediaMTX reports ready=false.
CAMERA_PING_INTERVAL_SECONDS: int = settings.camera_ping_interval_seconds

# Timeout for each ffprobe RTSP reachability check (seconds).
CAMERA_PING_TIMEOUT_SECONDS: int = settings.camera_ping_timeout_seconds

# Maximum number of concurrent ffprobe invocations per watchdog cycle.
# Prevents overloading the network on large camera deployments.
CAMERA_PING_MAX_CONCURRENT: int = 10

# ── Edge Push Priority ─────────────────────────────────────────────────────────
# If a push heartbeat was seen within this window (seconds), the camera is
# treated as EDGE_PUSH and RTSP health checks are skipped entirely.
EDGE_PUSH_HEARTBEAT_TIMEOUT_SECONDS: int = settings.edge_push_heartbeat_timeout_seconds

# How often the edge push watchdog checks for stale heartbeats (seconds).
EDGE_PUSH_CHECK_INTERVAL_SECONDS: int = settings.edge_push_check_interval_seconds

# ── MediaMTX Safety ───────────────────────────────────────────────────────────
# When True: all MediaMTX path updates use GET → compare → PATCH.
# Never use DELETE+ADD which triggers config reloads and kills WebRTC sessions.
MEDIAMTX_PATCH_ONLY: bool = True

# ── H.265 Transcoding ─────────────────────────────────────────────────────────
# Enable on-demand H.265 → H.264 transcoding for browser WebRTC compatibility.
ENABLE_H265_TRANSCODING: bool = True

# Idle timeout before stopping an unused transcoder process (seconds).
TRANSCODER_IDLE_TIMEOUT_SECONDS: int = settings.transcoder_grace_period_seconds

# ── WebRTC ────────────────────────────────────────────────────────────────────
# Maximum concurrent WHEP sessions per camera stream.
MAX_WEBRTC_SESSIONS_PER_CAMERA: int = 100

# ── Playback ──────────────────────────────────────────────────────────────────
# Redis cache TTL for timeline segment queries (seconds).
TIMELINE_CACHE_SECONDS: int = 60

# ── Recording Recovery ────────────────────────────────────────────────────────
# How often the gap recovery loop runs (hours — derived from settings).
RECORDING_RECOVERY_INTERVAL_HOURS: float = settings.recovery_interval_seconds / 3600
