import sys
import os
import cv2
import numpy as np
import uuid
import time
from typing import List

# Ensure system dist-packages is in sys.path for ultralytics & PyTorch
for p in ["/usr/local/lib/python3.10/dist-packages", "/usr/lib/python3/dist-packages"]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.append(p)

from ..schemas import DetectionResult, BoundingBox

class PersonDetector:
    def __init__(self, confidence_threshold: float = 0.20):
        self.confidence_threshold = confidence_threshold
        self.yolo_model = None

        # Try loading Ultralytics YOLOv8 nano
        try:
            from ultralytics import YOLO
            self.yolo_model = YOLO("yolov8n.pt")
            print("[PersonDetector] Successfully loaded YOLOv8 model!")
        except Exception as e:
            print(f"[PersonDetector] YOLOv8 load error ({e})")

    def detect(self, frame: np.ndarray, camera_id: str = "default") -> List[DetectionResult]:
        results = []
        if frame is None or frame.size == 0:
            return results

        h, w = frame.shape[:2]

        # ─── Ultralytics YOLOv8 Detection ─────────────────────────────
        if self.yolo_model is not None:
            try:
                predictions = self.yolo_model(frame, verbose=False, conf=self.confidence_threshold)
                if predictions and len(predictions) > 0:
                    boxes = predictions[0].boxes
                    for box in boxes:
                        cls_id = int(box.cls[0].item())
                        conf = float(box.conf[0].item())

                        # Class 0 in COCO is person
                        if cls_id == 0 and conf >= self.confidence_threshold:
                            xyxy = box.xyxy[0].tolist()  # [xmin, ymin, xmax, ymax] in pixels
                            xmin = float(xyxy[0] / w)
                            ymin = float(xyxy[1] / h)
                            xmax = float(xyxy[2] / w)
                            ymax = float(xyxy[3] / h)

                            results.append(
                                DetectionResult(
                                    id=f"person-{uuid.uuid4().hex[:8]}",
                                    label="Person",
                                    class_name="person",
                                    confidence=round(conf, 2),
                                    bbox=BoundingBox(
                                        xmin=max(0.0, min(1.0, xmin)),
                                        ymin=max(0.0, min(1.0, ymin)),
                                        xmax=max(0.0, min(1.0, xmax)),
                                        ymax=max(0.0, min(1.0, ymax))
                                    ),
                                    track_id=int(time.time() * 1000) % 10000,
                                    attributes={"class": "human", "mode": "yolov8n"}
                                )
                            )

                    return results
            except Exception as e:
                print(f"[PersonDetector] YOLO inference error: {e}")

        return results
