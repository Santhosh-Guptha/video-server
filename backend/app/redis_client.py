import json
import redis.asyncio as aioredis
from .config import settings

# Initialize redis connection pool
redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

class RedisManager:
    @staticmethod
    async def get_stream_state(stream_id: str) -> dict | None:
        try:
            data = await redis_client.get(f"vms:stream:state:{stream_id}")
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"[redis] Error getting stream state for {stream_id}: {e}")
        return None

    @staticmethod
    async def set_stream_state(stream_id: str, state: str, error_message: str | None = None) -> None:
        try:
            payload = {
                "status": state,
                "error_message": error_message,
                "updated_at": datetime_now_iso()
            }
            await redis_client.set(f"vms:stream:state:{stream_id}", json.dumps(payload))
        except Exception as e:
            print(f"[redis] Error setting stream state for {stream_id}: {e}")

    @staticmethod
    async def get_viewer_count(stream_id: str) -> int:
        try:
            count = await redis_client.get(f"vms:stream:viewers:{stream_id}")
            return int(count) if count else 0
        except Exception as e:
            print(f"[redis] Error getting viewer count for {stream_id}: {e}")
        return 0

    @staticmethod
    async def set_viewer_count(stream_id: str, count: int) -> None:
        try:
            await redis_client.set(f"vms:stream:viewers:{stream_id}", count)
        except Exception as e:
            print(f"[redis] Error setting viewer count for {stream_id}: {e}")

    @staticmethod
    async def acquire_lock(lock_name: str, expire_seconds: int = 10) -> bool:
        try:
            # Set key if not exists (NX) with expiration (EX)
            return bool(await redis_client.set(f"vms:lock:{lock_name}", "1", ex=expire_seconds, nx=True))
        except Exception as e:
            print(f"[redis] Error acquiring lock {lock_name}: {e}")
        return False

    @staticmethod
    async def release_lock(lock_name: str) -> None:
        try:
            await redis_client.delete(f"vms:lock:{lock_name}")
        except Exception as e:
            print(f"[redis] Error releasing lock {lock_name}: {e}")

def datetime_now_iso() -> str:
    from datetime import datetime
    return datetime.utcnow().isoformat()
