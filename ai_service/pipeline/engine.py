import sys
import os

# Ensure system dist-packages is in sys.path for ultralytics & PyTorch
for p in ["/usr/local/lib/python3.10/dist-packages", "/usr/lib/python3/dist-packages"]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.append(p)

import cv2
import numpy as np
import time
import threading
from typing import Dict, List, Any, Optional

from ..ingester.stream_ingester import StreamIngester
from ..models.person_detector import PersonDetector
from ..models.face_detector import FaceDetector
from ..models.vehicle_detector import VehicleDetector
from ..models.intrusion_detector import IntrusionDetector
from ..database import get_intrusion_zones
from ..events.event_manager import event_manager
from ..schemas import DetectionResult, BoundingBox

# Color palette for different detection types (BGR)
COLORS = {
    "person": (0, 255, 100),       # Green
    "head": (0, 220, 180),         # Teal
    "upper body": (0, 200, 150),   # Light teal
    "face": (255, 200, 0),         # Cyan/Yellow
    "car": (0, 165, 255),          # Orange
    "motorcycle": (0, 200, 255),   # Light Orange
    "bicycle": (200, 255, 0),      # Yellow-Green
    "bus": (0, 100, 255),          # Dark Orange
    "truck": (50, 80, 255),        # Red-Orange
    "train": (255, 0, 150),        # Purple
    "vehicle": (0, 165, 255),      # Orange (fallback)
    "intrusion": (0, 0, 255),      # Red
    "default": (255, 100, 0),      # Blue
}


def get_color(label: str) -> tuple:
    key = label.lower()
    return COLORS.get(key, COLORS["default"])


def compute_iou(box1: List[float], box2: List[float]) -> float:
    """Compute Intersection-over-Union (IoU) of two normalized boxes."""
    xA = max(box1[0], box2[0])
    yA = max(box1[1], box2[1])
    xB = min(box1[2], box2[2])
    yB = min(box1[3], box2[3])

    inter_area = max(0.0, xB - xA) * max(0.0, yB - yA)
    box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])

    union_area = box1_area + box2_area - inter_area
    if union_area <= 0.0:
        return 0.0
    return inter_area / union_area


