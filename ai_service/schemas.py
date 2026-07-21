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
    label: str = "Person"
    class_name: str = "person"
    confidence: float = 0.85
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
    timestamp: float
    formatted_time: str
    event_type: str  # "person_detected", "face_detected", "vehicle_detected", "intrusion_breach"
    label: str
    confidence: float
    bbox: Optional[BoundingBox] = None
    snapshot_url: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

class CameraSubscription(BaseModel):
    camera_id: str
    stream_url: str
    active_models: List[str] = Field(default=["person", "face", "vehicle", "intrusion"])
