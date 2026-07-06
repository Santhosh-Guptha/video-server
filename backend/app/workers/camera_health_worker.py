import asyncio
from ..db import get_session
from ..registries.camera_registry import CameraRegistry
from ..registries.stream_registry import StreamRegistry
from ..camera_watchdog import _ffprobe_rtsp

async def camera_health_worker_loop():
    """Background worker that pings physical camera devices concurrently and updates health status."""
    print("[worker] Starting camera health worker loop...")
    await asyncio.sleep(10.0)

    while True:
        try:
            async for session in get_session():
                active_cameras = await CameraRegistry.get_active_cameras(session)
                
                # Concurrency throttle to avoid network/socket exhaustion
                sem = asyncio.Semaphore(40)
                
                async def check_camera_stream(stream_id, stream_url, current_status):
                    async with sem:
                        try:
                            # Lightweight TCP socket connection check
                            online = await _ffprobe_rtsp(stream_url, timeout_seconds=5)
                            status = "ONLINE" if online else "OFFLINE"
                            
                            if current_status != status:
                                # Open a separate DB session for the update to prevent task-sharing session errors
                                async for update_session in get_session():
                                    await StreamRegistry.update_stream_state(stream_id, status, None, update_session)
                                    break
                        except Exception as task_err:
                            print(f"[worker] Error checking stream {stream_id}: {task_err}")

                tasks = []
                for cam in active_cameras:
                    if cam.streams:
                        for stream in cam.streams:
                            tasks.append(check_camera_stream(stream.stream_id, stream.stream_url, stream.status))
                
                if tasks:
                    print(f"[worker] Camera health watchdog starting concurrent checks on {len(tasks)} streams...")
                    await asyncio.gather(*tasks, return_exceptions=True)
                    print(f"[worker] Camera health watchdog finished concurrent checks.")
                
                # break out of session generator
                break
                
        except Exception as e:
            print(f"[worker] Camera health worker error: {e}")

        await asyncio.sleep(120)
