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
    ffmpeg_path: str = "ffmpeg"
    recording_dir: str = "./data/recordings"
    hls_dir: str = "./data/hls"
    segment_time_seconds: int = 60
    max_subscribers_per_stream: int = 200
    ui_poll_seconds: int = 5
    scheduler_interval_seconds: int = 10
    recovery_interval_seconds: int = 300
    cleanup_interval_seconds: int = 600
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

    # ── WebRTC policy ──────────────────────────────────────────────────────────
    max_webrtc_sessions_per_camera: int = 100
    enable_h265_transcoding: bool = True

    # ── Camera health watchdog ─────────────────────────────────────────────────
    camera_ping_interval_seconds: int = 120
    camera_ping_timeout_seconds: int = 5

    # ── Edge push policy ───────────────────────────────────────────────────────
    edge_push_heartbeat_timeout_seconds: int = 120
    edge_push_check_interval_seconds: int = 30

    # ── Storage retention policy ───────────────────────────────────────────────
    enable_retention: bool = True
    default_retention_days: int = 30

    class Config:
        env_file = ".env"

settings = Settings()
