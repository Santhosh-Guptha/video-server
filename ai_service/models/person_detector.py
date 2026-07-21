import sys
import os
import cv2
import numpy as np
import uuid
import time
from typing import List, Optional

# Ensure system dist-packages is in sys.path for ultralytics & PyTorch
for p in ["/usr/local/lib/python3.10/dist-packages", "/usr/lib/python3/dist-packages"]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.append(p)

from ..schemas import DetectionResult, BoundingBox

# COCO person-related class IDs
PERSON_CLASS_IDS = {0}  # 0: person (includes partial bodies, heads, etc.)

class PersonDetector:
    def __init__(self, confidence_threshold: float = 0.15, shared_model=None):
        self.confidence_threshold = confidence_threshold
        self.yolo_model = shared_model

        # Load own model only if no shared model was provided
        if self.yolo_model is None:
            try:
                from ultralytics import YOLO
                self.yolo_model = YOLO("yolov8s.pt")
                print("[PersonDetector] Loaded own YOLOv8s model")
            except Exception as e:
                print(f"[PersonDetector] YOLOv8 load error ({e})")

    def detect(self, frame: np.ndarray, camera_id: str = "default",
               confidence_override: float = None) -> List[DetectionResult]:
        results = []
        if frame is None or frame.size == 0:
            return results

        conf = confidence_override if confidence_override is not None else self.confidence_threshold
        h, w = frame.shape[:2]

        if self.yolo_model is not None:
            try:
                # Use higher resolution for better small-object detection
                predictions = self.yolo_model(frame, verbose=False, conf=conf, imgsz=960)
                if predictions and len(predictions) > 0:
                    boxes = predictions[0].boxes
                    for box in boxes:
                        cls_id = int(box.cls[0].item())
                        box_conf = float(box.conf[0].item())

                        if cls_id in PERSON_CLASS_IDS and box_conf >= conf:
                            xyxy = box.xyxy[0].tolist()
                            xmin = float(xyxy[0] / w)
                            ymin = float(xyxy[1] / h)
                            xmax = float(xyxy[2] / w)
                            ymax = float(xyxy[3] / h)

                            # Determine if it's a full body or partial (head/upper body)
                            box_h = ymax - ymin
                            box_w = xmax - xmin
                            aspect = box_h / max(box_w, 0.001)
                            if aspect < 0.8 and box_h < 0.15:
                                sub_label = "Head"
                            elif aspect < 1.2:
                                sub_label = "Upper Body"
                            else:
                                sub_label = "Person"

                            results.append(
                                DetectionResult(
                                    id=f"person-{uuid.uuid4().hex[:8]}",
                                    label=sub_label,
                                    class_name="person",
                                    confidence=round(box_conf, 2),
                                    bbox=BoundingBox(
                                        xmin=max(0.0, min(1.0, xmin)),
                                        ymin=max(0.0, min(1.0, ymin)),
                                        xmax=max(0.0, min(1.0, xmax)),
                                        ymax=max(0.0, min(1.0, ymax))
                                    ),
                                    track_id=int(time.time() * 1000) % 10000,
                                    attributes={"class": "human", "sub_type": sub_label.lower(), "mode": "yolov8s"}
                                )
                            )
            except Exception as e:
                print(f"[PersonDetector] YOLO inference error: {e}")

        return results
