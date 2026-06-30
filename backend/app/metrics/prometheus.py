import time
from fastapi import APIRouter, Response
from ..services.redis_viewer_tracker import RedisViewerTracker

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

# Simple in-memory structure to capture negotiation times and statistics
class MetricCollector:
    active_cameras = 0
    webrtc_negotiation_sum = 0.0
    webrtc_negotiation_count = 0
    ice_connection_sum = 0.0
    ice_connection_count = 0
    stream_reuse_count = 0
    stream_request_count = 0

metrics_collector = MetricCollector()

@router.get("")
async def prometheus_metrics():
    """Generates standard Prometheus text-based exporter output."""
    lines = []
    
    # 1. Active WebRTC viewer counts
    lines.append("# HELP vms_active_viewers Current count of active video streaming viewers.")
    lines.append("# TYPE vms_active_viewers gauge")
    
    # We can pull from database/Redis counts or memory fallbacks
    total_viewers = 0
    lines.append(f"vms_active_viewers {total_viewers}")
    
    # 2. Stream reuse ratio
    ratio = 0.0
    if metrics_collector.stream_request_count > 0:
        ratio = metrics_collector.stream_reuse_count / metrics_collector.stream_request_count
        
    lines.append("# HELP vms_stream_reuse_ratio Ratio of warm stream reuses to total requests.")
    lines.append("# TYPE vms_stream_reuse_ratio gauge")
    lines.append(f"vms_stream_reuse_ratio {round(ratio, 4)}")
    
    # 3. WebRTC average negotiation times
    avg_neg = 0.0
    if metrics_collector.webrtc_negotiation_count > 0:
        avg_neg = metrics_collector.webrtc_negotiation_sum / metrics_collector.webrtc_negotiation_count
        
    lines.append("# HELP vms_webrtc_negotiation_time_seconds Average WebRTC WHEP offer-answer negotiation time.")
    lines.append("# TYPE vms_webrtc_negotiation_time_seconds gauge")
    lines.append(f"vms_webrtc_negotiation_time_seconds {round(avg_neg, 4)}")

    return Response(content="\n".join(lines) + "\n", media_type="text/plain")
