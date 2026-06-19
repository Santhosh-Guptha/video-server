"""
================================================================================
  VMS Runtime Policy — Centralized Configuration Controller
================================================================================

  This is the SINGLE source of truth for ALL VMS streaming and recording behavior.

  Edit this file to change any behavior. No code changes required elsewhere.
  All settings can also be overridden via environment variables in .env.

  ── Deployment Modes ──────────────────────────────────────────────────────────

  Mode 1: Low Bandwidth (Recommended for production)
    LIVE_STREAM_PROFILE = "NORMAL"   → Live uses SUB stream
    PLAYBACK_PROFILE    = "HD"       → Playback uses MAIN stream
    RECORD_HD_ONLY      = True       → Only MAIN recorded

  Mode 2: Maximum Quality (Control rooms)
    LIVE_STREAM_PROFILE = "HD"
    PLAYBACK_PROFILE    = "HD"
    RECORD_HD_ONLY      = True

  Mode 3: Performance Optimized (Low-end hardware)
    LIVE_STREAM_PROFILE = "NORMAL"
    PLAYBACK_PROFILE    = "NORMAL"
    RECORD_HD_ONLY      = False
    RECORD_NORMAL       = True

  Mode 4: Adaptive Enterprise (Default)
    ENABLE_ADAPTIVE_PROFILE = True
    GRID_VIEW_PROFILE       = "NORMAL"   → 2x2 / 3x3 grid uses SUB
    FOCUS_VIEW_PROFILE      = "HD"       → 1x1 single camera uses MAIN
    PLAYBACK_PROFILE        = "HD"

================================================================================
"""

from .config import settings

# ── Profile name → ProfileType mapping ────────────────────────────────────────
# Maps the human-friendly policy names ("HD", "NORMAL", "MOBILE") to DB enum values.
# Never change these mappings — they must stay in sync with models.ProfileType.

PROFILE_MAP = {
    "HD":     "MAIN",    # Full resolution / high-bitrate main stream
    "NORMAL": "SUB",     # Reduced resolution / low-bitrate sub stream
    "MOBILE": "MOBILE",  # Mobile-optimized ultra-low bitrate stream
}

# ── Camera Source Validation ───────────────────────────────────────────────────

# When True: only cameras synced from the upstream Video Server API are accepted.
# Rejects unknown edge push devices, unregistered RTSP sources, and manual uploads.
# Set to False in dev/test environments only.
STRICT_CAMERA_VALIDATION: bool = settings.strict_camera_validation

# When True: unknown edge-push devices are auto-registered (dev/test mode only).
# Only takes effect when STRICT_CAMERA_VALIDATION = False.
ALLOW_UNKNOWN_EDGE_DEVICES: bool = settings.allow_unknown_edge_devices

# ── Recording Policy ───────────────────────────────────────────────────────────

# Record only HD (MAIN profile) streams.
# Benefits: ~50% storage reduction, lower disk I/O, faster timeline generation.
# Set False if you want to record NORMAL or MOBILE streams as well.
RECORD_HD_ONLY: bool = settings.record_hd_only

# Record NORMAL (SUB profile) streams.
# Only active when RECORD_HD_ONLY = False.
RECORD_NORMAL: bool = settings.record_normal

# Record MOBILE profile streams.
# Only active when RECORD_HD_ONLY = False.
RECORD_MOBILE: bool = settings.record_mobile

# ── Live Stream Profile Policy ─────────────────────────────────────────────────

# Default profile for live streaming when adaptive mode is disabled.
# Options: "HD" | "NORMAL" | "MOBILE"
LIVE_STREAM_PROFILE: str = settings.live_stream_profile

# Enable adaptive profile switching based on the UI layout grid size.
# When True, the per-layout profile overrides below apply.
# When False, LIVE_STREAM_PROFILE is always used.
ENABLE_ADAPTIVE_PROFILE: bool = settings.enable_adaptive_profile

# Profile used for single-camera focus view (1x1 layout).
FOCUS_VIEW_PROFILE: str = settings.focus_view_profile

# Profile used for multi-camera grid view (2x2, 3x3 layouts).
GRID_VIEW_PROFILE: str = settings.grid_view_profile

# Profile used for mobile/low-bandwidth clients.
MOBILE_VIEW_PROFILE: str = settings.mobile_view_profile

# ── Playback Policy ────────────────────────────────────────────────────────────

