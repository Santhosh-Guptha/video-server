from typing import Any
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "camera-video-platform"
    enable_webrtc: bool = True
    # Switch default to postgresql+asyncpg for production, fallback to SQLite for local development without container
    database_url: str = "postgresql+asyncpg://vms_admin:vms_secure_password@localhost:5432/vms_db"
    redis_url: str = "redis://127.0.0.1:6379/0"
    mediamtx_api_url: str = "http://127.0.0.1:9997"
    mediamtx_webrtc_url: str = "http://127.0.0.1:8889"
    stun_servers: list[str] = ["stun:stun.l.google.com:19302"]
    turn_server_url: str = "turn:localhost:3478"
    turn_server_username: str = "vms_user"
    turn_server_credential: str = "vms_turn_password"

    upstream_camera_api_url: str = ""
    upstream_timeout_seconds: float = 10.0
    upstream_sync_interval_minutes: int = 5
    filter_private_ips: bool = False
    ffmpeg_path: str = "ffmpeg"
    recording_dir: str = "./data/recordings"
    hls_dir: str = "./data/hls"
    segment_time_seconds: int = 60
    max_subscribers_per_stream: int = 200
    ui_poll_seconds: int = 5
    scheduler_interval_seconds: int = 10
    recovery_interval_seconds: int = 300
    cleanup_interval_seconds: int = 600
    indexer_interval_seconds: int = 600

    recovery_rtsp_template: str = "{rtsp_url}?starttime={start_iso}&endtime={end_iso}"

    edge_receiver_host: str = "0.0.0.0"
    edge_receiver_port: int = 9999
    edge_receiver_enabled: bool = True
    allow_unknown_edge_devices: bool = False
    strict_camera_validation: bool = True

    # ── H.265 on-demand transcoder ─────────────────────────────────────────────
    max_active_transcoders: int = 10
    transcoder_vcodec: str = "libx264"      # "h264_nvenc" for NVIDIA, "h264_qsv" for Intel QSV
    transcoder_preset: str = "ultrafast"
    transcoder_tune: str = "zerolatency"
    transcoder_grace_period_seconds: int = 60

    # ── Recording policy ───────────────────────────────────────────────────────
    # True  = only MAIN/HD profile streams are recorded (default — saves ~50% storage)
    # False = use RECORD_NORMAL / RECORD_MOBILE to fine-tune
    record_hd_only: bool = True
    record_normal: bool = False             # Record SUB/NORMAL streams
    record_mobile: bool = False             # Record MOBILE streams

    # ── Live streaming policy ──────────────────────────────────────────────────
    # Profile used for live streaming when adaptive mode is disabled.
    # Options: "HD" | "NORMAL" | "MOBILE"
    live_stream_profile: str = "NORMAL"

    # Enable adaptive live profile switching based on the UI layout grid size.
    enable_adaptive_profile: bool = True

    # 1x1 single-camera view — use HD for the best quality in focus mode
    focus_view_profile: str = "HD"

    # 2x2, 3x3 grid view — use NORMAL to save bandwidth with many cameras
    grid_view_profile: str = "NORMAL"

    # Mobile / low-bandwidth client view
    mobile_view_profile: str = "MOBILE"

    # ── Playback policy ────────────────────────────────────────────────────────
    # Profile to use when serving recorded video for playback.
    # Options: "HD" | "NORMAL" | "MOBILE"
    playback_profile: str = "HD"

    # Allow falling back to NORMAL recordings when HD recordings are unavailable.
    playback_allow_normal_fallback: bool = True
    playback_allow_mobile_fallback: bool = False
    playback_speeds: list[float] = [0.5, 1.0, 2.0, 4.0, 8.0]

    # ── WebRTC policy ──────────────────────────────────────────────────────────
    max_webrtc_sessions_per_camera: int = 100
    enable_h265_transcoding: bool = True
    enable_hls_fallback: bool = True
    webrtc_connection_timeout_seconds: int = 10

    # ── Camera health watchdog ─────────────────────────────────────────────────
    camera_ping_interval_seconds: int = 120
    camera_ping_timeout_seconds: int = 5
    camera_ping_max_concurrent: int = 10
    enable_rtsp_health_check: bool = True
    offline_cooldown_seconds: int = 120          # 2 min cooldown before retrying offline cameras
    startup_stagger_batch_size: int = 10         # activate streams in batches of N during startup

    # ── Edge push policy ───────────────────────────────────────────────────────
    edge_push_heartbeat_timeout_seconds: int = 120
    edge_push_check_interval_seconds: int = 30
    enable_edge_push: bool = True
    edge_push_priority: bool = True

    # ── Storage retention policy ───────────────────────────────────────────────
    enable_retention: bool = True
    default_retention_days: int = 30
    enable_low_disk_eviction: bool = True
    low_disk_space_threshold_gb: float = 5.0
    target_free_space_gb: float = 10.0

    # ── Recording policy constants ─────────────────────────────────────────────
    enable_recording: bool = True
    enable_self_healing_recordings: bool = False

    # ── Playback timeline policy constants ─────────────────────────────────────
    timeline_cache_seconds: int = 60
    timeline_merge_threshold_seconds: int = 5
    timeline_default_zoom: str = "24h"

    # ── MediaMTX safety constants ──────────────────────────────────────────────
    mediamtx_patch_only: bool = True
    allow_delete_add_reconfiguration: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# ── Profile map ──────────────────────────────────────────────────────────────
