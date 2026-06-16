"""
Edge Push Client – Camera Video Platform
=========================================
Reads camera streams via RTSP using FFmpeg, then pushes raw H264/H265
NAL units to the VMS server using the custom TCP binary protocol.

Protocol:
  Every TCP message = 4-byte big-endian length header + body
  Body types:
    0x01 0x05 → Camera CONFIG packet  (sent once on connect)
    0x02      → IMAGE / frame packet  (sent per NAL unit)

Dependencies:
  - Python 3.8+
  - ffmpeg  (must be in PATH)
  - ffprobe (must be in PATH)

Usage:
  python3 edge_push.py
  python3 edge_push.py --config /path/to/edge_push_config.json
"""

import socket
import struct
import subprocess
import time
import json
import threading
import traceback
import base64
import select
import argparse
import logging
import sys
import os

# ──────────────────────────────────────────────
#  Logging
# ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("edge-push")


# ──────────────────────────────────────────────
#  Protocol Constants  (DO NOT CHANGE)
# ──────────────────────────────────────────────

PROXY_METADATA_COMMAND          = 0x01
PROXY_METADATA_IMAGE            = 0x02
PROXY_COMMAND_TYPE_CAMERA_CONFIG = 0x05

ENCODE_TYPE_H264 = 3
ENCODE_TYPE_H265 = 10

STATS_LOG_INTERVAL = 10   # seconds between FPS log lines
RECONNECT_DELAY    = 5    # seconds before reconnect on error


# ──────────────────────────────────────────────
#  Codec / FPS Detection
# ──────────────────────────────────────────────

def detect_codec_and_fps(rtsp_url: str):
    """Use ffprobe to detect codec name and average FPS from an RTSP stream."""
    out = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,avg_frame_rate",
        "-of", "json",
        rtsp_url,
    ], timeout=15).decode()

    stream = json.loads(out)["streams"][0]
    codec  = stream["codec_name"]
    n, d   = map(int, stream["avg_frame_rate"].split("/"))
    fps    = n / d if d else 25.0
    return codec, fps


# ──────────────────────────────────────────────
#  NAL Unit Helpers
# ──────────────────────────────────────────────

def nal_type_h264(nal: bytes) -> int:
    return nal[4] & 0x1F


def nal_type_h265(nal: bytes) -> int:
    return (nal[4] >> 1) & 0x3F


def is_h264_idr(nal: bytes) -> bool:
    return nal_type_h264(nal) == 5


def is_h265_idr(nal: bytes) -> bool:
    return nal_type_h265(nal) in (19, 20)


# ──────────────────────────────────────────────
#  NAL Stream Reader
# ──────────────────────────────────────────────

class NalReader:
    """Reads Annex-B NAL units from a binary stream (FFmpeg stdout)."""

    START_CODE = b"\x00\x00\x00\x01"

    def __init__(self, stream):
        self.stream = stream
        self.buffer = b""

    def next_nal(self):
        """Return the next complete NAL unit, or None on timeout/EOF."""
        while True:
            idx = self.buffer.find(self.START_CODE, 4)
            if idx != -1:
                nal = self.buffer[:idx]
                self.buffer = self.buffer[idx:]
                return nal

            ready, _, _ = select.select([self.stream], [], [], 5.0)
            if not ready:
                return None  # timeout – caller treats as stream stall

            data = self.stream.read(4096)
            if not data:
                return None  # EOF

            self.buffer += data


# ──────────────────────────────────────────────
#  FFmpeg Process
# ──────────────────────────────────────────────

