import asyncio
from sqlalchemy import select
from ..db import get_session
from ..models import CameraStream, Camera
from ..registries.camera_registry import CameraRegistry
from ..config import settings

async def camera_sync_worker_loop():
    """Background worker that periodically ensures active camera paths are configured in MediaMTX."""
    print("[worker] Starting camera configuration sync worker loop...")
    await asyncio.sleep(5.0)

    while True:
        try:
            async for db_session in get_session():
                # 1. Fetch active camera streams from DB
                active_cams = await CameraRegistry.get_active_cameras(db_session)
                active_cams_ids = {c.id for c in active_cams}
                
                stmt = select(CameraStream).where(CameraStream.camera_id.in_(active_cams_ids))
                res = await db_session.execute(stmt)
                active_streams = res.scalars().all()
                active_stream_ids = {s.stream_id for s in active_streams}

                # 2. Get existing configuration paths in MediaMTX
                from ..stream_manager import stream_manager
                try:
                    paths_resp = await stream_manager._get("/v3/config/paths/list?page=0&itemsPerPage=10000")
                    if paths_resp.status_code == 200:
                        items = paths_resp.json().get("items", [])
                        mediamtx_paths = {item.get("name") for item in items if isinstance(item, dict) and "name" in item}
                    else:
                        mediamtx_paths = set()
                except Exception as e:
                    print(f"[worker] Camera sync failed to query MediaMTX paths: {e}")
                    mediamtx_paths = set()

                # Add missing paths permanently (with sourceOnDemand: true)
                for stream in active_streams:
                    if stream.stream_id not in mediamtx_paths:
                        print(f"[worker] Registering missing camera path permanently: {stream.stream_id}")
                        await stream_manager.add_stream(db_session, stream)

                # Remove deactivated/deleted paths
                for path in mediamtx_paths:
                    if path != "all_others" and not path.endswith("_h264") and path not in active_stream_ids:
                        print(f"[worker] De-registering decommissioned camera path: {path}")
                        try:
                            await stream_manager._delete(f"/v3/config/paths/delete/{path}")
                        except Exception as e:
                            print(f"[worker] Failed to delete path configuration {path}: {e}")

        except Exception as e:
            print(f"[worker] Camera sync worker error: {e}")

        await asyncio.sleep(10)
