# Backend

## Run locally
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## What it does
- Syncs camera list from `/api/cameras/camera-videoserver`
- Stores normalized camera metadata in SQLite
- Starts RTSP live ingest with FFmpeg
- Exposes HLS live endpoint
- Exposes playback index endpoint
- Provides WebSocket status updates
