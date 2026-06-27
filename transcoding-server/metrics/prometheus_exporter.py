from prometheus_client import Gauge, make_asgi_app
import asyncio
from scheduler.gpu_scheduler import GPUScheduler
from workers.ffmpeg_worker import TranscodingWorkerPool

# Define Prometheus metrics
ACTIVE_TRANSCODERS = Gauge(
    "vms_active_transcoders_count",
    "Total number of active transcoding FFmpeg worker processes",
    ["pool_type"]
)

GPU_UTILIZATION = Gauge(
    "vms_gpu_utilization_percent",
    "GPU hardware core utilization percentage",
    ["gpu_index"]
)

GPU_VRAM_USED = Gauge(
    "vms_gpu_vram_used_megabytes",
    "GPU memory VRAM usage in megabytes",
    ["gpu_index"]
)

GPU_TEMPERATURE = Gauge(
    "vms_gpu_temperature_celsius",
    "GPU core temperature in degrees Celsius",
    ["gpu_index"]
)

ACTIVE_VIEWERS = Gauge(
    "vms_active_transcoded_viewers",
    "Total number of connected viewers consuming transcoded streams",
    ["pool_type"]
)

async def update_prometheus_metrics():
    """Background task to periodically synchronize internal metrics with Prometheus Gauges."""
    while True:
        try:
            # 1. Update GPU stats
            gpu_status = await GPUScheduler.get_cluster_status()
            for gpu in gpu_status:
                idx = str(gpu["gpu_index"])
                GPU_UTILIZATION.labels(gpu_index=idx).set(gpu["utilization_pct"])
                GPU_VRAM_USED.labels(gpu_index=idx).set(gpu["used_vram_mb"])
                GPU_TEMPERATURE.labels(gpu_index=idx).set(gpu["temperature_c"])

            # 2. Update Workers stats
            worker_status = await TranscodingWorkerPool.get_worker_status()
            
            # Live pool
            ACTIVE_TRANSCODERS.labels(pool_type="live").set(worker_status["live_worker_count"])
            total_live_viewers = sum(s["viewers"] for s in worker_status["live_active_sessions"])
            ACTIVE_VIEWERS.labels(pool_type="live").set(total_live_viewers)

            # Playback pool
            ACTIVE_TRANSCODERS.labels(pool_type="playback").set(worker_status["playback_worker_count"])
            total_playback_viewers = sum(s["viewers"] for s in worker_status["playback_active_sessions"])
            ACTIVE_VIEWERS.labels(pool_type="playback").set(total_playback_viewers)

        except Exception as e:
            print(f"[metrics] Error updating prometheus gauges: {e}")

        await asyncio.sleep(5)

# Create ASGI app for scraping metrics
metrics_app = make_asgi_app()
