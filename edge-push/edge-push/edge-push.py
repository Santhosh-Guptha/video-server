import socket
import struct
import subprocess
import time
import json
import threading
import traceback
import base64
import select

# ================= PROTOCOL CONSTANTS =================

PROXY_METADATA_COMMAND = 0x01
PROXY_METADATA_IMAGE = 0x02
PROXY_COMMAND_TYPE_CAMERA_CONFIG = 0x05

ENCODE_TYPE_H264 = 3
ENCODE_TYPE_H265 = 10

STATS_LOG_INTERVAL = 10
RECONNECT_DELAY = 5

# =====================================================


def log(msg):
    print(f"[EDGE] {time.strftime('%H:%M:%S')} {msg}", flush=True)


# ---------- Detect codec & FPS ----------

def detect_codec_and_fps(rtsp_url):
    out = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,avg_frame_rate",
        "-of", "json", rtsp_url
    ]).decode()

    s = json.loads(out)["streams"][0]
    codec = s["codec_name"]
    n, d = map(int, s["avg_frame_rate"].split("/"))
    fps = n / d if d else 25.0
    return codec, fps


# ---------- NAL helpers ----------

def nal_type_h264(n):
    return n[4] & 0x1F


def nal_type_h265(n):
    return (n[4] >> 1) & 0x3F


def is_h264_idr(n):
    return nal_type_h264(n) == 5


def is_h265_idr(n):
    return nal_type_h265(n) in (19, 20)


# ---------- NAL Reader ----------

class NalReader:
    def __init__(self, stream):
        self.stream = stream
        self.buffer = b""

    def next_nal(self):
        while True:
            idx = self.buffer.find(b"\x00\x00\x00\x01", 4)
            if idx != -1:
                nal = self.buffer[:idx]
                self.buffer = self.buffer[idx:]
                return nal

            ready, _, _ = select.select([self.stream], [], [], 5.0)
            if not ready:
                return None

            data = self.stream.read(4096)
            if not data:
                return None

            self.buffer += data


# ---------- FFmpeg ----------

def start_ffmpeg(rtsp_url, codec):
    fmt = "hevc" if codec in ("hevc", "h265") else "h264"
    log(f"Starting FFmpeg ({fmt})")
    return subprocess.Popen(
        ["ffmpeg", "-rtsp_transport", "tcp", "-i", rtsp_url,
         "-an", "-c:v", "copy", "-f", fmt, "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0
    )


# ---------- Extract configParam ----------

def extract_config_param(ffmpeg, codec):
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
                        base64.b64encode(pps).decode()
                    ]), buf
            else:
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
                        base64.b64encode(pps).decode()
                    ]), buf


# ---------- Push Client ----------

class EdgePushClient:
    def __init__(self, cam, codec, camera_fps):
        self.cam = cam
        self.codec = codec
        self.camera_fps = camera_fps
        self.encode_type = ENCODE_TYPE_H265 if codec in ("hevc", "h265") else ENCODE_TYPE_H264

        self.sock = None
        self.out = None
        self.total_frames = 0
        self.interval_frames = 0
        self.lock = threading.Lock()
        self.stop_event = threading.Event()

        self._setup_compression()
        self.stats_thread = threading.Thread(target=self._stats, daemon=True)
        self.stats_thread.start()

    def _setup_compression(self):
        cfps = self.cam.get("compressedFps")

        if not cfps or cfps >= self.camera_fps:
            self.compress = False
            self.frame_gap = 1
        else:
            self.compress = True
            self.frame_gap = int(round(self.camera_fps / cfps))

        self.allow_chain = False
        self.p_count = 0

        log(f"[{self.cam['cameraId']}] cameraFPS={self.camera_fps}, "
            f"compressedFPS={cfps}, frameGap={self.frame_gap}, "
            f"compression={'ON' if self.compress else 'OFF'}")

    def connect(self, config_param):
        self.sock = socket.create_connection(
            (self.cam["pushHost"], self.cam["pushPort"]), timeout=10
        )
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.out = self.sock.makefile("wb")
        self._send_camera_config(config_param)

    def _send_camera_config(self, config_param):
        req = {
            "cameraId": self.cam["cameraId"],
            "width": self.cam["width"],
            "height": self.cam["height"],
            "configParam": config_param,
            "encoderType": self.encode_type,
            "extras": {"pushType": self.cam.get("pushType", "RAW_PUSH")}
        }

        body = (
            struct.pack(">B", PROXY_METADATA_COMMAND) +
            struct.pack(">B", PROXY_COMMAND_TYPE_CAMERA_CONFIG) +
            struct.pack(">I", 0) +
            json.dumps(req, separators=(",", ":")).encode()
        )
        self._send(body)

    def send_frame(self, nal):
        if not self.out:
            return

        is_idr = is_h265_idr(nal) if self.encode_type == ENCODE_TYPE_H265 else is_h264_idr(nal)

        if self.compress:
            if is_idr:
                self.allow_chain = True
                self.p_count = 0
            elif not self.allow_chain:
                return
            elif self.p_count >= self.frame_gap - 1:
                self.allow_chain = False
                return
            else:
                self.p_count += 1

        ts = int(time.time() * 1000)
        hdr = json.dumps({
            "cameraId": self.cam["cameraId"],
            "iframe": is_idr,
            "frameLength": len(nal),
            "captureTimeStamp": ts,
            "timeStamp": ts
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
            self.total_frames += 1
            self.interval_frames += 1

    def _send(self, body):
        try:
            self.out.write(struct.pack(">I", len(body)))
            self.out.write(body)
            self.out.flush()
        except Exception:
            self.out = None
            raise

    def _stats(self):
        last = time.time()
        while not self.stop_event.is_set():
            self.stop_event.wait(STATS_LOG_INTERVAL)
            if self.stop_event.is_set():
                break
            with self.lock:
                now = time.time()
                fps = self.interval_frames / (now - last) if now > last else 0.0
                log(f"[{self.cam['cameraId']}] pushed={fps:.2f}fps total={self.total_frames}")
                self.interval_frames = 0
                last = now

    def close(self):
        self.stop_event.set()
        try:
            if self.out:
                self.out.close()
            if self.sock:
                self.sock.close()
        except Exception:
            pass


# ---------- Camera Worker ----------

def camera_worker(cam):
    while True:
        try:
            codec, fps = detect_codec_and_fps(cam["rtspUrl"])
            log(f"[{cam['cameraId']}] codec={codec}, cameraFPS={fps}")

            ffmpeg = start_ffmpeg(cam["rtspUrl"], codec)
            cfg, rem = extract_config_param(ffmpeg, codec)

            reader = NalReader(ffmpeg.stdout)
            reader.buffer = rem

            client = EdgePushClient(cam, codec, fps)
            client.connect(cfg)

            log(f"[{cam['cameraId']}] Streaming started")

            while True:
                nal = reader.next_nal()
                if nal is None:
                    raise RuntimeError("Stream ended")
                client.send_frame(nal)

        except Exception as e:
            log(f"[{cam['cameraId']}] ERROR: {e}")
            traceback.print_exc()

        finally:
            try:
                client.close()
            except Exception:
                pass
            try:
                ffmpeg.kill()
            except Exception:
                pass

            log(f"[{cam['cameraId']}] Reconnecting in {RECONNECT_DELAY}s")
            time.sleep(RECONNECT_DELAY)


# ---------- MAIN ----------

def main():
    with open("edge_push_config.json") as f:
        cams = json.load(f)

    for cam in cams:
        threading.Thread(target=camera_worker, args=(cam,), daemon=True).start()

    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
