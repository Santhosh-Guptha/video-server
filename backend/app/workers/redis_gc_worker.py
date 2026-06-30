import asyncio
from ..redis_client import redis_client

async def redis_gc_worker_loop():
    """Background worker that periodically removes expired locks and stale registry keys from Redis."""
    print("[worker] Starting Redis GC worker loop...")
    await asyncio.sleep(30.0)

    while True:
        try:
            if redis_client:
                # Find and delete any leftover stale keys or locks
                keys = await redis_client.keys("vms:lock:*")
                for key in keys:
                    # Let Redis naturally expire them or check TTL
                    ttl = await redis_client.ttl(key)
                    if ttl <= 0:
                        await redis_client.delete(key)
                        print(f"[worker] Redis GC: Cleared expired lock key {key}")
        except Exception as e:
            print(f"[worker] Redis GC worker error: {e}")

        await asyncio.sleep(60)
