from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "camera-video-platform"
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    upstream_camera_api_url: str = "https://uat1.iviscloud.net/api/cameras/camera-videoserver"
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