# Profile to use when serving recorded video for playback.
# Options: "HD" | "NORMAL" | "MOBILE"
PLAYBACK_PROFILE: str = settings.playback_profile

# When the requested playback profile stream has no recordings,
# allow falling back to NORMAL (SUB) stream recordings.
PLAYBACK_ALLOW_NORMAL_FALLBACK: bool = settings.playback_allow_normal_fallback

# Allow falling back to MOBILE recordings for playback (rarely needed).
PLAYBACK_ALLOW_MOBILE_FALLBACK: bool = False

# Available playback speed multipliers exposed to the UI.
PLAYBACK_SPEEDS: list = [0.5, 1.0, 2.0, 4.0, 8.0]

# ── WebRTC Policy ──────────────────────────────────────────────────────────────

# Master switch: enable/disable WebRTC (WHEP/WHIP) session management.
ENABLE_WEBRTC: bool = settings.enable_webrtc

# When WebRTC is unavailable or fails, fall back to HLS streaming.
ENABLE_HLS_FALLBACK: bool = True

# WebRTC session establishment timeout (seconds).
WEBRTC_CONNECTION_TIMEOUT_SECONDS: int = 10

# Maximum concurrent WHEP sessions per camera stream.
# Prevents server overload on popular streams.
MAX_WEBRTC_SESSIONS_PER_CAMERA: int = settings.max_webrtc_sessions_per_camera

# ── H.265 Transcoding Policy ───────────────────────────────────────────────────

# Enable on-demand H.265 → H.264 transcoding for browser WebRTC/HLS compatibility.
# Browser players do not natively support H.265; this transparently converts streams.
ENABLE_H265_TRANSCODING: bool = settings.enable_h265_transcoding

# FFmpeg encoder to use for H.265 → H.264 transcoding.
# "libx264"    — software encoding (any CPU, high compatibility)
# "h264_nvenc" — NVIDIA GPU hardware encoding (requires CUDA driver)
# "h264_qsv"   — Intel Quick Sync hardware encoding
TRANSCODER_VCODEC: str = settings.transcoder_vcodec

# FFmpeg preset — controls speed vs. compression trade-off.
# "ultrafast" = lowest latency, highest CPU usage.
# Other options: "superfast", "veryfast", "faster", "fast", "medium"
TRANSCODER_PRESET: str = settings.transcoder_preset

# FFmpeg tune — optimizes encoder behavior.
TRANSCODER_TUNE: str = "zerolatency"

# Time (seconds) to keep a transcoder running after all viewers disconnect.
# Prevents thrashing when viewers quickly reconnect.
TRANSCODER_IDLE_TIMEOUT_SECONDS: int = settings.transcoder_grace_period_seconds

# Maximum number of simultaneous H.265 transcoders.
# Each transcoder consumes 1-3 CPU cores. Size based on your server capacity.
MAX_ACTIVE_TRANSCODERS: int = settings.max_active_transcoders

# ── Recording Segment Policy ───────────────────────────────────────────────────

# Duration of each individual recording segment file (seconds).
# Shorter = finer-grained timeline scrubbing, more files.
# Longer  = fewer files, coarser scrubbing.
SEGMENT_DURATION_SECONDS: int = settings.segment_time_seconds

# Master switch: enable/disable all recording.
ENABLE_RECORDING: bool = True

# How often the gap-recovery loop attempts to backfill missing segments (hours).
RECORDING_RECOVERY_INTERVAL_HOURS: float = settings.recovery_interval_seconds / 3600

# ── Playback Timeline Policy ───────────────────────────────────────────────────

# Redis cache TTL for timeline segment queries (seconds).
# Higher = fewer DB queries, potentially stale data.
TIMELINE_CACHE_SECONDS: int = 60

# Minimum gap duration (seconds) between segments to be treated as a real gap.
# Smaller gaps (e.g., <5s) are merged into the previous segment.
TIMELINE_MERGE_THRESHOLD_SECONDS: int = 5

# Default zoom level for the playback timeline UI.
# Options: "24h" | "6h" | "1h"
TIMELINE_DEFAULT_ZOOM: str = "24h"

# ── Edge Push Policy ───────────────────────────────────────────────────────────

# Enable edge-push (RTSP-push from edge device → VMS) support.
ENABLE_EDGE_PUSH: bool = True

