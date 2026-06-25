import uuid
from datetime import datetime
from pydantic import BaseModel, computed_field
from typing import Optional, List

class CameraStreamOut(BaseModel):
    id: uuid.UUID
    camera_id: uuid.UUID
    stream_id: str
    profile_type: str
    resolution: str
    fps: int
    codec: str
    bitrate: Optional[int] = None
    stream_url: str
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class CameraOut(BaseModel):
    id: uuid.UUID
    source_camera_id: int
    name: str
    active: bool
    streams: List[CameraStreamOut] = []
    created_at: datetime
    updated_at: datetime

    # ----------------------------------------------------
    # Computed fields to maintain backward compatibility
    # with the frontend React interface
    # ----------------------------------------------------
    @computed_field
    @property
    def stream_id(self) -> str:
        return self.streams[0].stream_id if self.streams else f"cam_{self.source_camera_id}_main"

    @computed_field
    @property
    def stream_type(self) -> str:
        return self.streams[0].profile_type if self.streams else "MAIN"

    @computed_field
    @property
    def rtsp_url(self) -> Optional[str]:
        return self.streams[0].stream_url if self.streams else None

    @computed_field
    @property
    def fps(self) -> Optional[int]:
        return self.streams[0].fps if self.streams else None

    @computed_field
    @property
    def width(self) -> Optional[int]:
        if self.streams:
            parts = self.streams[0].resolution.split("x")
            return int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 1920
        return 1920

    @computed_field
    @property
    def height(self) -> Optional[int]:
        if self.streams:
            parts = self.streams[0].resolution.split("x")
            return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1080
        return 1080

    @computed_field
    @property
    def archive_type(self) -> Optional[str]:
        return self.streams[0].codec if self.streams else "H264"

    @computed_field
    @property
    def transcode(self) -> bool:
        return False

    @computed_field
    @property
    def bitrate(self) -> Optional[int]:
        return self.streams[0].bitrate * 1000 if self.streams and self.streams[0].bitrate else None

    @computed_field
    @property
    def camera_type(self) -> str:
        return "PROXY"

    @computed_field
    @property
    def decode_type(self) -> str:
        return "NONE"

    @computed_field
    @property
    def server_http_port(self) -> int:
        return 7888

    @computed_field
    @property
    def raw_json(self) -> str:
        import json
        return json.dumps({"archiveDays": 3})

    class Config:
        from_attributes = True

class RecordingSegmentOut(BaseModel):
    stream_id: str
    file_path: str
    start_ts: float
    end_ts: float

    class Config:
        from_attributes = True

class SyncResponse(BaseModel):
    total: int
    created_or_updated: int
    source: str

class CameraCreate(BaseModel):
    source_camera_id: int
    name: str
    active: bool = True
    make: Optional[str] = None
    stream_id: str
    profile_type: str = "MAIN"
    resolution: str = "1920x1080"
    fps: int = 30
    codec: str = "H264"
    bitrate: Optional[int] = None
    stream_url: str
    stream_mode: str = "AUTO"
    always_on: bool = False

class CameraUpdate(BaseModel):
    name: str
    active: bool
    make: Optional[str] = None
    resolution: str
    fps: int
    codec: str
    bitrate: Optional[int] = None
    stream_url: str
    always_on: bool

class SettingsUpdate(BaseModel):
    use_upstream_cameras: bool

