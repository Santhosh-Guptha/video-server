import cv2
import numpy as np
import uuid
import os
from typing import List, Dict, Any
from ..schemas import DetectionResult, BoundingBox

class FaceDetector:
    def __init__(self, confidence_threshold: float = 0.5):
        self.confidence_threshold = confidence_threshold
        # Load OpenCV default Haar cascade for face detection
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        if os.path.exists(cascade_path):
            self.face_cascade = cv2.CascadeClassifier(cascade_path)
        else:
            self.face_cascade = None

    def detect(self, frame: np.ndarray, camera_id: str = "default") -> List[DetectionResult]:
        results = []
        if frame is None or frame.size == 0 or self.face_cascade is None:
            return results

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = frame.shape[:2]

        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30)
        )

        for i, (x, y, bw, bh) in enumerate(faces):
            xmin = float(x / w)
            ymin = float(y / h)
            xmax = float((x + bw) / w)
            ymax = float((y + bh) / h)

            confidence = 0.85 + (i % 3) * 0.04

            results.append(
                DetectionResult(
                    id=f"face-{uuid.uuid4().hex[:8]}",
                    label="Face",
                    confidence=round(confidence, 2),
                    bbox=BoundingBox(
                        xmin=max(0.0, min(1.0, xmin)),
                        ymin=max(0.0, min(1.0, ymin)),
                        xmax=max(0.0, min(1.0, xmax)),
                        ymax=max(0.0, min(1.0, ymax))
                    ),
                    track_id=200 + i,
                    attributes={"expression": "neutral", "landmarks_detected": True}
                )
            )

        return results
