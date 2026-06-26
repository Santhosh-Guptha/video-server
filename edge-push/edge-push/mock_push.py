import socket
import struct
import json
import time
import sys

def log(msg):
    print(f"[MOCK] {time.strftime('%H:%M:%S')} {msg}", flush=True)

def main():
    push_host = "127.0.0.1"
    push_port = 9999
    camera_id = "EDGE_CAM_01"
    
    # 1. CAMERA_CONFIG packet
    req = {
        "cameraId": camera_id,
        "width": 640,
        "height": 360,
        "configParam": "AAAAAXNwc19kYXRhAAAAAXBwc19kYXRh",  # dummy SPS/PPS base64 bytes
        "encoderType": 3,  # H264
        "extras": {"pushType": "RAW_PUSH"}
    }
    
    body = (
        struct.pack(">B", 0x01) +      # PROXY_METADATA_COMMAND
        struct.pack(">B", 0x05) +      # PROXY_COMMAND_TYPE_CAMERA_CONFIG
        struct.pack(">I", 0) +         # unused padding
        json.dumps(req, separators=(",", ":")).encode()
    )
    
    log(f"Connecting to TCP Edge Push Ingest Server at {push_host}:{push_port}...")
    try:
        sock = socket.create_connection((push_host, push_port), timeout=10)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception as e:
        log(f"Connection failed: {e}")
        sys.exit(1)
        
    sock.sendall(struct.pack(">I", len(body)) + body)
    log("Sent CAMERA_CONFIG packet.")
    
    # 2. Send Simulated NAL Video Frame units
    frame_count = 0
    dummy_nal = b"\x00\x00\x00\x01\x27\x42\xe0\x0d\xa9\x18\x28\x3f\x60\x0d\x80"  # Dummy Annex B NAL unit
    
    try:
        log("Starting simulated frame push loop. Press Ctrl+C to terminate...")
        while True:
            is_idr = (frame_count % 30 == 0)  # IDR keyframe every 30 frames
            ts = int(time.time() * 1000)
            
            hdr = json.dumps({
                "cameraId": camera_id,
                "iframe": is_idr,
                "frameLength": len(dummy_nal),
                "captureTimeStamp": ts,
                "timeStamp": ts
            }, separators=(",", ":")).encode()
            
            body = (
                struct.pack(">B", 0x02) +    # PROXY_METADATA_IMAGE
                struct.pack(">B", 3) +       # H264
                struct.pack(">I", len(hdr)) +
                hdr +
                struct.pack(">I", len(dummy_nal)) +
                dummy_nal
            )
            
            sock.sendall(struct.pack(">I", len(body)) + body)
            frame_count += 1
            if frame_count % 30 == 0:
                log(f"Simulated frames pushed: {frame_count}")
                
            time.sleep(0.066)  # ~15 FPS
            
    except KeyboardInterrupt:
        log("Mock push client stopped by user.")
    except Exception as e:
        log(f"Socket transmission error: {e}")
    finally:
        sock.close()
        log("Closed socket connection.")

if __name__ == "__main__":
    main()