PROFILE_MAP = {
    "HD": "MAIN",
    "NORMAL": "SUB",
    "MOBILE": "MOBILE",
}

# ── Dynamic policy helpers ───────────────────────────────────────────────────
def resolve_live_profile(layout_size: int = 0) -> str:
    from .policy_loader import PolicyLoader
    enable_adaptive = PolicyLoader.get("stream_policy.yaml", "enable_adaptive_profile", settings.enable_adaptive_profile)
    focus_view = PolicyLoader.get("stream_policy.yaml", "focus_view_profile", settings.focus_view_profile)
    grid_view = PolicyLoader.get("stream_policy.yaml", "grid_view_profile", settings.grid_view_profile)
    live_profile = PolicyLoader.get("stream_policy.yaml", "live_stream_profile", settings.live_stream_profile)
    
    if enable_adaptive and layout_size > 0:
        profile_name = focus_view if layout_size == 1 else grid_view
    else:
        profile_name = live_profile
    return PROFILE_MAP.get(profile_name.upper(), "SUB")

def resolve_playback_profile() -> str:
    from .policy_loader import PolicyLoader
    playback_prof = PolicyLoader.get("playback_policy.yaml", "playback_profile", settings.playback_profile)
    return PROFILE_MAP.get(playback_prof.upper(), "MAIN")

def get_recording_profiles() -> list:
    from .policy_loader import PolicyLoader
    hd_only = PolicyLoader.get("recording_policy.yaml", "record_hd_only", settings.record_hd_only)
    rec_normal = PolicyLoader.get("recording_policy.yaml", "record_normal", settings.record_normal)
    rec_mobile = PolicyLoader.get("recording_policy.yaml", "record_mobile", settings.record_mobile)
    
    if hd_only:
        return ["MAIN"]
    profiles = ["MAIN"]
    if rec_normal:
        profiles.append("SUB")
    if rec_mobile:
        profiles.append("MOBILE")
    return profiles

def should_record_profile(profile_type_value: str) -> bool:
    return profile_type_value in get_recording_profiles()

