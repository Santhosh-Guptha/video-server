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

    def get_latest_frame(self) -> Optional[Tuple[np.ndarray, bool]]:
        """Reads camera video frames. Returns None if no source available."""
        if not self.is_running:
            return None

        with self.lock:
            # 1. Read from open VideoCapture object continuously
            if self.cap is not None and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None and frame.size > 0:
                    return frame, True
                else:
                    # Video segment reached end -> Seek back to start for smooth continuous loop
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

            # No source available — return None cleanly
            return None
