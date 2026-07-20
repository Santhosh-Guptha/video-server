import json
import os
from typing import List
from pydantic_settings import BaseSettings

# Load default config from default_settings.json outside the code
CONFIG_DIR = os.path.join(os.path.dirname(__file__), "configs")
DEFAULTS_FILE = os.path.join(CONFIG_DIR, "default_settings.json")
try:
    with open(DEFAULTS_FILE, "r") as f:
        defaults = json.load(f)
except Exception as e:
    print(f"[config] Failed to load defaults file: {e}")
    defaults = {}

class Settings(BaseSettings):
    app_name: str = defaults.get("app_name", "camera-video-platform")
    enable_webrtc: bool = defaults.get("enable_webrtc", True)
    database_url: str = defaults.get("database_url", "postgresql+asyncpg://vms_admin:vms_secure_password@localhost:5432/vms_db")
    redis_url: str = defaults.get("redis_url", "redis://127.0.0.1:6379/0")
    mediamtx_api_url: str = defaults.get("mediamtx_api_url", "http://127.0.0.1:9997")
    mediamtx_webrtc_url: str = defaults.get("mediamtx_webrtc_url", "http://127.0.0.1:8889")
    stun_servers: List[str] = defaults.get("stun_servers", ["stun:stun.l.google.com:19302"])
    turn_server_url: str = defaults.get("turn_server_url", "turn:localhost:3478")
    turn_server_username: str = defaults.get("turn_server_username", "vms_user")
    turn_server_credential: str = defaults.get("turn_server_credential", "vms_turn_password")

    upstream_camera_api_url: str = defaults.get("upstream_camera_api_url", "")
    upstream_timeout_seconds: float = defaults.get("upstream_timeout_seconds", 10.0)
    upstream_sync_interval_minutes: int = defaults.get("upstream_sync_interval_minutes", 5)
    ffmpeg_path: str = defaults.get("ffmpeg_path", "ffmpeg")
    recording_dir: str = defaults.get("recording_dir", "./data/recordings")
    hls_dir: str = defaults.get("hls_dir", "./data/hls")
    segment_time_seconds: int = defaults.get("segment_time_seconds", 60)
    max_subscribers_per_stream: int = defaults.get("max_subscribers_per_stream", 200)
    ui_poll_seconds: int = defaults.get("ui_poll_seconds", 5)
    scheduler_interval_seconds: int = defaults.get("scheduler_interval_seconds", 10)
    recovery_interval_seconds: int = defaults.get("recovery_interval_seconds", 300)
    cleanup_interval_seconds: int = defaults.get("cleanup_interval_seconds", 600)
    indexer_interval_seconds: int = defaults.get("indexer_interval_seconds", 600)

    recovery_rtsp_template: str = defaults.get("recovery_rtsp_template", "{rtsp_url}?starttime={start_iso}&endtime={end_iso}")

    edge_receiver_host: str = defaults.get("edge_receiver_host", "0.0.0.0")
    edge_receiver_port: int = defaults.get("edge_receiver_port", 9999)
    edge_receiver_enabled: bool = defaults.get("edge_receiver_enabled", True)
    allow_unknown_edge_devices: bool = defaults.get("allow_unknown_edge_devices", False)
    strict_camera_validation: bool = defaults.get("strict_camera_validation", True)

    max_active_transcoders: int = defaults.get("max_active_transcoders", 10)
    transcoder_vcodec: str = defaults.get("transcoder_vcodec", "libx264")
    transcoder_preset: str = defaults.get("transcoder_preset", "ultrafast")
    transcoder_tune: str = defaults.get("transcoder_tune", "zerolatency")
    transcoder_grace_period_seconds: int = defaults.get("transcoder_grace_period_seconds", 60)

    record_hd_only: bool = defaults.get("record_hd_only", True)
    record_normal: bool = defaults.get("record_normal", False)
    record_mobile: bool = defaults.get("record_mobile", False)

    live_stream_profile: str = defaults.get("live_stream_profile", "NORMAL")
    enable_adaptive_profile: bool = defaults.get("enable_adaptive_profile", True)
    focus_view_profile: str = defaults.get("focus_view_profile", "HD")
    grid_view_profile: str = defaults.get("grid_view_profile", "NORMAL")
    mobile_view_profile: str = defaults.get("mobile_view_profile", "MOBILE")

    playback_profile: str = defaults.get("playback_profile", "HD")
    playback_allow_normal_fallback: bool = defaults.get("playback_allow_normal_fallback", True)
    playback_allow_mobile_fallback: bool = defaults.get("playback_allow_mobile_fallback", False)
    playback_speeds: List[float] = defaults.get("playback_speeds", [0.5, 1.0, 2.0, 4.0, 8.0])

    max_webrtc_sessions_per_camera: int = defaults.get("max_webrtc_sessions_per_camera", 100)
    enable_h265_transcoding: bool = defaults.get("enable_h265_transcoding", True)
    enable_hls_fallback: bool = defaults.get("enable_hls_fallback", True)
    webrtc_connection_timeout_seconds: int = defaults.get("webrtc_connection_timeout_seconds", 10)

    camera_ping_interval_seconds: int = defaults.get("camera_ping_interval_seconds", 120)
    camera_ping_timeout_seconds: int = defaults.get("camera_ping_timeout_seconds", 5)
    camera_ping_max_concurrent: int = defaults.get("camera_ping_max_concurrent", 10)
    enable_rtsp_health_check: bool = defaults.get("enable_rtsp_health_check", True)

    edge_push_heartbeat_timeout_seconds: int = defaults.get("edge_push_heartbeat_timeout_seconds", 120)
    edge_push_check_interval_seconds: int = defaults.get("edge_push_check_interval_seconds", 30)
    enable_edge_push: bool = defaults.get("enable_edge_push", True)
    preferred_profile: str = defaults.get("preferred_profile", "HD")
    record_fallback_to_normal: bool = defaults.get("record_fallback_to_normal", True)
    live_stream_fallback: bool = defaults.get("live_stream_fallback", True)
    edge_push_priority: bool = defaults.get("edge_push_priority", True)

    enable_retention: bool = defaults.get("enable_retention", True)
    default_retention_days: int = defaults.get("default_retention_days", 30)
    enable_low_disk_eviction: bool = defaults.get("enable_low_disk_eviction", True)
    low_disk_space_threshold_gb: float = defaults.get("low_disk_space_threshold_gb", 5.0)
    target_free_space_gb: float = defaults.get("target_free_space_gb", 10.0)

    enable_recording: bool = defaults.get("enable_recording", True)

    timeline_cache_seconds: int = defaults.get("timeline_cache_seconds", 60)
    timeline_merge_threshold_seconds: int = defaults.get("timeline_merge_threshold_seconds", 5)
    timeline_default_zoom: str = defaults.get("timeline_default_zoom", "24h")

    mediamtx_patch_only: bool = defaults.get("mediamtx_patch_only", True)
    allow_delete_add_reconfiguration: bool = defaults.get("allow_delete_add_reconfiguration", False)

    enable_device_config: bool = defaults.get("enable_device_config", False)
    enable_local_transcode: bool = defaults.get("enable_local_transcode", False)

    enable_sd_card_on_demand: bool = defaults.get("enable_sd_card_on_demand", True)
    sd_card_on_demand_retention_seconds: int = defaults.get("sd_card_on_demand_retention_seconds", 3600)

    class Config:
        env_file = ".env"
        extra = "ignore"

    def __init__(self, **values):
        super().__init__(**values)
        pref = self.preferred_profile.upper()
        
        # Respect user overrides explicitly set via .env or arguments
        explicit = getattr(self, "model_fields_set", getattr(self, "__fields_set__", set()))
        
        if pref in ("NORMAL", "SUB"):
            if "live_stream_profile" not in explicit:
                self.live_stream_profile = "NORMAL"
            if "playback_profile" not in explicit:
                self.playback_profile = "NORMAL"
            if "record_hd_only" not in explicit:
                self.record_hd_only = False
            if "record_normal" not in explicit:
                self.record_normal = True
        else:
            if "live_stream_profile" not in explicit:
                self.live_stream_profile = "HD"
            if "playback_profile" not in explicit:
                self.playback_profile = "HD"
            if "record_hd_only" not in explicit:
                self.record_hd_only = True
            if "record_normal" not in explicit:
                self.record_normal = False

