import time
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

class BoundingBox(BaseModel):
    xmin: float
    ymin: float
    xmax: float
    ymax: float

class Point2D(BaseModel):
    x: float
    y: float

class DetectionResult(BaseModel):
    id: str
    label: str
    confidence: float
    bbox: BoundingBox
    track_id: Optional[int] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)

class IntrusionZone(BaseModel):
    zone_id: str
    camera_id: str
    name: str
    polygon: List[Point2D]  # Normalized coordinates [0.0 - 1.0]
    enabled: bool = True

class AIEvent(BaseModel):
    event_id: str
    camera_id: str
    camera_name: str
    event_type: str  # "person_detected", "face_detected", "vehicle_detected", "intrusion_breach"
    timestamp: float = Field(default_factory=time.time)
    formatted_time: str
    confidence: float
    label: str
    bbox: BoundingBox
    zone_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    snapshot_url: Optional[str] = None

class CameraSubscription(BaseModel):
    camera_id: str
    name: str
    stream_url: str
    active_models: List[str] = Field(default=["person", "face", "vehicle", "intrusion"])
    enabled: bool = True
    sampling_fps: int = 5

class ModelConfig(BaseModel):
    model_name: str
    enabled: bool = True
    confidence_threshold: float = 0.5
    min_size: int = 30
