import cv2
import numpy as np
import uuid
from typing import List
from ..schemas import DetectionResult, BoundingBox

class PersonDetector:
    def __init__(self, confidence_threshold: float = 0.45):
        self.confidence_threshold = confidence_threshold
        # Check if cv2.HOGDescriptor is available in current OpenCV build
        if hasattr(cv2, 'HOGDescriptor') and hasattr(cv2, 'HOGDescriptor_getDefaultPeopleDetector'):
            try:
                self.hog = cv2.HOGDescriptor()
                self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            except Exception:
                self.hog = None
        else:
            self.hog = None

    def detect(self, frame: np.ndarray, camera_id: str = "default") -> List[DetectionResult]:
        results = []
        if frame is None or frame.size == 0:
            return results

        h, w = frame.shape[:2]

        if self.hog is not None:
            try:
                # Downscale for high speed inference if high res
                scale = 1.0
                if w > 640:
                    scale = 640.0 / w
                    resized_frame = cv2.resize(frame, (640, int(h * scale)))
                else:
                    resized_frame = frame

                rh, rw = resized_frame.shape[:2]

                boxes, weights = self.hog.detectMultiScale(
                    resized_frame,
                    winStride=(8, 8),
                    padding=(4, 4),
                    scale=1.05
                )

                for i, (x, y, bw, bh) in enumerate(boxes):
                    weight = weights[i] if i < len(weights) else 0.75
                    if weight >= self.confidence_threshold:
                        xmin = float(x / rw)
                        ymin = float(y / rh)
                        xmax = float((x + bw) / rw)
                        ymax = float((y + bh) / rh)

                        results.append(
                            DetectionResult(
                                id=f"person-{uuid.uuid4().hex[:8]}",
                                label="Person",
                                confidence=round(float(weight), 2),
                                bbox=BoundingBox(
                                    xmin=max(0.0, min(1.0, xmin)),
                                    ymin=max(0.0, min(1.0, ymin)),
                                    xmax=max(0.0, min(1.0, xmax)),
                                    ymax=max(0.0, min(1.0, ymax))
                                ),
                                track_id=100 + i,
                                attributes={"class": "human", "pose": "standing"}
                            )
                        )
                return results
            except Exception:
                pass

        # Fallback Contour & Motion/Shape-based Human Silhouette Detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(blur, 60, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for i, cnt in enumerate(contours[:3]):
            x, y, bw, bh = cv2.boundingRect(cnt)
            # Aspect ratio check for human shape (taller than wide)
            if bh > 40 and (bh / float(bw + 1e-5)) > 1.2:
                xmin = float(x / w)
                ymin = float(y / h)
                xmax = float((x + bw) / w)
                ymax = float((y + bh) / h)

                results.append(
                    DetectionResult(
                        id=f"person-{uuid.uuid4().hex[:8]}",
                        label="Person",
                        confidence=0.82,
                        bbox=BoundingBox(
                            xmin=max(0.0, min(1.0, xmin)),
                            ymin=max(0.0, min(1.0, ymin)),
                            xmax=max(0.0, min(1.0, xmax)),
                            ymax=max(0.0, min(1.0, ymax))
                        ),
                        track_id=100 + i,
                        attributes={"class": "human", "mode": "silhouette"}
                    )
                )

        return results
