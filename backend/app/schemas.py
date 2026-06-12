from pydantic import BaseModel
from typing import Optional, Any

class CameraOut(BaseModel):
    pk: int
    source_camera_id: int
    stream_id: str
    name: str
    stream_type: str
    rtsp_url: Optional[str] = None
    fps: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    archive_type: Optional[str] = None
    active: bool
    transcode: bool
    bitrate: Optional[int] = None
    camera_type: Optional[str] = None
    decode_type: Optional[str] = None
    server_http_port: Optional[int] = None
    raw_json: str

    class Config:
        from_attributes = True

class RecordingSegmentOut(BaseModel):
    stream_id: str
    camera_name: str
    file_path: str
    start_ts: float
    end_ts: float

class SyncResponse(BaseModel):
    total: int
    created_or_updated: int
    source: str