# ── Dynamic module attribute resolver ─────────────────────────────────────────
# This maps requests for config settings dynamically to the active policy files.
_DYNAMIC_POLICY_MAP = {
    "STRICT_CAMERA_VALIDATION": ("security_policy.yaml", "strict_camera_validation", settings.strict_camera_validation),
    "ALLOW_UNKNOWN_EDGE_DEVICES": ("security_policy.yaml", "allow_unknown_edge_devices", settings.allow_unknown_edge_devices),
    "RECORD_HD_ONLY": ("recording_policy.yaml", "record_hd_only", settings.record_hd_only),
    "RECORD_NORMAL": ("recording_policy.yaml", "record_normal", settings.record_normal),
    "RECORD_MOBILE": ("recording_policy.yaml", "record_mobile", settings.record_mobile),
    "LIVE_STREAM_PROFILE": ("stream_policy.yaml", "live_stream_profile", settings.live_stream_profile),
    "ENABLE_ADAPTIVE_PROFILE": ("stream_policy.yaml", "enable_adaptive_profile", settings.enable_adaptive_profile),
    "FOCUS_VIEW_PROFILE": ("stream_policy.yaml", "focus_view_profile", settings.focus_view_profile),
    "GRID_VIEW_PROFILE": ("stream_policy.yaml", "grid_view_profile", settings.grid_view_profile),
    "MOBILE_VIEW_PROFILE": ("stream_policy.yaml", "mobile_view_profile", settings.mobile_view_profile),
    "PLAYBACK_PROFILE": ("playback_policy.yaml", "playback_profile", settings.playback_profile),
    "PLAYBACK_ALLOW_NORMAL_FALLBACK": ("playback_policy.yaml", "playback_allow_normal_fallback", settings.playback_allow_normal_fallback),
    "PLAYBACK_ALLOW_MOBILE_FALLBACK": ("playback_policy.yaml", "playback_allow_mobile_fallback", settings.playback_allow_mobile_fallback),
    "PLAYBACK_SPEEDS": ("playback_policy.yaml", "playback_speeds", settings.playback_speeds),
    "ENABLE_WEBRTC": ("stream_policy.yaml", "enable_webrtc", settings.enable_webrtc),
    "ENABLE_HLS_FALLBACK": ("stream_policy.yaml", "enable_hls_fallback", settings.enable_hls_fallback),
    "WEBRTC_CONNECTION_TIMEOUT_SECONDS": ("session_policy.yaml", "webrtc_connection_timeout_seconds", settings.webrtc_connection_timeout_seconds),
    "MAX_WEBRTC_SESSIONS_PER_CAMERA": ("session_policy.yaml", "max_webrtc_sessions_per_camera", settings.max_webrtc_sessions_per_camera),
    "TRANSCODER_VCODEC": ("transcoder_policy.yaml", "transcoder_vcodec", settings.transcoder_vcodec),
    "TRANSCODER_PRESET": ("transcoder_policy.yaml", "transcoder_preset", settings.transcoder_preset),
    "TRANSCODER_TUNE": ("transcoder_policy.yaml", "transcoder_tune", settings.transcoder_tune),
    "TRANSCODER_IDLE_TIMEOUT_SECONDS": ("session_policy.yaml", "transcoder_grace_period_seconds", settings.transcoder_grace_period_seconds),
    "MAX_ACTIVE_TRANSCODERS": ("transcoder_policy.yaml", "max_active_transcoders", settings.max_active_transcoders),
    "SEGMENT_DURATION_SECONDS": ("recording_policy.yaml", "segment_time_seconds", settings.segment_time_seconds),
    "ENABLE_RECORDING": ("recording_policy.yaml", "enable_recording", settings.enable_recording),
    "ENABLE_RTSP_HEALTH_CHECK": ("watchdog_policy.yaml", "enable_rtsp_health_check", settings.enable_rtsp_health_check),
    "CAMERA_PING_INTERVAL_SECONDS": ("watchdog_policy.yaml", "camera_ping_interval_seconds", settings.camera_ping_interval_seconds),
    "CAMERA_PING_TIMEOUT_SECONDS": ("watchdog_policy.yaml", "camera_ping_timeout_seconds", settings.camera_ping_timeout_seconds),
    "ENABLE_RETENTION": ("storage_policy.yaml", "enable_retention", settings.enable_retention),
    "DEFAULT_RETENTION_DAYS": ("storage_policy.yaml", "default_retention_days", settings.default_retention_days),
}

def __getattr__(name: str) -> Any:
    if name in _DYNAMIC_POLICY_MAP:
        from .policy_loader import PolicyLoader
        policy_file, key, default_val = _DYNAMIC_POLICY_MAP[name]
        return PolicyLoader.get(policy_file, key, default_val)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# ── UPPERCASE Compatibility Aliases for policy values ──────────────────────────
# Non-policy static values are left here; policy values fall through to __getattr__.
RECORDING_RECOVERY_INTERVAL_HOURS = settings.recovery_interval_seconds / 3600.0
TIMELINE_CACHE_SECONDS = settings.timeline_cache_seconds
TIMELINE_MERGE_THRESHOLD_SECONDS = settings.timeline_merge_threshold_seconds
TIMELINE_DEFAULT_ZOOM = settings.timeline_default_zoom
ENABLE_EDGE_PUSH = settings.enable_edge_push
EDGE_PUSH_PRIORITY = settings.edge_push_priority
EDGE_PUSH_HEARTBEAT_TIMEOUT_SECONDS = settings.edge_push_heartbeat_timeout_seconds
EDGE_PUSH_CHECK_INTERVAL_SECONDS = settings.edge_push_check_interval_seconds
CAMERA_PING_MAX_CONCURRENT = settings.camera_ping_max_concurrent
UPSTREAM_SYNC_INTERVAL_MINUTES = settings.upstream_sync_interval_minutes
INDEXER_INTERVAL_SECONDS = settings.indexer_interval_seconds
MEDIAMTX_PATCH_ONLY = settings.mediamtx_patch_only
ALLOW_DELETE_ADD_RECONFIGURATION = settings.allow_delete_add_reconfiguration
ENABLE_H265_TRANSCODING = True

