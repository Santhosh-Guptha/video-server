import asyncio
from ..stream_manager import stream_manager

async def mediamtx_health_worker_loop():
    """Background worker that monitors MediaMTX HTTP API reachability."""
    print("[worker] Starting MediaMTX health worker loop...")
    await asyncio.sleep(10.0)

    while True:
        try:
            resp = await stream_manager._get("/v3/config/paths/list?page=0&itemsPerPage=1", timeout=5.0)
            status = "HEALTHY" if resp.status_code == 200 else "DEGRADED"
            print(f"[worker] MediaMTX API Health: {status} (status: {resp.status_code})")
        except Exception as e:
            print(f"[worker] MediaMTX API Health: UNREACHABLE ({e})")

        await asyncio.sleep(30)
