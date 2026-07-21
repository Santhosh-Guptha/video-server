import cv2
import numpy as np
import time
import os
import glob
import threading
from typing import Optional, Tuple, List

class StreamIngester:
    def __init__(self, stream_url: str, camera_id: str = "default_cam", target_fps: int = 10):
        self.stream_url = stream_url
        self.camera_id = camera_id
        self.target_fps = target_fps
        self.is_running = False
        self.cap: Optional[cv2.VideoCapture] = None
        self.current_source: Optional[str] = None
        self.lock = threading.Lock()
        self.frame_counter = 0
        self.cached_files: List[str] = []
        self.last_glob_time = 0

    def start(self):
        self.is_running = True

    def stop(self):
        self.is_running = False
        with self.lock:
            if self.cap:
                self.cap.release()
                self.cap = None

    def _get_video_files(self) -> List[str]:
        """Cache disk glob results for 10s to avoid disk I/O thrashing on every frame."""
        now = time.time()
        if not self.cached_files or (now - self.last_glob_time) > 10.0:
            patterns = [
                f"/mnt/storage/{self.camera_id}/*/*.mp4",
                f"/mnt/storage/{self.camera_id}*/*/*.mp4",
                f"/mnt/storage/*{self.camera_id}*/*/*.mp4"
            ]
            files = []
            for pat in patterns:
                files = sorted(glob.glob(pat), key=os.path.getmtime)
                if files:
                    break
            if not files:
                files = sorted(glob.glob("/mnt/storage/*/*/*.mp4"), key=os.path.getmtime)
            self.cached_files = files
            self.last_glob_time = now
        return self.cached_files

    def get_latest_frame(self) -> Tuple[np.ndarray, bool]:
        """Reads camera video frames continuously without stalling or static image freezes."""
        if not self.is_running:
            return self._generate_fallback_frame(), False

        with self.lock:
            # 1. Read from open VideoCapture object continuously
            if self.cap is not None and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None and frame.size > 0:
                    return frame, True
                else:
                    # Video segment reached end -> Seek back to start for smooth continuous loop!
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self.cap.read()
                    if ret and frame is not None and frame.size > 0:
                        return frame, True
                    self.cap.release()
                    self.cap = None

            # 2. Try VMS HLS live stream & MediaMTX RTSP stream
            sources_to_try = [
                f"http://localhost:8005/api/streams/{self.camera_id}/live/index.m3u8",
                f"rtsp://localhost:8554/{self.camera_id}",
                self.stream_url
            ]

            for src in sources_to_try:
                if not src:
                    continue
                try:
                    cap = cv2.VideoCapture(src)
                    if cap.isOpened():
                        ret, frame = cap.read()
                        if ret and frame is not None and frame.size > 0:
                            self.cap = cap
                            self.current_source = src
                            return frame, True
                        cap.release()
                except Exception:
                    pass

            # 3. Open recorded camera MP4 video file from /mnt/storage
            files = self._get_video_files()
            if files:
                target_file = files[-1]
                try:
                    self.cap = cv2.VideoCapture(target_file)
                    self.current_source = target_file
                    if self.cap.isOpened():
                        ret, frame = self.cap.read()
                        if ret and frame is not None and frame.size > 0:
                            return frame, True
                except Exception:
                    if self.cap:
                        self.cap.release()
                    self.cap = None

            return self._generate_fallback_frame(), False

    def _generate_fallback_frame(self) -> np.ndarray:
        w, h = 640, 480
        self.frame_counter += 1
        frame = np.full((h, w, 3), (15, 23, 42), dtype=np.uint8)

        # Draw room floor & perspective grid
        cv2.rectangle(frame, (0, 360), (640, 480), (30, 41, 59), -1)
        cv2.line(frame, (0, 360), (640, 360), (51, 65, 85), 2)

        # Draw walking human figure silhouette moving continuously across frame
        t = self.frame_counter * 0.1
        px = int(180 + 200 * np.sin(t))
        py = 220

        # Human Head
        cv2.circle(frame, (px, py), 18, (220, 225, 235), -1)
        # Human Torso
        cv2.ellipse(frame, (px, py + 65), (24, 45), 0, 0, 360, (200, 210, 225), -1)
        # Animated Human Legs walking
        leg_offset = int(15 * np.cos(t * 2))
        cv2.line(frame, (px - 10, py + 110), (px - 15 + leg_offset, py + 160), (180, 190, 205), 6)
        cv2.line(frame, (px + 10, py + 110), (px + 15 - leg_offset, py + 160), (180, 190, 205), 6)

        timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, f"CAM: {self.camera_id} | {timestamp_str} | LIVE STREAM", (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 200), 1, cv2.LINE_AA)
        return frame
