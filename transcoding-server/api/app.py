import time
import asyncio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router
from metrics.prometheus_exporter import metrics_app, update_prometheus_metrics

app = FastAPI(
    title="Hybrid Codec-Aware VMS Transcoding Platform",
    description="Distributed High-Performance H.265 Transcoding Gateway",
    version="1.0.0"
)

# Enable CORS for frontend API dashboard checks
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the api routing definitions
app.include_router(router)

# Mount the Prometheus ASGI metrics page
app.mount("/metrics", metrics_app)

@app.on_event("startup")
async def startup_event():
    print("[app] Transcoding Server starting up...")
    # Warm up GPUScheduler metrics
    from scheduler.gpu_scheduler import GPUScheduler
    await GPUScheduler.update_metrics()
    
    # Run the background metrics update loop
    asyncio.create_task(update_prometheus_metrics())
    print("[app] GPU metrics and Prometheus gauges loop started.")

@app.on_event("shutdown")
async def shutdown_event():
    print("[app] Transcoding Server shutting down... cleaning up active processes...")
    from workers.ffmpeg_worker import TranscodingWorkerPool
    # Kill all running FFmpeg child processes on clean shutdown
    live_sessions = TranscodingWorkerPool._live_pool
    playback_sessions = TranscodingWorkerPool._playback_pool
    
    for stream_id, state in list(live_sessions.items()):
        try:
            state.process.kill()
        except:
            pass
            
    for session_key, state in list(playback_sessions.items()):
        try:
            state.process.kill()
        except:
            pass
            
    print("[app] Cleanup complete.")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    print(f"[http] {request.method} {request.url.path} finished in {duration:.4f}s with status {response.status_code}")
    return response
