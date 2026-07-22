import sys
import json
import urllib.request
import urllib.error
import os
import re
import subprocess
from datetime import datetime, timedelta

def get_file_duration(path):
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        if res.returncode == 0:
            return float(res.stdout.strip())
    except Exception:
        pass
    return 60.0

def main():
    if len(sys.argv) < 3:
        print("Usage: python -m app.record_complete <stream_id> <file_path>")
        sys.exit(1)

    stream_id = sys.argv[1]
    file_path = sys.argv[2]

    if not stream_id or not file_path:
        print("Error: stream_id and file_path must be non-empty.")
        sys.exit(1)

    # Resolve filename and directory
    dir_name = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)

    # Check if the filename matches single-timestamp format: YYYYMMDD_HHMMSS_live.mp4
    # We want to rename it to YYYYMMDD_HHMMSS_HHMMSS_live.mp4
    match = re.search(r"^(\d{8})_(\d{6})_live\.mp4$", base_name)
    if match:
        date_str, time_str = match.groups()
        try:
            start_dt = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
            duration = get_file_duration(file_path)
            end_dt = start_dt + timedelta(seconds=round(duration))
            end_time_str = end_dt.strftime("%H%M%S")
            
            new_base_name = f"{date_str}_{time_str}_{end_time_str}_live.mp4"
            new_file_path = os.path.join(dir_name, new_base_name)
            
            os.rename(file_path, new_file_path)
            file_path = new_file_path
            print(f"[record_complete] Renamed {base_name} -> {new_base_name}")
        except Exception as rename_err:
            print(f"[record_complete] Rename failed: {rename_err}")

    # Prepare webhook payload
    payload = {
        "stream_id": stream_id,
        "file_path": file_path
    }
    data = json.dumps(payload).encode('utf-8')

    backend_url = os.environ.get("BACKEND_WEBHOOK_URL", "http://localhost:8005")
    url = f"{backend_url.rstrip('/')}/api/recordings/segment-complete"

    req = urllib.request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            status = response.getcode()
            body = response.read().decode('utf-8')
            print(f"[record_complete] Webhook success: Status {status}, Response: {body}")
    except urllib.error.URLError as e:
        print(f"[record_complete] Webhook failed to connect to {url}: {e}")
        sys.exit(0)
    except Exception as e:
        print(f"[record_complete] Webhook error: {e}")
        sys.exit(0)

if __name__ == "__main__":
    main()
