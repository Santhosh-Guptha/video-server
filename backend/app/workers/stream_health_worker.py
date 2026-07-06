import asyncio
from sqlalchemy import select
from ..db import get_session
from ..models import CameraStream, StreamState
from ..registries.stream_registry import StreamRegistry
from ..stream_manager import stream_manager
from ..redis_client import RedisManager

async def stream_health_worker_loop():
    """Background worker that monitors MediaMTX stream status and transitions pipeline state."""
    print("[worker] Starting stream health worker loop...")
    await asyncio.sleep(5.0)

    while True:
        try:
            async for session in get_session():
                # Query all active streams
                stmt = select(CameraStream)
                res = await session.execute(stmt)
                streams = res.scalars().all()

                # Get path lists from MediaMTX
                try:
                    resp = await stream_manager._get("/v3/paths/list?page=0&itemsPerPage=10000")
                    if resp.status_code == 200:
                        items = resp.json().get("items", [])
                        paths_info = {item.get("name"): item for item in items if isinstance(item, dict) and "name" in item}
                    else:
                        paths_info = {}
                except Exception as e:
                    print(f"[worker] Stream health failed to query MediaMTX status: {e}")
                    paths_info = {}

                for s in streams:
                    info = paths_info.get(s.stream_id)
                    ready = info and info.get("ready") is True
                    
                    if ready:
                        # Stream is active and publishing
                        readers = info.get("readers", [])
                        # Filter out internal HLS muxer
                        active_readers = [r for r in readers if isinstance(r, dict) and r.get("type") != "hlsMuxer"] if isinstance(readers, list) else []
                        clients_count = len(active_readers)
                        
                        await RedisManager.set_viewer_count(s.stream_id, clients_count)
                        
                        target_state = "ONLINE"
                        if clients_count == 0:
                            # Warm grace state
                            target_state = "WARM"
                            
                        if s.status != target_state:
                            await StreamRegistry.update_stream_state(s.stream_id, target_state, None, session)
                    else:
                        # Stream configured but not publishing (connecting or offline)
                        viewer_count = await RedisManager.get_viewer_count(s.stream_id)
                        is_expected_active = s.always_on or (viewer_count > 0)
                        
                        if is_expected_active:
                            target_state = "CONNECTING" if s.status == "ONLINE" else "OFFLINE"
                            if s.status != target_state:
                                await StreamRegistry.update_stream_state(s.stream_id, target_state, "Source disconnected", session)
                        else:
                            # Stream is idle (no active viewers and not always_on).
                            # If it was left in WARM or CONNECTING, reset it to ONLINE so the camera stays healthy.
                            if s.status in ("WARM", "CONNECTING"):
                                await StreamRegistry.update_stream_state(s.stream_id, "ONLINE", None, session)

        except Exception as e:
            print(f"[worker] Stream health worker error: {e}")

        await asyncio.sleep(10)
