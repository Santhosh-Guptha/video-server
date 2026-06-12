# Frontend UI

A polished React + Vite frontend for the camera video platform.

## Features
- sync cameras from backend
- camera dashboard with search
- live player using HLS.js
- start/stop live actions
- recording list
- playback list
- responsive dark UI with CSS

## Run
```bash
npm install
npm run dev -- --host 0.0.0.0
```

The app proxies `/api` and `/ws` to `localhost:8000`.
