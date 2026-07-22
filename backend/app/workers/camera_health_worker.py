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
            active_streams = []
            async for session in get_session():
                active_cameras = await CameraRegistry.get_active_cameras(session)
                for cam in active_cameras:
                    if cam.streams:
                        for stream in cam.streams:
                            active_streams.append({
                                "stream_id": stream.stream_id,
                                "stream_url": stream.stream_url,
                                "status": stream.status
                            })
                break

            # Concurrency throttle for TCP socket probes
            sem = asyncio.Semaphore(50)
            
            async def check_camera_stream(stream_id, stream_url):
                async with sem:
                    try:
                        # Use a 4-second timeout to handle high-latency routes safely
                        online = await _ffprobe_rtsp(stream_url, timeout_seconds=4)
                        return stream_id, "ONLINE" if online else "OFFLINE"
                    except Exception:
                        return stream_id, "OFFLINE"

            tasks = []
            stream_status_map = {}
            for s_info in active_streams:
                tasks.append(check_camera_stream(s_info["stream_id"], s_info["stream_url"]))
                stream_status_map[s_info["stream_id"]] = s_info["status"]
            
            if tasks:
                print(f"[worker] Camera health watchdog starting concurrent probes on {len(tasks)} streams...")
                results = await asyncio.gather(*tasks, return_exceptions=True)
                print(f"[worker] Camera health watchdog completed concurrent probes.")
                
                # Open a new session to apply updates
                async for session in get_session():
                    updates_count = 0
                    print(f"[worker] Sample results from watchdog: {results[:5]}")
                    for res in results:
                        if isinstance(res, tuple):
                            stream_id, status = res
                            old_status = stream_status_map.get(stream_id)
                            old_status_str = old_status.value if hasattr(old_status, "value") else str(old_status)
                            if old_status_str != status:
                                await StreamRegistry.update_stream_state(stream_id, status, None, session)
                                updates_count += 1
                                
                    if updates_count > 0:
                        await session.commit()
                        print(f"[worker] Camera health watchdog updated status for {updates_count} streams.")
                    else:
                        print("[worker] Camera health watchdog completed with 0 updates.")
                    break
                
        except Exception as e:
            print(f"[worker] Camera health worker error: {e}")

        await asyncio.sleep(120)
