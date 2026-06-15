from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "camera-video-platform"
    enable_webrtc: bool = True
    # Switch default to postgresql+asyncpg for production, fallback to SQLite for local development without container
    database_url: str = "postgresql+asyncpg://vms_admin:vms_secure_password@localhost:5432/vms_db"
    redis_url: str = "redis://localhost:6379/0"
    mediamtx_api_url: str = "http://localhost:9997"
    mediamtx_webrtc_url: str = "http://localhost:8889"
    stun_servers: list[str] = ["stun:stun.l.google.com:19302"]
    turn_server_url: str = "turn:localhost:3478"
    turn_server_username: str = "vms_user"
    turn_server_credential: str = "vms_turn_password"
    
    upstream_camera_api_url: str = "https://iportal.iviscloud.net/api/cameras/camera-videoserver"
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

    class Config:
        env_file = ".env"

settings = Settings()

