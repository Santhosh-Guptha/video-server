import asyncio
from ..redis_client import redis_client

async def redis_health_worker_loop():
    """Background worker that monitors Redis cache availability and latency."""
    print("[worker] Starting Redis health worker loop...")
    await asyncio.sleep(10.0)

    while True:
        try:
            if redis_client:
                # Run a fast ping request
                await redis_client.ping()
                print("[worker] Redis Cache Health: HEALTHY")
            else:
                print("[worker] Redis Cache Health: IN-MEMORY FALLBACK MODE ACTIVE")
        except Exception as e:
            print(f"[worker] Redis Cache Health: ERROR ({e})")

        await asyncio.sleep(30)
