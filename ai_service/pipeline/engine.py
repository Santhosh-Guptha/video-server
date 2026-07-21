import cv2
import numpy as np
import time
import threading
import asyncio
from typing import Dict, List, Any, Optional

from ..ingester.stream_ingester import StreamIngester
from ..models.person_detector import PersonDetector
from ..models.face_detector import FaceDetector
from ..models.vehicle_detector import VehicleDetector
from ..models.intrusion_detector import IntrusionDetector
from ..database import get_intrusion_zones
from ..events.event_manager import event_manager

class AIPipelineEngine:
    def __init__(self):
        self.person_detector = PersonDetector(confidence_threshold=0.45)
        self.face_detector = FaceDetector(confidence_threshold=0.5)
        self.vehicle_detector = VehicleDetector(confidence_threshold=0.5)
        self.intrusion_detector = IntrusionDetector()

        self.ingesters: Dict[str, StreamIngester] = {}
        self.active_models: Dict[str, List[str]] = {}
        self.annotated_frames: Dict[str, np.ndarray] = {}
        self.latest_detections: Dict[str, List[Dict[str, Any]]] = {}
        self.lock = threading.Lock()
        self.is_running = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        if not self.is_running:
            self.is_running = True
            self.thread = threading.Thread(target=self._run_loop, daemon=True)
            self.thread.start()

    def stop(self):
        self.is_running = False
        for ingester in self.ingesters.values():
            ingester.stop()

    def register_camera(self, camera_id: str, stream_url: str, active_models: List[str]):
        with self.lock:
            if camera_id in self.ingesters:
                self.ingesters[camera_id].stop()

            ingester = StreamIngester(stream_url=stream_url, camera_id=camera_id)
            ingester.start()
            self.ingesters[camera_id] = ingester
            self.active_models[camera_id] = active_models

    def update_camera_models(self, camera_id: str, active_models: List[str]):
        with self.lock:
            self.active_models[camera_id] = active_models

    def get_latest_annotated_frame(self, camera_id: str) -> Optional[np.ndarray]:
        with self.lock:
            return self.annotated_frames.get(camera_id)

    def get_latest_detections(self, camera_id: str) -> List[Dict[str, Any]]:
        with self.lock:
            return self.latest_detections.get(camera_id, [])

    def _run_loop(self):
        last_event_times: Dict[str, float] = {}

        while self.is_running:
            camera_ids = list(self.ingesters.keys())
            if not camera_ids:
                # Add default synthetic camera if none registered
                self.register_camera(
                    camera_id="cam-01",
                    stream_url="rtsp://localhost:8554/live/cam-01",
                    active_models=["person", "face", "vehicle", "intrusion"]
                )
                time.sleep(0.1)
                continue

            for camera_id in camera_ids:
                ingester = self.ingesters.get(camera_id)
                if not ingester:
                    continue

                frame, is_real = ingester.get_latest_frame()
                if frame is None:
                    continue

                active_mods = self.active_models.get(camera_id, ["person", "face", "vehicle", "intrusion"])
                detections = []

                # Execute AI Models
                if "person" in active_mods:
                    p_dets = self.person_detector.detect(frame, camera_id)
                    detections.extend(p_dets)

                if "face" in active_mods:
                    f_dets = self.face_detector.detect(frame, camera_id)
                    detections.extend(f_dets)

                if "vehicle" in active_mods:
                    v_dets = self.vehicle_detector.detect(frame, camera_id)
                    detections.extend(v_dets)

                # Fetch active intrusion zones for camera
                zones = get_intrusion_zones(camera_id)
                breaches = []
                if "intrusion" in active_mods and zones:
                    breaches = self.intrusion_detector.check_breaches(detections, zones)

                # Draw Visual AI Annotations on Frame Buffer
                annotated = frame.copy()
                h, w = annotated.shape[:2]

                # Draw intrusion zone polygons
                for z in zones:
                    if z["enabled"] and z["polygon"]:
                        pts = np.array([[int(pt["x"] * w), int(pt["y"] * h)] for pt in z["polygon"]], np.int32)
                        cv2.polylines(annotated, [pts], isClosed=True, color=(0, 165, 255), thickness=2)
                        cv2.putText(annotated, f"Zone: {z['name']}", (pts[0][0], max(20, pts[0][1] - 10)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1, cv2.LINE_AA)

                det_dicts = []
                now = time.time()

                for det in detections:
                    det_dict = det.model_dump()
                    det_dicts.append(det_dict)

                    # Draw Bounding Box & Label
                    xmin, ymin = int(det.bbox.xmin * w), int(det.bbox.ymin * h)
                    xmax, ymax = int(det.bbox.xmax * w), int(det.bbox.ymax * h)

                    color = (0, 255, 0) if det.label == "Person" else (255, 200, 0) if det.label == "Face" else (255, 100, 0)
                    cv2.rectangle(annotated, (xmin, ymin), (xmax, ymax), color, 2)

                    label_str = f"{det.label} {int(det.confidence * 100)}%"
                    cv2.putText(annotated, label_str, (xmin, max(15, ymin - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

                    # Rate limit AI Event Generation (1 event per 3 seconds per label per camera)
                    evt_key = f"{camera_id}:{det.label}"
                    if now - last_event_times.get(evt_key, 0) > 3.0:
                        last_event_times[evt_key] = now
                        evt_type = f"{det.label.lower()}_detected"
                        event_manager.process_and_emit(
                            camera_id=camera_id,
                            camera_name=f"Camera {camera_id}",
                            event_type=evt_type,
                            label=det.label,
                            confidence=det.confidence,
                            bbox=det.bbox.model_dump(),
                            details=det.attributes
                        )

                # Process Zone Breaches
                for breach in breaches:
                    evt_key = f"{camera_id}:intrusion:{breach['zone_id']}"
                    if now - last_event_times.get(evt_key, 0) > 2.0:
                        last_event_times[evt_key] = now
                        event_manager.process_and_emit(
                            camera_id=camera_id,
                            camera_name=f"Camera {camera_id}",
                            event_type="intrusion_breach",
                            label=f"Intrusion Alert ({breach['label']})",
                            confidence=breach["confidence"],
                            bbox=breach["bbox"],
                            zone_id=breach["zone_id"],
                            details={"zone_name": breach["zone_name"], "breach_point": breach["breach_point"]}
                        )

                with self.lock:
                    self.annotated_frames[camera_id] = annotated
                    self.latest_detections[camera_id] = det_dicts

            time.sleep(0.1)

pipeline_engine = AIPipelineEngine()