# When True: edge-push cameras take priority over RTSP pull.
# The watchdog will not restart RTSP pull for cameras with active edge pushes.
EDGE_PUSH_PRIORITY: bool = True

# Time window (seconds) within which an edge push heartbeat must be seen
# for the camera to be treated as EDGE_PUSH mode.
EDGE_PUSH_HEARTBEAT_TIMEOUT_SECONDS: int = settings.edge_push_heartbeat_timeout_seconds

# How often the edge-push watchdog checks for stale heartbeats (seconds).
EDGE_PUSH_CHECK_INTERVAL_SECONDS: int = settings.edge_push_check_interval_seconds

# ── RTSP Watchdog Policy ───────────────────────────────────────────────────────

# Enable periodic RTSP reachability health checks via ffprobe.
ENABLE_RTSP_HEALTH_CHECK: bool = True

# Interval between full health check cycles (seconds).
CAMERA_PING_INTERVAL_SECONDS: int = settings.camera_ping_interval_seconds

# Timeout for each ffprobe RTSP reachability check (seconds).
CAMERA_PING_TIMEOUT_SECONDS: int = settings.camera_ping_timeout_seconds

# Maximum concurrent ffprobe invocations per watchdog cycle.
CAMERA_PING_MAX_CONCURRENT: int = 10

# ── Upstream Camera Sync Policy ────────────────────────────────────────────────

# How often to re-sync camera list from the upstream Video Server API (minutes).
UPSTREAM_SYNC_INTERVAL_MINUTES: int = settings.upstream_sync_interval_minutes

# ── Storage Retention Policy ───────────────────────────────────────────────────

# Enable automatic deletion of recordings older than DEFAULT_RETENTION_DAYS.
ENABLE_RETENTION: bool = settings.enable_retention

# Number of days to retain recordings before automatic deletion.
DEFAULT_RETENTION_DAYS: int = settings.default_retention_days

# ── MediaMTX Safety Policy ─────────────────────────────────────────────────────

# When True: all MediaMTX path updates use GET → compare → PATCH only.
# Never DELETE+ADD (which triggers full config reloads and kills WebRTC sessions).
MEDIAMTX_PATCH_ONLY: bool = True

# When True: allow DELETE+ADD reconfiguration as a last-resort fallback.
# Only set True if PATCH-only mode is causing issues.
ALLOW_DELETE_ADD_RECONFIGURATION: bool = False


# ── Policy helper: resolve profile_type for a given context ───────────────────

def resolve_live_profile(layout_size: int = 0) -> str:
    """
    Returns the DB ProfileType string ("MAIN", "SUB", "MOBILE") to use
    for live streaming, based on the current policy and optional layout size.

    Args:
        layout_size: Number of cameras currently in the grid (0 = unknown/default).
                     1 = single/focus view → may use HD profile.
                     2+ = grid view → use NORMAL profile to save bandwidth.

    Returns:
        A ProfileType string: "MAIN", "SUB", or "MOBILE"
    """
    if ENABLE_ADAPTIVE_PROFILE and layout_size > 0:
        profile_name = FOCUS_VIEW_PROFILE if layout_size == 1 else GRID_VIEW_PROFILE
    else:
        profile_name = LIVE_STREAM_PROFILE
    return PROFILE_MAP.get(profile_name.upper(), "SUB")


def resolve_playback_profile() -> str:
    """
    Returns the DB ProfileType string to use for playback stream selection.
    Applies the PLAYBACK_PROFILE policy with optional fallback chain.

    Returns:
        A ProfileType string: "MAIN", "SUB", or "MOBILE"
    """
    return PROFILE_MAP.get(PLAYBACK_PROFILE.upper(), "MAIN")


def get_recording_profiles() -> list:
    """
    Returns a list of ProfileType strings ("MAIN", "SUB", "MOBILE")
    that are eligible for recording under the current policy.
    """
    if RECORD_HD_ONLY:
        return ["MAIN"]
    profiles = ["MAIN"]
    if RECORD_NORMAL:
        profiles.append("SUB")
    if RECORD_MOBILE:
        profiles.append("MOBILE")
    return profiles


def should_record_profile(profile_type_value: str) -> bool:
    """
    Returns True if a stream with the given profile_type should be recorded.

    Args:
        profile_type_value: ProfileType enum value string, e.g. "MAIN", "SUB", "MOBILE"
    """
    allowed = get_recording_profiles()
    return profile_type_value in allowed
