import asyncio
from ..db import get_session
from ..registries.camera_registry import CameraRegistry
from ..registries.stream_registry import StreamRegistry
from ..camera_watchdog import _ffprobe_rtsp

async def camera_health_worker_loop():
    """Background worker that pings physical camera devices and updates health status."""
    print("[worker] Starting camera health worker loop...")
    await asyncio.sleep(10.0)

    while True:
        try:
            async for session in get_session():
                active_cameras = await CameraRegistry.get_active_cameras(session)
                for cam in active_cameras:
                    # Perform simple ONVIF or network reachability check
                    online = False
                    if cam.streams:
                        # Probe the first stream RTSP port
                        stream = cam.streams[0]
                        rtsp_url = stream.stream_url
                        online = await _ffprobe_rtsp(rtsp_url, timeout_seconds=3)
                    
                        status = "ONLINE" if online else "OFFLINE"
                        if stream.status != status:
                            await StreamRegistry.update_stream_state(stream.stream_id, status, None, session)
        except Exception as e:
            print(f"[worker] Camera health worker error: {e}")

        await asyncio.sleep(120)
