import socket
import struct
import subprocess
import time
import json
import threading
import sys
import os
import re
import base64
import select

# ================= PROTOCOL CONSTANTS =================
PROXY_METADATA_COMMAND = 0x01
PROXY_METADATA_IMAGE = 0x02
PROXY_COMMAND_TYPE_CAMERA_CONFIG = 0x05
ENCODE_TYPE_H264 = 3

def log(msg):
    print(f"[WEBCAM-PUSH] {time.strftime('%H:%M:%S')} {msg}", flush=True)

# ---------- Discover Local Webcams ----------
def discover_devices():
    devices = []
    if sys.platform.startswith("win"):
        # Run FFmpeg to list DirectShow devices
        cmd = ["ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Parse output for video devices
        lines = proc.stderr.splitlines()
        log("Listing DirectShow devices:")
        for line in lines:
            if "DirectShow video devices" in line:
                continue
            # Look for lines containing "Alternative name" or names in quotes
            match = re.search(r'\"([^\"]+)\" \(video\)', line)
            if match:
                dev_name = match.group(1)
                devices.append(dev_name)
                log(f" Found Webcam: {dev_name}")
    elif sys.platform.startswith("linux"):
        # Check standard video devices under /dev/
        for i in range(10):
            path = f"/dev/video{i}"
            if os.path.exists(path):
                devices.append(path)
                log(f" Found Webcam: {path}")
    elif sys.platform == "darwin":
        # Run FFmpeg to list AVFoundation devices
        cmd = ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        lines = proc.stderr.splitlines()
        for line in lines:
            match = re.search(r'\[\d+\]\s+(.+)', line)
            if match:
                dev_name = match.group(1)
                devices.append(dev_name)
                log(f" Found Webcam: {dev_name}")
    return devices

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

# ---------- Extract H.264 SPS/PPS for configParam ----------
def extract_sps_pps(ffmpeg_stdout):
    sps = pps = None
    buf = b""
    while True:
        chunk = ffmpeg_stdout.read(4096)
        if not chunk:
            break
        buf += chunk
        while True:
            idx = buf.find(b"\x00\x00\x00\x01", 4)
            if idx == -1:
                break
            nal = buf[:idx]
            buf = buf[idx:]
            
            # Check H.264 NAL type
            nal_type = nal[4] & 0x1F
            if nal_type == 7:
                sps = nal
            elif nal_type == 8:
                pps = nal
            
            if sps and pps:
                config_str = ",".join([
                    base64.b64encode(sps).decode(),
                    base64.b64encode(pps).decode()
                ])
                return config_str, buf

# ---------- Push Client Connection ----------
class EdgePushClient:
    def __init__(self, host, port, camera_id):
        self.host = host
        self.port = port
        self.camera_id = camera_id
        self.sock = None
        self.out = None

    def connect(self, config_param):
        log(f"Connecting to VMS server at {self.host}:{self.port}...")
        self.sock = socket.create_connection((self.host, self.port), timeout=10)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.out = self.sock.makefile("wb")
        
        # Send Camera Configuration Meta Packet
        req = {
            "cameraId": self.camera_id,
            "width": 640,
            "height": 480,
            "configParam": config_param,
            "encoderType": ENCODE_TYPE_H264,
            "extras": {"pushType": "RAW_PUSH"}
        }
        body = (
            struct.pack(">B", PROXY_METADATA_COMMAND) +
            struct.pack(">B", PROXY_COMMAND_TYPE_CAMERA_CONFIG) +
            struct.pack(">I", 0) +
            json.dumps(req, separators=(",", ":")).encode()
        )
        self._send(body)
        log("Sent CAMERA_CONFIG metadata successfully.")

    def send_frame(self, nal):
        if not self.out:
            return
        
        nal_type = nal[4] & 0x1F
        is_idr = (nal_type == 5)
        
        ts = int(time.time() * 1000)
        hdr = json.dumps({
            "cameraId": self.camera_id,
            "iframe": is_idr,
            "frameLength": len(nal),
            "captureTimeStamp": ts,
            "timeStamp": ts
        }, separators=(",", ":")).encode()

        body = (
            struct.pack(">B", PROXY_METADATA_IMAGE) +
            struct.pack(">B", ENCODE_TYPE_H264) +
            struct.pack(">I", len(hdr)) +
            hdr +
            struct.pack(">I", len(nal)) +
            nal
        )
        self._send(body)

    def _send(self, body):
        try:
            self.out.write(struct.pack(">I", len(body)))
            self.out.write(body)
            self.out.flush()
        except Exception:
            self.out = None
            raise

    def close(self):
        try:
            if self.out:
                self.out.close()
            if self.sock:
                self.sock.close()
        except Exception:
            pass

def main():
    # Configure Server Target & Camera Name
    push_host = "172.20.100.235"
    push_port = 9999
    camera_id = "WEBCAM_CAMERA"

    # Ask user for values if running interactively
    print("--------------------------------------------------")
    print(f"Default VMS Host: {push_host}")
    print(f"Default Ingest Port: {push_port}")
    print(f"Default Camera ID: {camera_id}")
    print("--------------------------------------------------")
    user_host = input(f"Enter VMS Host IP [{push_host}]: ").strip()
    if user_host:
        push_host = user_host
    user_cam = input(f"Enter Camera ID [{camera_id}]: ").strip()
    if user_cam:
        camera_id = user_cam

    devices = discover_devices()
    if not devices:
        log("ERROR: No webcams detected! Make sure your webcam is plugged in and recognized.")
        sys.exit(1)

    selected_device = devices[0]
    log(f"Auto-selected Webcam: '{selected_device}'")

    # Start FFmpeg to capture webcam and encode to H.264
    if sys.platform.startswith("win"):
        # DirectShow input for Windows
        cmd = [
            "ffmpeg",
            "-f", "dshow",
            "-video_size", "640x480",
            "-framerate", "30",
            "-i", f"video={selected_device}",
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-f", "h264",
            "-"
        ]
    elif sys.platform.startswith("linux"):
        # V4L2 input for Linux
        cmd = [
            "ffmpeg",
            "-f", "v4l2",
            "-video_size", "640x480",
            "-framerate", "30",
            "-i", selected_device,
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-f", "h264",
            "-"
        ]
    else: # macOS
        cmd = [
            "ffmpeg",
            "-f", "avfoundation",
            "-video_size", "640x480",
            "-framerate", "30",
            "-i", f"{selected_device}:",
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-f", "h264",
            "-"
        ]

    log(f"Starting FFmpeg webcam capture command: {' '.join(cmd)}")
    try:
        ffmpeg_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0
        )
    except FileNotFoundError:
        log("ERROR: FFmpeg command not found! Please download and install FFmpeg and add it to your PATH.")
        sys.exit(1)

    try:
        # Extract SPS/PPS
        log("Analyzing webcam stream for SPS/PPS parameters...")
        config_param, remaining_buf = extract_sps_pps(ffmpeg_proc.stdout)
        log(f"Extracted config parameters: {config_param[:30]}...")

        # Initialize NalReader and feed remaining buffer
        reader = NalReader(ffmpeg_proc.stdout)
        reader.buffer = remaining_buf

        # Connect and Push
        client = EdgePushClient(push_host, push_port, camera_id)
        client.connect(config_param)

        log("Pushing webcam video. Press Ctrl+C to stop.")
        frame_cnt = 0
        while True:
            nal = reader.next_nal()
            if nal is None:
                raise RuntimeError("Webcam video input ended.")
            
            client.send_frame(nal)
            frame_cnt += 1
            if frame_cnt % 30 == 0:
                log(f"Webcam frames pushed: {frame_cnt}")

    except KeyboardInterrupt:
        log("Webcam push client stopped by user.")
    except Exception as e:
        log(f"Error during streaming: {e}")
    finally:
        try:
            client.close()
        except:
            pass
        try:
            ffmpeg_proc.terminate()
            ffmpeg_proc.wait(timeout=2)
        except:
            pass
        log("Stopped webcam push.")

if __name__ == "__main__":
    main()
