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

# COCO vehicle class IDs
VEHICLE_CLASS_IDS = {
    1: "Bicycle",
    2: "Car",
    3: "Motorcycle",
    5: "Bus",
    6: "Train",
    7: "Truck"
}

class VehicleDetector:
    def __init__(self, confidence_threshold: float = 0.15, shared_model=None):
        self.confidence_threshold = confidence_threshold
        self.yolo_model = shared_model
        self.car_cascade = None

        # Load own model only if no shared model was provided
        if self.yolo_model is None:
            try:
                from ultralytics import YOLO
                self.yolo_model = YOLO("yolov8s.pt")
                print("[VehicleDetector] Loaded own YOLOv8s model")
            except Exception as e:
                print(f"[VehicleDetector] YOLOv8 not available ({e})")

        # OpenCV Haar Cascade as ultimate fallback
        try:
            car_cascade_path = cv2.data.haarcascades + 'haarcascade_car.xml'
            if os.path.exists(car_cascade_path):
                self.car_cascade = cv2.CascadeClassifier(car_cascade_path)
        except Exception:
            pass

    def detect(self, frame: np.ndarray, camera_id: str = "default",
               confidence_override: float = None) -> List[DetectionResult]:
        results = []
        if frame is None or frame.size == 0:
            return results

        conf = confidence_override if confidence_override is not None else self.confidence_threshold
        h, w = frame.shape[:2]

        # ─── YOLOv8 Detection ─────────────────────────────────────────
        if self.yolo_model is not None:
            try:
                predictions = self.yolo_model(frame, verbose=False, conf=conf, imgsz=960)
                if predictions and len(predictions) > 0:
                    boxes = predictions[0].boxes
                    for box in boxes:
                        cls_id = int(box.cls[0].item())
                        box_conf = float(box.conf[0].item())

                        if cls_id in VEHICLE_CLASS_IDS and box_conf >= conf:
                            vehicle_label = VEHICLE_CLASS_IDS[cls_id]
                            xyxy = box.xyxy[0].tolist()
                            xmin = float(xyxy[0] / w)
                            ymin = float(xyxy[1] / h)
                            xmax = float(xyxy[2] / w)
                            ymax = float(xyxy[3] / h)

                            results.append(
                                DetectionResult(
                                    id=f"vehicle-{uuid.uuid4().hex[:8]}",
                                    label=vehicle_label,
                                    class_name="vehicle",
                                    confidence=round(box_conf, 2),
                                    bbox=BoundingBox(
                                        xmin=max(0.0, min(1.0, xmin)),
                                        ymin=max(0.0, min(1.0, ymin)),
                                        xmax=max(0.0, min(1.0, xmax)),
                                        ymax=max(0.0, min(1.0, ymax))
                                    ),
                                    track_id=int(time.time() * 1000) % 10000,
                                    attributes={"vehicle_type": vehicle_label, "mode": "yolov8s"}
                                )
                            )

                    if len(results) > 0:
                        return results
            except Exception as e:
                print(f"[VehicleDetector] YOLO inference error: {e}")

        # ─── Haar Cascade Fallback ────────────────────────────────────
        if self.car_cascade is not None:
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                cars = self.car_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=4)
                for i, (x, y, bw, bh) in enumerate(cars):
                    xmin = float(x / w)
                    ymin = float(y / h)
                    xmax = float((x + bw) / w)
                    ymax = float((y + bh) / h)
                    results.append(
                        DetectionResult(
                            id=f"vehicle-{uuid.uuid4().hex[:8]}",
                            label="Car",
                            class_name="vehicle",
                            confidence=0.82,
                            bbox=BoundingBox(
                                xmin=max(0.0, min(1.0, xmin)),
                                ymin=max(0.0, min(1.0, ymin)),
                                xmax=max(0.0, min(1.0, xmax)),
                                ymax=max(0.0, min(1.0, ymax))
                            ),
                            track_id=300 + i,
                            attributes={"vehicle_type": "Car", "mode": "haar_cascade"}
                        )
                    )
            except Exception:
                pass

        return results
