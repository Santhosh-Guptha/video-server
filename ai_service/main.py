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
    description="On-demand AI computer vision & event generation service",
    version="2.0.0"
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
    # NOTE: No pipeline_engine.start() — AI runs on-demand only

@app.on_event("shutdown")
def shutdown_event():
    # Clean up all registered ingesters
    for cam_id in list(pipeline_engine.ingesters.keys()):
        pipeline_engine.unregister_camera(cam_id)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "ai_service", "version": "2.0.0", "port": 8001}

@app.get("/api/ai/status")
def get_ai_status():
    return {
        "status": "running",
        "mode": "on_demand",
        "active_cameras": len(pipeline_engine.ingesters),
        "active_camera_ids": pipeline_engine.get_active_camera_ids(),
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

# ─── On-Demand Camera AI Control ──────────────────────────────────

@app.post("/api/ai/cameras/{camera_id}/start")
def start_camera_ai(camera_id: str, payload: Optional[Dict[str, Any]] = None):
    """Register a camera for on-demand AI processing."""
    active_models = ["person"]
    if payload and "active_models" in payload:
        active_models = payload["active_models"]

    pipeline_engine.register_camera(
        camera_id=camera_id,
        stream_url=f"rtsp://localhost:8554/{camera_id}",
        active_models=active_models
    )
    return {
        "status": "started",
        "camera_id": camera_id,
        "active_models": active_models
    }

@app.post("/api/ai/cameras/{camera_id}/stop")
def stop_camera_ai(camera_id: str):
    """Unregister a camera, freeing all AI processing resources."""
    pipeline_engine.unregister_camera(camera_id)
    return {"status": "stopped", "camera_id": camera_id}

@app.post("/api/ai/cameras/subscribe")
def subscribe_camera(sub: CameraSubscription):
    """Legacy subscribe endpoint — registers for on-demand processing."""
    pipeline_engine.register_camera(
        camera_id=sub.camera_id,
        stream_url=sub.stream_url,
        active_models=sub.active_models
    )
    return {"status": "subscribed", "camera_id": sub.camera_id}

@app.post("/api/ai/cameras/{camera_id}/models")
def update_models(camera_id: str, payload: Dict[str, Any]):
    active_models = payload.get("active_models", ["person"])
    pipeline_engine.update_camera_models(camera_id, active_models)
    return {"status": "updated", "camera_id": camera_id, "active_models": active_models}

# ─── AI Configuration Endpoints ───────────────────────────────────

@app.get("/api/ai/config")
def get_ai_config():
    """Get global AI configuration (thresholds, inference size)."""
    return pipeline_engine.get_config()

@app.post("/api/ai/config")
def update_ai_config(payload: Dict[str, Any]):
    """Update global AI configuration."""
    pipeline_engine.update_config(payload)
    return {"status": "updated", "config": pipeline_engine.get_config()}

@app.post("/api/ai/cameras/{camera_id}/config")
def update_camera_config(camera_id: str, payload: Dict[str, Any]):
    """Update per-camera AI configuration (overrides global)."""
    pipeline_engine.update_config(payload, camera_id=camera_id)
    return {"status": "updated", "camera_id": camera_id, "config": pipeline_engine.get_config(camera_id)}

@app.get("/api/ai/cameras/{camera_id}/config")
def get_camera_config(camera_id: str):
    """Get effective AI configuration for a specific camera."""
    return pipeline_engine.get_config(camera_id)

# ─── On-Demand Detection Endpoints ────────────────────────────────

@app.get("/api/ai/streams/{camera_id}/detections")
def get_detections(camera_id: str):
    """On-demand: grabs a frame, runs AI models, returns detections immediately."""
    if not pipeline_engine.is_camera_active(camera_id):
        # Auto-register if not yet started (backward compat)
        pipeline_engine.register_camera(
            camera_id=camera_id,
            stream_url=f"rtsp://localhost:8554/{camera_id}",
            active_models=["person"]
        )

    result = pipeline_engine.process_camera_once(camera_id)
    return result

@app.get("/api/ai/streams/{camera_id}/frame")
def get_single_frame_jpeg(camera_id: str):
    """Returns a single JPEG image frame with real-time AI bounding box annotations."""
    if not pipeline_engine.is_camera_active(camera_id):
        pipeline_engine.register_camera(
            camera_id=camera_id,
            stream_url=f"rtsp://localhost:8554/{camera_id}",
            active_models=["person"]
        )

    # Process one frame on-demand
    pipeline_engine.process_camera_once(camera_id)

    frame = pipeline_engine.get_latest_annotated_frame(camera_id)
    if frame is None:
        frame = np.full((480, 640, 3), (20, 25, 35), dtype=np.uint8)
        cv2.putText(frame, f"CAM: {camera_id} | NO STREAM", (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 200), 1, cv2.LINE_AA)

    ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ret:
        raise HTTPException(status_code=500, detail="Failed to encode frame")

    return Response(
        content=buffer.tobytes(),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
    )

@app.get("/api/ai/streams/{camera_id}/live")
def stream_annotated_feed(camera_id: str):
    """Motion JPEG stream with on-demand AI visual overlays."""
    if not pipeline_engine.is_camera_active(camera_id):
        pipeline_engine.register_camera(
            camera_id=camera_id,
            stream_url=f"rtsp://localhost:8554/{camera_id}",
            active_models=["person"]
        )

    def generate_frames():
        while True:
            pipeline_engine.process_camera_once(camera_id)
            frame = pipeline_engine.get_latest_annotated_frame(camera_id)
            if frame is None:
                frame = np.full((480, 640, 3), (20, 25, 35), dtype=np.uint8)
                cv2.putText(frame, f"CAM: {camera_id} | WAITING FOR STREAM", (15, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 200), 1, cv2.LINE_AA)

            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ret:
                jpg_bytes = buffer.tobytes()
                header = (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n'
                    b'Content-Length: ' + str(len(jpg_bytes)).encode() + b'\r\n\r\n'
                )
                yield header + jpg_bytes + b'\r\n'
            time.sleep(0.04)

    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
    )

@app.websocket("/ws/ai-events")
async def websocket_ai_events(websocket: WebSocket):
    await event_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        event_manager.disconnect(websocket)
