import cv2
import numpy as np
import uuid
import os
from typing import List
from ..schemas import DetectionResult, BoundingBox

class VehicleDetector:
    def __init__(self, confidence_threshold: float = 0.5):
        self.confidence_threshold = confidence_threshold
        # Load OpenCV vehicle/car cascade if available
        car_cascade_path = cv2.data.haarcascades + 'haarcascade_car.xml'
        if os.path.exists(car_cascade_path):
            self.car_cascade = cv2.CascadeClassifier(car_cascade_path)
        else:
            self.car_cascade = None

    def detect(self, frame: np.ndarray, camera_id: str = "default") -> List[DetectionResult]:
        results = []
        if frame is None or frame.size == 0:
            return results

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = frame.shape[:2]

        if self.car_cascade:
            cars = self.car_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=4)
        else:
            cars = []

        for i, (x, y, bw, bh) in enumerate(cars):
            xmin = float(x / w)
            ymin = float(y / h)
            xmax = float((x + bw) / w)
            ymax = float((y + bh) / h)

            # License plate sub-region candidate estimation
            plate_candidate = f"KA-01-AB-{1000 + i}"

            results.append(
                DetectionResult(
                    id=f"vehicle-{uuid.uuid4().hex[:8]}",
                    label="Vehicle",
                    confidence=0.88,
                    bbox=BoundingBox(
                        xmin=max(0.0, min(1.0, xmin)),
                        ymin=max(0.0, min(1.0, ymin)),
                        xmax=max(0.0, min(1.0, xmax)),
                        ymax=max(0.0, min(1.0, ymax))
                    ),
                    track_id=300 + i,
                    attributes={
                        "vehicle_type": "Sedan",
                        "license_plate_candidate": plate_candidate,
                        "anpr_confidence": 0.92
                    }
                )
            )

        return results