def start_ffmpeg(rtsp_url: str, codec: str) -> subprocess.Popen:
    """Start FFmpeg in copy mode, outputting raw Annex-B to stdout."""
    fmt = "hevc" if codec in ("hevc", "h265") else "h264"
    log.info(f"Starting FFmpeg ({fmt}) for {rtsp_url}")
    return subprocess.Popen(
        [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-i", rtsp_url,
            "-an",          # drop audio
            "-c:v", "copy", # copy codec – no re-encode
            "-f", fmt,
            "-",            # output to stdout
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
    )


def extract_config_param(ffmpeg: subprocess.Popen, codec: str):
    """
    Read NAL units from FFmpeg until SPS/PPS (H264) or VPS/SPS/PPS (H265)
    are found. Return a base64-encoded comma-separated config string plus
    the remaining buffer to hand off to NalReader.
    """
    sps = pps = vps = None
    buf = b""

    while True:
        buf += ffmpeg.stdout.read(4096)

        while True:
            idx = buf.find(b"\x00\x00\x00\x01", 4)
            if idx == -1:
                break

            nal = buf[:idx]
            buf = buf[idx:]

            if codec == "h264":
                t = nal_type_h264(nal)
                if t == 7:
                    sps = nal
                elif t == 8:
                    pps = nal
                if sps and pps:
                    return ",".join([
                        base64.b64encode(sps).decode(),
                        base64.b64encode(pps).decode(),
                    ]), buf
            else:  # h265 / hevc
                t = nal_type_h265(nal)
                if t == 32:
                    vps = nal
                elif t == 33:
                    sps = nal
                elif t == 34:
                    pps = nal
                if vps and sps and pps:
                    return ",".join([
                        base64.b64encode(vps).decode(),
                        base64.b64encode(sps).decode(),
                        base64.b64encode(pps).decode(),
                    ]), buf


# ──────────────────────────────────────────────
#  TCP Push Client
# ──────────────────────────────────────────────

class EdgePushClient:
    """
    Manages a single TCP connection to the VMS Edge Receiver.
    Sends the camera CONFIG packet once on connect, then streams
    frame packets for each NAL unit received from FFmpeg.
    """

    def __init__(self, cam: dict, codec: str, camera_fps: float):
        self.cam        = cam
        self.codec      = codec
        self.camera_fps = camera_fps
        self.cam_id     = cam["cameraId"]
        self.encode_type = ENCODE_TYPE_H265 if codec in ("hevc", "h265") else ENCODE_TYPE_H264

        self.sock  = None
        self.out   = None
        self.lock  = threading.Lock()
        self.total_frames    = 0
        self.interval_frames = 0
        self.stop_event      = threading.Event()

        self._setup_compression()

        self._stats_thread = threading.Thread(target=self._stats_loop, daemon=True)
        self._stats_thread.start()

    # ── Compression / frame-drop config ──────────

    def _setup_compression(self):
        cfps = self.cam.get("compressedFps")

        if not cfps or cfps >= self.camera_fps:
            self.compress  = False
            self.frame_gap = 1
        else:
            self.compress  = True
            self.frame_gap = int(round(self.camera_fps / cfps))

        self.allow_chain = False
        self.p_count     = 0

        log.info(
            f"[{self.cam_id}] cameraFPS={self.camera_fps:.1f}, "
            f"compressedFPS={cfps}, frameGap={self.frame_gap}, "
            f"compression={'ON' if self.compress else 'OFF'}"
        )

    # ── Connection ───────────────────────────────

    def connect(self, config_param: str):
        self.sock = socket.create_connection(
            (self.cam["pushHost"], self.cam["pushPort"]),
            timeout=10,
        )
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.out = self.sock.makefile("wb")
        self._send_camera_config(config_param)
        log.info(f"[{self.cam_id}] Connected to {self.cam['pushHost']}:{self.cam['pushPort']}")

    # ── Packet builders ──────────────────────────

    def _send_camera_config(self, config_param: str):
        payload = json.dumps({
            "cameraId":    self.cam_id,
            "width":       self.cam["width"],
            "height":      self.cam["height"],
            "configParam": config_param,
            "encoderType": self.encode_type,
            "extras":      {"pushType": self.cam.get("pushType", "RAW_PUSH")},
        }, separators=(",", ":")).encode()

        body = (
            struct.pack(">B", PROXY_METADATA_COMMAND) +
            struct.pack(">B", PROXY_COMMAND_TYPE_CAMERA_CONFIG) +
            struct.pack(">I", 0) +
            payload
        )
        self._send(body)
        log.info(f"[{self.cam_id}] CONFIG packet sent")

    def send_frame(self, nal: bytes):
        if not self.out:
            return

        is_idr = (
            is_h265_idr(nal) if self.encode_type == ENCODE_TYPE_H265
            else is_h264_idr(nal)
        )

        # Frame-drop logic when compression is enabled
        if self.compress:
            if is_idr:
                self.allow_chain = True
                self.p_count     = 0
            elif not self.allow_chain:
                return
            elif self.p_count >= self.frame_gap - 1:
                self.allow_chain = False
                return
            else:
                self.p_count += 1

        ts  = int(time.time() * 1000)
        hdr = json.dumps({
            "cameraId":        self.cam_id,
            "iframe":          is_idr,
            "frameLength":     len(nal),
            "captureTimeStamp": ts,
            "timeStamp":       ts,
        }, separators=(",", ":")).encode()

        body = (
            struct.pack(">B", PROXY_METADATA_IMAGE) +
            struct.pack(">B", self.encode_type) +
            struct.pack(">I", len(hdr)) +
            hdr +
            struct.pack(">I", len(nal)) +
            nal
        )
        self._send(body)

        with self.lock:
            self.total_frames    += 1
            self.interval_frames += 1

    def _send(self, body: bytes):
        try:
            self.out.write(struct.pack(">I", len(body)))
            self.out.write(body)
            self.out.flush()
        except Exception:
            self.out = None
            raise

    # ── Stats logging ────────────────────────────

    def _stats_loop(self):
        last = time.time()
        while not self.stop_event.is_set():
            self.stop_event.wait(STATS_LOG_INTERVAL)
            if self.stop_event.is_set():
                break
            with self.lock:
                now = time.time()
                fps = self.interval_frames / (now - last) if now > last else 0.0
                log.info(f"[{self.cam_id}] pushed={fps:.2f} fps  total={self.total_frames}")
                self.interval_frames = 0
                last = now

    # ── Cleanup ──────────────────────────────────

    def close(self):
        self.stop_event.set()
        try:
            if self.out:
                self.out.close()
            if self.sock:
                self.sock.close()
        except Exception:
            pass


# ──────────────────────────────────────────────
#  Camera Worker Thread
# ──────────────────────────────────────────────

def camera_worker(cam: dict):
    """
    Main loop for a single camera entry.
    Restarts automatically on any error (RTSP disconnect, TCP drop, etc.)
    """
    cam_id = cam["cameraId"]

    while True:
        ffmpeg = None
        client = None
        try:
            log.info(f"[{cam_id}] Detecting codec & FPS …")
            codec, fps = detect_codec_and_fps(cam["rtspUrl"])
            log.info(f"[{cam_id}] codec={codec}  fps={fps:.2f}")

            ffmpeg = start_ffmpeg(cam["rtspUrl"], codec)
            cfg, remaining = extract_config_param(ffmpeg, codec)
            log.info(f"[{cam_id}] Config param extracted")

            reader = NalReader(ffmpeg.stdout)
            reader.buffer = remaining

            client = EdgePushClient(cam, codec, fps)
            client.connect(cfg)
            log.info(f"[{cam_id}] Streaming …")

            while True:
                nal = reader.next_nal()
                if nal is None:
                    raise RuntimeError("RTSP stream stalled or ended")
                client.send_frame(nal)

        except KeyboardInterrupt:
            log.info(f"[{cam_id}] Interrupted")
            break

        except Exception as exc:
            log.error(f"[{cam_id}] ERROR: {exc}")
            traceback.print_exc()

        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass
            if ffmpeg:
                try:
                    ffmpeg.kill()
                    ffmpeg.wait(timeout=3)
                except Exception:
                    pass

        log.info(f"[{cam_id}] Reconnecting in {RECONNECT_DELAY}s …")
        time.sleep(RECONNECT_DELAY)


# ──────────────────────────────────────────────
#  Entry Point
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Edge Push Client – Camera Video Platform")
    parser.add_argument(
        "--config", "-c",
        default=os.path.join(os.path.dirname(__file__), "edge_push_config.json"),
        help="Path to edge_push_config.json (default: same directory as script)",
    )
    args = parser.parse_args()

    with open(args.config) as f:
        cameras = json.load(f)

    if not cameras:
        log.error("No cameras defined in config. Exiting.")
        sys.exit(1)

    log.info(f"Starting edge push for {len(cameras)} camera(s) …")

    threads = []
    for cam in cameras:
        t = threading.Thread(target=camera_worker, args=(cam,), daemon=True, name=cam["cameraId"])
        t.start()
        threads.append(t)

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("Shutting down …")


if __name__ == "__main__":
    main()
