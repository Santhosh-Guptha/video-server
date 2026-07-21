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
    def __init__(self, confidence_threshold: float = 0.35):
        self.confidence_threshold = confidence_threshold
        self.yolo_model = None
        self.hog = None
        self.fullbody_cascade = None
        self.upperbody_cascade = None

        # 1. Try loading Ultralytics YOLOv8 nano
        try:
            from ultralytics import YOLO
            # Load yolov8n.pt (downloads automatically ~6MB if missing)
            self.yolo_model = YOLO("yolov8n.pt")
            print("[PersonDetector] Successfully loaded YOLOv8 model!")
        except Exception as e:
            print(f"[PersonDetector] YOLOv8 not available ({e}), falling back to OpenCV HOG/Haar")

        # 2. OpenCV HOG People Detector (fallback)
        try:
            self.hog = cv2.HOGDescriptor()
            self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        except Exception:
            self.hog = None

        # 3. OpenCV Haar Cascade (fallback)
        try:
            fb_path = cv2.data.haarcascades + 'haarcascade_fullbody.xml'
            ub_path = cv2.data.haarcascades + 'haarcascade_upperbody.xml'
            if os.path.exists(fb_path):
                self.fullbody_cascade = cv2.CascadeClassifier(fb_path)
            if os.path.exists(ub_path):
                self.upperbody_cascade = cv2.CascadeClassifier(ub_path)
        except Exception:
            pass

    def detect(self, frame: np.ndarray, camera_id: str = "default") -> List[DetectionResult]:
        results = []
        if frame is None or frame.size == 0:
            return results

        h, w = frame.shape[:2]

        # ─── Tier 1: Ultralytics YOLOv8 Detection ─────────────────────
        if self.yolo_model is not None:
            try:
                # Run inference on frame
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

                    if len(results) > 0:
                        return results
            except Exception as e:
                print(f"[PersonDetector] YOLO inference error: {e}")

        # ─── Tier 2: OpenCV HOG MultiScale People Detector ──────────
        if self.hog is not None:
            try:
                scale = 1.0
                if w > 640:
                    scale = 640.0 / w
                    resized_frame = cv2.resize(frame, (640, int(h * scale)))
                else:
                    resized_frame = frame

                rh, rw = resized_frame.shape[:2]

                boxes, weights = self.hog.detectMultiScale(
                    resized_frame,
                    winStride=(4, 4),
                    padding=(8, 8),
                    scale=1.05,
                    hitThreshold=0.2
                )

                for i, (x, y, bw, bh) in enumerate(boxes):
                    weight = float(weights[i]) if (weights is not None and i < len(weights)) else 0.5
                    if weight >= 0.3:
                        conf = min(0.98, max(0.65, 0.70 + (weight * 0.2)))

                        xmin = float(x / rw)
                        ymin = float(y / rh)
                        xmax = float((x + bw) / rw)
                        ymax = float((y + bh) / rh)

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
                                track_id=100 + i,
                                attributes={"class": "human", "mode": "hog_svm"}
                            )
                        )
                if len(results) > 0:
                    return results
            except Exception:
                pass

        # ─── Tier 3: Haar Cascade Body Detector ─────────────────────
        if self.fullbody_cascade is not None or self.upperbody_cascade is not None:
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                bodies = []
                if self.fullbody_cascade is not None:
                    bodies = self.fullbody_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 80))
                if len(bodies) == 0 and self.upperbody_cascade is not None:
                    bodies = self.upperbody_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 70))

                for i, (x, y, bw, bh) in enumerate(bodies):
                    xmin = float(x / w)
                    ymin = float(y / h)
                    xmax = float((x + bw) / w)
                    ymax = float((y + bh) / h)

                    results.append(
                        DetectionResult(
                            id=f"person-{uuid.uuid4().hex[:8]}",
                            label="Person",
                            class_name="person",
                            confidence=0.85,
                            bbox=BoundingBox(
                                xmin=max(0.0, min(1.0, xmin)),
                                ymin=max(0.0, min(1.0, ymin)),
                                xmax=max(0.0, min(1.0, xmax)),
                                ymax=max(0.0, min(1.0, ymax))
                            ),
                            track_id=200 + i,
                            attributes={"class": "human", "mode": "haar_cascade"}
                        )
                    )
                if len(results) > 0:
                    return results
            except Exception:
                pass

        return results
