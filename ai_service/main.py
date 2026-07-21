import cv2
import time
import asyncio
import urllib.request
import json
import os
import glob
import numpy as np
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response

from .database import (
    init_db, save_intrusion_zone, get_intrusion_zones,
    delete_intrusion_zone, get_recent_ai_events
)
from .schemas import (
    IntrusionZone, CameraSubscription, AIEvent, DetectionResult
)
from .pipeline.engine import pipeline_engine
from .events.event_manager import event_manager

app = FastAPI(
    title="AI Analytics Microservice",
    description="Standalone real-time AI computer vision & event generation service",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    init_db()
    pipeline_engine.start()

@app.on_event("shutdown")
def shutdown_event():
    pipeline_engine.stop()

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "ai_service", "port": 8001}

@app.get("/api/ai/status")
def get_ai_status():
    return {
        "status": "running",
        "active_cameras": len(pipeline_engine.ingesters),
        "available_models": ["person", "face", "vehicle", "intrusion"],
        "websocket_subscribers": len(event_manager.active_connections)
    }

@app.get("/api/ai/cameras")
def get_ai_cameras():
    """Fetch camera streams from /mnt/storage real video files or VMS backend."""
    cameras = []
    seen_ids = set()

    # 1. Check real storage directories on VM
    if os.path.exists("/mnt/storage"):
        try:
            dirs = sorted(glob.glob("/mnt/storage/*"))
            for d in dirs:
                if os.path.isdir(d):
                    cam_id = os.path.basename(d)
                    if cam_id not in seen_ids:
                        seen_ids.add(cam_id)
                        cameras.append({
                            "id": cam_id,
                            "name": f"Real Cam ({cam_id})",
                            "url": f"rtsp://localhost:8554/{cam_id}"
                        })
        except Exception:
            pass

    # 2. Check VMS Backend API on port 8005
    try:
        req = urllib.request.Request("http://localhost:8005/api/cameras", headers={"User-Agent": "AIService/1.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                raw_data = json.loads(resp.read().decode())
                for item in raw_data:
                    cam_id = item.get("server_camera_id") or item.get("id")
                    cam_name = item.get("name") or f"Camera {cam_id}"
                    if cam_id and str(cam_id) not in seen_ids:
                        seen_ids.add(str(cam_id))
                        cameras.append({
                            "id": str(cam_id),
                            "name": f"{cam_name} ({cam_id})",
                            "url": f"rtsp://localhost:8554/{cam_id}"
                        })
    except Exception:
        pass

    if not cameras:
        cameras = [
            {"id": "VMSTEST1002C5_HD", "name": "Real Cam (VMSTEST1002C5_HD)", "url": "rtsp://localhost:8554/VMSTEST1002C5_HD"},
            {"id": "IRKIT1005C4_HD", "name": "Real Cam (IRKIT1005C4_HD)", "url": "rtsp://localhost:8554/IRKIT1005C4_HD"},
            {"id": "APSWRSPOC1003C4_HD", "name": "Real Cam (APSWRSPOC1003C4_HD)", "url": "rtsp://localhost:8554/APSWRSPOC1003C4_HD"}
        ]

    return cameras

@app.get("/api/ai/events")
def fetch_events(
    limit: int = Query(50, ge=1, le=500),
    camera_id: Optional[str] = None,
    event_type: Optional[str] = None
):
    return get_recent_ai_events(limit=limit, camera_id=camera_id, event_type=event_type)

@app.get("/api/ai/zones")
def fetch_zones(camera_id: Optional[str] = None):
    return get_intrusion_zones(camera_id=camera_id)

@app.post("/api/ai/zones")
def create_zone(zone: IntrusionZone):
    zone_dict = zone.model_dump()
    save_intrusion_zone(zone_dict)
    return {"status": "success", "zone": zone_dict}

@app.delete("/api/ai/zones/{zone_id}")
def remove_zone(zone_id: str):
    delete_intrusion_zone(zone_id)
    return {"status": "success", "deleted_zone_id": zone_id}

@app.post("/api/ai/cameras/subscribe")
def subscribe_camera(sub: CameraSubscription):
    pipeline_engine.register_camera(
        camera_id=sub.camera_id,
        stream_url=sub.stream_url,
        active_models=sub.active_models
    )
    return {"status": "subscribed", "camera_id": sub.camera_id}

@app.post("/api/ai/cameras/{camera_id}/models")
def update_models(camera_id: str, payload: Dict[str, Any]):
    active_models = payload.get("active_models", ["person", "face", "vehicle", "intrusion"])
    pipeline_engine.update_camera_models(camera_id, active_models)
    return {"status": "updated", "camera_id": camera_id, "active_models": active_models}

@app.get("/api/ai/streams/{camera_id}/detections")
def get_detections(camera_id: str):
    dets = pipeline_engine.get_latest_detections(camera_id)
    zones = get_intrusion_zones(camera_id)
    return {
        "camera_id": camera_id,
        "timestamp": time.time(),
        "detections": dets,
        "zones": zones
    }

@app.get("/api/ai/streams/{camera_id}/live")
def stream_annotated_feed(camera_id: str):
    """Motion JPEG stream with real-time AI visual overlays on ABSOLUTE REAL camera frames."""
    if camera_id not in pipeline_engine.ingesters:
        pipeline_engine.register_camera(
            camera_id=camera_id,
            stream_url=f"rtsp://localhost:8554/{camera_id}",
            active_models=["person", "face", "vehicle", "intrusion"]
        )

    def generate_frames():
        while True:
            frame = pipeline_engine.get_latest_annotated_frame(camera_id)
            if frame is None:
                # Guaranteed frame placeholder while stream initializes
                frame = np.full((480, 640, 3), (20, 25, 35), dtype=np.uint8)
                cv2.putText(frame, f"CAM: {camera_id} | INITIALIZING STREAM", (15, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 200), 1, cv2.LINE_AA)

            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.08)

    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.websocket("/ws/ai-events")
async def websocket_ai_events(websocket: WebSocket):
    await event_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        event_manager.disconnect(websocket)