settings = Settings()

# ── Profile map ──────────────────────────────────────────────────────────────
PROFILE_MAP = {
    "HD": "MAIN",
    "NORMAL": "SUB",
    "MOBILE": "MOBILE",
}

# ── Dynamic policy helpers ───────────────────────────────────────────────────
def resolve_live_profile(layout_size: int = 0) -> str:
    if settings.enable_adaptive_profile and layout_size > 0:
        profile_name = settings.focus_view_profile if layout_size == 1 else settings.grid_view_profile
    else:
        profile_name = settings.live_stream_profile
    return PROFILE_MAP.get(profile_name.upper(), "SUB")

def resolve_playback_profile() -> str:
    return PROFILE_MAP.get(settings.playback_profile.upper(), "MAIN")

def get_recording_profiles() -> list:
    if settings.record_hd_only:
        return ["MAIN"]
    profiles = ["MAIN"]
    if settings.record_normal:
        profiles.append("SUB")
    if settings.record_mobile:
        profiles.append("MOBILE")
    return profiles

def should_record_profile(profile_type_value: str) -> bool:
    return profile_type_value in get_recording_profiles()

# ── UPPERCASE Compatibility Aliases for policy values ──────────────────────────
STRICT_CAMERA_VALIDATION = settings.strict_camera_validation
ALLOW_UNKNOWN_EDGE_DEVICES = settings.allow_unknown_edge_devices
RECORD_HD_ONLY = settings.record_hd_only
RECORD_NORMAL = settings.record_normal
RECORD_MOBILE = settings.record_mobile
LIVE_STREAM_PROFILE = settings.live_stream_profile
ENABLE_ADAPTIVE_PROFILE = settings.enable_adaptive_profile
FOCUS_VIEW_PROFILE = settings.focus_view_profile
GRID_VIEW_PROFILE = settings.grid_view_profile
MOBILE_VIEW_PROFILE = settings.mobile_view_profile
PLAYBACK_PROFILE = settings.playback_profile
PLAYBACK_ALLOW_NORMAL_FALLBACK = settings.playback_allow_normal_fallback
PLAYBACK_ALLOW_MOBILE_FALLBACK = settings.playback_allow_mobile_fallback
PLAYBACK_SPEEDS = settings.playback_speeds
ENABLE_WEBRTC = settings.enable_webrtc
ENABLE_HLS_FALLBACK = settings.enable_hls_fallback
WEBRTC_CONNECTION_TIMEOUT_SECONDS = settings.webrtc_connection_timeout_seconds
MAX_WEBRTC_SESSIONS_PER_CAMERA = settings.max_webrtc_sessions_per_camera
ENABLE_H265_TRANSCODING = settings.enable_h265_transcoding
TRANSCODER_VCODEC = settings.transcoder_vcodec
TRANSCODER_PRESET = settings.transcoder_preset
TRANSCODER_TUNE = settings.transcoder_tune
TRANSCODER_IDLE_TIMEOUT_SECONDS = settings.transcoder_grace_period_seconds
MAX_ACTIVE_TRANSCODERS = settings.max_active_transcoders
SEGMENT_DURATION_SECONDS = settings.segment_time_seconds
ENABLE_RECORDING = settings.enable_recording
RECORDING_RECOVERY_INTERVAL_HOURS = settings.recovery_interval_seconds / 3600.0
TIMELINE_CACHE_SECONDS = settings.timeline_cache_seconds
TIMELINE_MERGE_THRESHOLD_SECONDS = settings.timeline_merge_threshold_seconds
TIMELINE_DEFAULT_ZOOM = settings.timeline_default_zoom
ENABLE_EDGE_PUSH = settings.enable_edge_push
PREFERRED_PROFILE = settings.preferred_profile
RECORD_FALLBACK_TO_NORMAL = settings.record_fallback_to_normal
LIVE_STREAM_FALLBACK = settings.live_stream_fallback
EDGE_PUSH_PRIORITY = settings.edge_push_priority
EDGE_PUSH_HEARTBEAT_TIMEOUT_SECONDS = settings.edge_push_heartbeat_timeout_seconds
EDGE_PUSH_CHECK_INTERVAL_SECONDS = settings.edge_push_check_interval_seconds
ENABLE_RTSP_HEALTH_CHECK = settings.enable_rtsp_health_check
CAMERA_PING_INTERVAL_SECONDS = settings.camera_ping_interval_seconds
CAMERA_PING_TIMEOUT_SECONDS = settings.camera_ping_timeout_seconds
CAMERA_PING_MAX_CONCURRENT = settings.camera_ping_max_concurrent
UPSTREAM_SYNC_INTERVAL_MINUTES = settings.upstream_sync_interval_minutes
ENABLE_RETENTION = settings.enable_retention
DEFAULT_RETENTION_DAYS = settings.default_retention_days
INDEXER_INTERVAL_SECONDS = settings.indexer_interval_seconds
MEDIAMTX_PATCH_ONLY = settings.mediamtx_patch_only
ALLOW_DELETE_ADD_RECONFIGURATION = settings.allow_delete_add_reconfiguration
ENABLE_DEVICE_CONFIG = settings.enable_device_config
ENABLE_LOCAL_TRANSCODE = settings.enable_local_transcode
