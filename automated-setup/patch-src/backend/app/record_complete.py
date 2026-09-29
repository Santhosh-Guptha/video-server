import sys
import json
import urllib.request
import urllib.error
import os

def main():
    if len(sys.argv) < 3:
        print("Usage: python -m app.record_complete <stream_id> <file_path>")
        sys.exit(1)

    stream_id = sys.argv[1]
    file_path = sys.argv[2]

    if not stream_id or not file_path:
        print("Error: stream_id and file_path must be non-empty.")
        sys.exit(1)

    # The backend owns duration probing, naming and indexing. Probing here
    # too doubles ffprobe work and creates competing names for one segment.

    # Prepare webhook payload
    payload = {
        "stream_id": stream_id,
        "file_path": file_path
    }
    data = json.dumps(payload).encode('utf-8')

    backend_url = os.environ.get("BACKEND_WEBHOOK_URL", "http://localhost:8006")
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
