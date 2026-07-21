import cv2
import numpy as np
import time
import os
import glob
import threading
from typing import Optional, Tuple, List

class StreamIngester:
    def __init__(self, stream_url: str, camera_id: str = "default_cam", target_fps: int = 15):
        self.stream_url = stream_url
        self.camera_id = camera_id
        self.target_fps = target_fps
        self.is_running = False
        self.cap: Optional[cv2.VideoCapture] = None
        self.latest_frame: Optional[np.ndarray] = None
        self.lock = threading.Lock()
        self.worker_thread: Optional[threading.Thread] = None
        self.cached_files: List[str] = []
        self.last_glob_time = 0

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.worker_thread.start()

    def stop(self):
        self.is_running = False
        with self.lock:
            if self.cap:
                self.cap.release()
                self.cap = None
            self.latest_frame = None

    def _get_video_files(self) -> List[str]:
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

    def _reader_loop(self):
        """Dedicated background reader thread: continuously consumes video stream & flushes buffer to guarantee zero-latency live frames."""
        while self.is_running:
            # 1. Connect to video source if not open
            if self.cap is None or not self.cap.isOpened():
                sources_to_try = [
                    f"rtsp://localhost:8554/{self.camera_id}",
                    f"http://localhost:8005/api/streams/{self.camera_id}/live/index.m3u8",
                    self.stream_url
                ]

                connected = False
                for src in sources_to_try:
                    if not src:
                        continue
                    try:
                        cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
                        # Set buffer size to 1 to disable frame queuing in FFmpeg
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        if cap.isOpened():
                            ret, frame = cap.read()
                            if ret and frame is not None and frame.size > 0:
                                self.cap = cap
                                with self.lock:
                                    self.latest_frame = frame
                                connected = True
                                break
                            cap.release()
                    except Exception:
                        pass

                if not connected:
                    # Fallback to local recorded MP4
                    files = self._get_video_files()
                    if files:
                        try:
                            cap = cv2.VideoCapture(files[-1])
                            if cap.isOpened():
                                ret, frame = cap.read()
                                if ret and frame is not None and frame.size > 0:
                                    self.cap = cap
                                    with self.lock:
                                        self.latest_frame = frame
                                    connected = True
                        except Exception:
                            if self.cap:
                                self.cap.release()
                                self.cap = None

                if not connected:
                    time.sleep(0.5)
                    continue

            # 2. Continuously read newest frame & discard stale buffered frames
            try:
                # Flush extra queued frames if any
                for _ in range(2):
                    self.cap.grab()

                ret, frame = self.cap.retrieve()
                if not ret or frame is None or frame.size == 0:
                    ret, frame = self.cap.read()

                if ret and frame is not None and frame.size > 0:
                    with self.lock:
                        self.latest_frame = frame
                else:
                    # Loop recorded file or reconnect stream
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self.cap.read()
                    if ret and frame is not None and frame.size > 0:
                        with self.lock:
                            self.latest_frame = frame
                    else:
                        if self.cap:
                            self.cap.release()
                            self.cap = None
                        time.sleep(0.1)
            except Exception:
                if self.cap:
                    self.cap.release()
                    self.cap = None
                time.sleep(0.1)

            # Throttle reader loop to target FPS (~25 FPS)
            time.sleep(1.0 / 25.0)

    def get_latest_frame(self) -> Optional[Tuple[np.ndarray, bool]]:
        """Returns the absolute newest live frame instantly from the background reader buffer."""
        if not self.is_running:
            return None

        with self.lock:
            if self.latest_frame is not None:
                return self.latest_frame.copy(), True

        return None