def draw_fancy_box(frame, xmin, ymin, xmax, ymax, label_str, color, thickness=2):
    """Draw a bounding box with a filled label background for readability."""
    cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), color, thickness)

    # Corner accents (top-left and bottom-right)
    corner_len = min(20, (xmax - xmin) // 4, (ymax - ymin) // 4)
    cv2.line(frame, (xmin, ymin), (xmin + corner_len, ymin), color, thickness + 1)
    cv2.line(frame, (xmin, ymin), (xmin, ymin + corner_len), color, thickness + 1)
    cv2.line(frame, (xmax, ymax), (xmax - corner_len, ymax), color, thickness + 1)
    cv2.line(frame, (xmax, ymax), (xmax, ymax - corner_len), color, thickness + 1)

    # Label background
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.45
    (tw, th), _ = cv2.getTextSize(label_str, font, font_scale, 1)
    label_y = max(0, ymin - 4)
    cv2.rectangle(frame, (xmin, label_y - th - 6), (xmin + tw + 8, label_y), color, -1)
    cv2.putText(frame, label_str, (xmin + 4, label_y - 4), font, font_scale, (0, 0, 0), 1, cv2.LINE_AA)


class AIPipelineEngine:
    """On-demand AI pipeline engine with shared YOLO model and configurable thresholds."""

    def __init__(self):
        # ─── Load Shared YOLOv8s Model (once) ──────────────────────
        self.shared_yolo = None
        try:
            from ultralytics import YOLO
            self.shared_yolo = YOLO("yolov8s.pt")
            print("[Engine] ✓ Shared YOLOv8s model loaded successfully!")
        except Exception as e:
            print(f"[Engine] YOLOv8s load error ({e}), detectors will load own models")

        # ─── Initialize Detectors with Shared Model ────────────────
        self.person_detector = PersonDetector(confidence_threshold=0.15, shared_model=self.shared_yolo)
        self.face_detector = FaceDetector(confidence_threshold=0.30)
        self.vehicle_detector = VehicleDetector(confidence_threshold=0.15, shared_model=self.shared_yolo)
        self.intrusion_detector = IntrusionDetector()

        # ─── State ─────────────────────────────────────────────────
        self.ingesters: Dict[str, StreamIngester] = {}
        self.active_models: Dict[str, List[str]] = {}
        self.annotated_frames: Dict[str, np.ndarray] = {}
        self.latest_detections: Dict[str, List[Dict[str, Any]]] = {}
        self.last_event_times: Dict[str, float] = {}

        # ─── Object Tracking & Stabilization State ─────────────────
        self.tracks: Dict[str, List[Dict[str, Any]]] = {}

        # ─── Configurable Thresholds (per-camera or global) ────────
        self.config: Dict[str, Any] = {
            "person_threshold": 0.15,
            "vehicle_threshold": 0.15,
            "face_threshold": 0.30,
            "inference_size": 960,
        }
        self.camera_configs: Dict[str, Dict[str, Any]] = {}

        self.lock = threading.Lock()

    # ─── Configuration ─────────────────────────────────────────────
    def update_config(self, new_config: Dict[str, Any], camera_id: str = None):
        """Update global or per-camera AI configuration."""
        if camera_id:
            if camera_id not in self.camera_configs:
                self.camera_configs[camera_id] = {}
            self.camera_configs[camera_id].update(new_config)
        else:
            self.config.update(new_config)

    def get_config(self, camera_id: str = None) -> Dict[str, Any]:
        """Get effective config (camera-specific overrides global)."""
        cfg = dict(self.config)
        if camera_id and camera_id in self.camera_configs:
            cfg.update(self.camera_configs[camera_id])
        return cfg

    # ─── Camera Management ─────────────────────────────────────────
    def register_camera(self, camera_id: str, stream_url: str, active_models: List[str]):
        """Register a camera ingester for on-demand processing."""
        with self.lock:
            if camera_id in self.ingesters:
                self.active_models[camera_id] = active_models
                return

            ingester = StreamIngester(stream_url=stream_url, camera_id=camera_id)
            ingester.start()
            self.ingesters[camera_id] = ingester
            self.active_models[camera_id] = active_models
            self.tracks[camera_id] = []

    def unregister_camera(self, camera_id: str):
        """Stop and remove a camera ingester."""
        with self.lock:
            ingester = self.ingesters.pop(camera_id, None)
            if ingester:
                ingester.stop()
            self.active_models.pop(camera_id, None)
            self.annotated_frames.pop(camera_id, None)
            self.latest_detections.pop(camera_id, None)
            self.camera_configs.pop(camera_id, None)
            self.tracks.pop(camera_id, None)

    def update_camera_models(self, camera_id: str, active_models: List[str]):
        with self.lock:
            self.active_models[camera_id] = active_models

    def get_latest_annotated_frame(self, camera_id: str) -> Optional[np.ndarray]:
        with self.lock:
            return self.annotated_frames.get(camera_id)

    def get_latest_detections(self, camera_id: str) -> List[Dict[str, Any]]:
        with self.lock:
            return self.latest_detections.get(camera_id, [])

    def is_camera_active(self, camera_id: str) -> bool:
        return camera_id in self.ingesters

    def get_active_camera_ids(self) -> List[str]:
        return list(self.ingesters.keys())

    # ─── Object Stabilization & Tracking ───────────────────────────
    def track_and_stabilize(self, camera_id: str, new_detections: List[DetectionResult]) -> List[DetectionResult]:
        """
        Track objects across frames using IoU matching and stabilize boxes
        via EMA smoothing + a deadband hysteresis window. Bridge detection gaps.
        """
        if camera_id not in self.tracks:
            self.tracks[camera_id] = []
        tracks = self.tracks[camera_id]

        matched_track_indices = set()
        matched_detection_indices = set()

        # 1. Match current detections to active tracks
        for d_idx, det in enumerate(new_detections):
            best_iou = 0.0
            best_t_idx = -1
            det_box = [det.bbox.xmin, det.bbox.ymin, det.bbox.xmax, det.bbox.ymax]

            for t_idx, track in enumerate(tracks):
                if t_idx in matched_track_indices:
                    continue
                # Ensure class name matches (e.g. don't match person with car)
                if track["class_name"] != det.class_name:
                    continue

                iou = compute_iou(track["bbox"], det_box)
                if iou > best_iou:
                    best_iou = iou
                    best_t_idx = t_idx

            if best_iou >= 0.20:
                matched_track_indices.add(best_t_idx)
                matched_detection_indices.add(d_idx)
                track = tracks[best_t_idx]

                prev_xmin, prev_ymin, prev_xmax, prev_ymax = track["bbox"]
                new_xmin, new_ymin, new_xmax, new_ymax = det_box

                # Deadband calculations
                prev_cx = (prev_xmin + prev_xmax) / 2.0
                prev_cy = (prev_ymin + prev_ymax) / 2.0
                prev_w = prev_xmax - prev_xmin
                prev_h = prev_ymax - prev_ymin

                new_cx = (new_xmin + new_xmax) / 2.0
                new_cy = (new_ymin + new_ymax) / 2.0
                new_w = new_xmax - new_xmin
                new_h = new_ymax - new_ymin

                # Hysteresis shift and size deadband threshold (1.5%)
                shift_limit = 0.015
                size_limit = 0.015

                if (abs(new_cx - prev_cx) < shift_limit and
                        abs(new_cy - prev_cy) < shift_limit and
                        abs(new_w - prev_w) < size_limit and
                        abs(new_h - prev_h) < size_limit):
                    # Stationary object -> lock the bounding box coordinates
                    smoothed_box = [prev_xmin, prev_ymin, prev_xmax, prev_ymax]
                else:
                    # Active movement -> apply EMA smoothing
                    alpha = 0.25
                    smoothed_box = [
                        alpha * new_xmin + (1.0 - alpha) * prev_xmin,
                        alpha * new_ymin + (1.0 - alpha) * prev_ymin,
                        alpha * new_xmax + (1.0 - alpha) * prev_xmax,
                        alpha * new_ymax + (1.0 - alpha) * prev_ymax
                    ]

                # Update track details
                track["bbox"] = smoothed_box
                track["label"] = det.label
                track["confidence"] = 0.3 * det.confidence + 0.7 * track["confidence"]
                track["missed_frames"] = 0
                track["seen_count"] += 1
                track["attributes"] = det.attributes

        # 2. Handle missed tracks
        for t_idx, track in enumerate(tracks):
            if t_idx not in matched_track_indices:
                track["missed_frames"] += 1

        # 3. Create tracks for new unmatched detections
        for d_idx, det in enumerate(new_detections):
            if d_idx not in matched_detection_indices:
                new_track = {
                    "id": det.id,
                    "label": det.label,
                    "class_name": det.class_name,
                    "bbox": [det.bbox.xmin, det.bbox.ymin, det.bbox.xmax, det.bbox.ymax],
                    "confidence": det.confidence,
                    "track_id": int(time.time() * 1000) % 100000 + d_idx,
                    "attributes": det.attributes,
                    "missed_frames": 0,
                    "seen_count": 1
                }
                tracks.append(new_track)

        # 4. Clean up tracks (keep-alive/dropout bridging up to 10 frames)
        max_missed_frames = 10
        active_tracks = [t for t in tracks if t["missed_frames"] <= max_missed_frames]
        self.tracks[camera_id] = active_tracks

        # 5. Convert to DetectionResult objects
        stabilized_results = []
        for track in active_tracks:
            if track["seen_count"] >= 1:
                stabilized_results.append(
                    DetectionResult(
                        id=track["id"],
                        label=track["label"],
                        class_name=track["class_name"],
                        confidence=round(track["confidence"], 2),
                        bbox=BoundingBox(
                            xmin=max(0.0, min(1.0, track["bbox"][0])),
                            ymin=max(0.0, min(1.0, track["bbox"][1])),
                            xmax=max(0.0, min(1.0, track["bbox"][2])),
                            ymax=max(0.0, min(1.0, track["bbox"][3]))
                        ),
                        track_id=track["track_id"],
                        attributes=track["attributes"]
                    )
                )

        return stabilized_results

    # ─── Core Processing ───────────────────────────────────────────
    def process_camera_once(self, camera_id: str) -> Dict[str, Any]:
        """
        On-demand: grab one frame, run AI models, smooth/stabilize boxes,
        draw annotations, cache results, and return detections + zones.
        """
        ingester = self.ingesters.get(camera_id)
        if not ingester:
            return {
                "camera_id": camera_id,
                "timestamp": time.time(),
                "detections": [],
                "zones": [],
                "status": "not_registered"
            }

        frame_result = ingester.get_latest_frame()
        if frame_result is None:
            return {
                "camera_id": camera_id,
                "timestamp": time.time(),
                "detections": self.latest_detections.get(camera_id, []),
                "zones": get_intrusion_zones(camera_id),
                "status": "no_frame"
            }

        frame, is_real = frame_result
        if frame is None:
            return {
                "camera_id": camera_id,
                "timestamp": time.time(),
                "detections": self.latest_detections.get(camera_id, []),
                "zones": get_intrusion_zones(camera_id),
                "status": "no_frame"
            }

        # Get effective config for this camera
        cfg = self.get_config(camera_id)
        active_mods = self.active_models.get(camera_id, ["person"])
        detections = []

        # ─── Execute AI Models ─────────────────────────────────────
        if "person" in active_mods:
            try:
                p_dets = self.person_detector.detect(
                    frame, camera_id,
                    confidence_override=cfg.get("person_threshold")
                )
                detections.extend(p_dets)
            except Exception:
                pass

        if "face" in active_mods:
            try:
                f_dets = self.face_detector.detect(frame, camera_id)
                detections.extend(f_dets)
            except Exception:
                pass

        if "vehicle" in active_mods:
            try:
                v_dets = self.vehicle_detector.detect(
                    frame, camera_id,
                    confidence_override=cfg.get("vehicle_threshold")
                )
                detections.extend(v_dets)
            except Exception:
                pass

        # ─── Apply Bounding Box Tracking & Stabilization ──────────
        detections = self.track_and_stabilize(camera_id, detections)

        # ─── Intrusion Zone Processing ─────────────────────────────
        zones = get_intrusion_zones(camera_id)
        breaches = []
        if "intrusion" in active_mods and zones:
            try:
                breaches = self.intrusion_detector.check_breaches(detections, zones)
            except Exception:
                pass

        # ─── Draw Visual AI Annotations ────────────────────────────
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        # Draw intrusion zone polygons
        for z in zones:
            if z.get("enabled") and z.get("polygon"):
                try:
                    pts = np.array([[int(pt["x"] * w), int(pt["y"] * h)] for pt in z["polygon"]], np.int32)
                    overlay = annotated.copy()
                    cv2.fillPoly(overlay, [pts], (0, 0, 255, 40))
                    cv2.addWeighted(overlay, 0.15, annotated, 0.85, 0, annotated)
                    cv2.polylines(annotated, [pts], isClosed=True, color=(0, 0, 255), thickness=2)
                    cv2.putText(annotated, f"Zone: {z['name']}", (pts[0][0], max(20, pts[0][1] - 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
                except Exception:
                    pass

        det_dicts = []
        now = time.time()

        for det in detections:
            try:
                det_dict = det.model_dump()
                det_dicts.append(det_dict)

                # Draw Bounding Box & Label
                xmin, ymin = int(det.bbox.xmin * w), int(det.bbox.ymin * h)
                xmax, ymax = int(det.bbox.xmax * w), int(det.bbox.ymax * h)

                color = get_color(det.label)
                label_str = f"{det.label} {int(det.confidence * 100)}%"
                draw_fancy_box(annotated, xmin, ymin, xmax, ymax, label_str, color)

                # Rate-limited AI Event Generation (1 event per 3 seconds per label per camera)
                evt_key = f"{camera_id}:{det.label}"
                if now - self.last_event_times.get(evt_key, 0) > 3.0:
                    self.last_event_times[evt_key] = now
                    evt_type = f"{det.class_name or det.label.lower()}_detected"
                    event_manager.process_and_emit(
                        camera_id=camera_id,
                        camera_name=f"Camera {camera_id}",
                        event_type=evt_type,
                        label=det.label,
                        confidence=det.confidence,
                        bbox=det.bbox.model_dump(),
                        details=det.attributes
                    )
            except Exception:
                pass

        # Process Zone Breaches
        for breach in breaches:
            try:
                evt_key = f"{camera_id}:intrusion:{breach['zone_id']}"
                if now - self.last_event_times.get(evt_key, 0) > 2.0:
                    self.last_event_times[evt_key] = now
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
            except Exception:
                pass

        # Draw detection count HUD overlay
        det_count = len(detections)
        if det_count > 0:
            hud_text = f"Detections: {det_count}"
            cv2.rectangle(annotated, (w - 160, 8), (w - 10, 30), (0, 0, 0), -1)
            cv2.putText(annotated, hud_text, (w - 155, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 200), 1, cv2.LINE_AA)

        with self.lock:
            self.annotated_frames[camera_id] = annotated
            self.latest_detections[camera_id] = det_dicts

        return {
            "camera_id": camera_id,
            "timestamp": now,
            "detections": det_dicts,
            "zones": zones,
            "status": "ok"
        }


pipeline_engine = AIPipelineEngine()
