# Camera Video Platform Full Stack

This project includes:
- Backend: FastAPI + SQLite + FFmpeg
- Frontend: React + Vite
- Integration with `/api/cameras/camera-videoserver`
- Live view via HLS
- Recording metadata and playback listing
- WebSocket status channel

## Quick start

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open:
- http://localhost:5173

## Notes
- If the upstream camera API is unreachable, the backend falls back to sample camera data.
- For real camera live view, FFmpeg must be installed and the RTSP URLs must be reachable from the backend host.
