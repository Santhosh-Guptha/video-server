import json
import redis.asyncio as aioredis
from .config import settings

# Initialize redis connection pool with graceful offline fallback
try:
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
except Exception as e:
    print(f"[redis] Failed to initialize Redis connection pool: {e}. Falling back to in-memory store.")
    redis_client = None

class RedisManager:
    # Class-level in-memory fallback dictionary
    _memory_cache = {}

    @staticmethod
    async def get_stream_state(stream_id: str) -> dict | None:
        if redis_client:
            try:
                data = await redis_client.get(f"vms:stream:state:{stream_id}")
                if data:
                    return json.loads(data)
            except Exception as e:
                print(f"[redis] Connection error getting state: {e}. Reading from memory cache.")
        
        # In-memory fallback
        data = RedisManager._memory_cache.get(f"vms:stream:state:{stream_id}")
        return json.loads(data) if data else None

    @staticmethod
    async def set_stream_state(stream_id: str, state: str, error_message: str | None = None) -> None:
        payload = {
            "status": state,
            "error_message": error_message,
            "updated_at": datetime_now_iso()
        }
        serialized = json.dumps(payload)
        
        if redis_client:
            try:
                await redis_client.set(f"vms:stream:state:{stream_id}", serialized)
                return
            except Exception as e:
                print(f"[redis] Connection error setting state: {e}. Writing to memory cache.")
                
        # In-memory fallback
        RedisManager._memory_cache[f"vms:stream:state:{stream_id}"] = serialized

    @staticmethod
    async def get_viewer_count(stream_id: str) -> int:
        if redis_client:
            try:
                count = await redis_client.get(f"vms:stream:viewers:{stream_id}")
                return int(count) if count else 0
            except Exception as e:
                print(f"[redis] Connection error getting viewer count: {e}. Reading from memory cache.")
                
        return int(RedisManager._memory_cache.get(f"vms:stream:viewers:{stream_id}", 0))

    @staticmethod
    async def set_viewer_count(stream_id: str, count: int) -> None:
        if redis_client:
            try:
                await redis_client.set(f"vms:stream:viewers:{stream_id}", count)
                return
            except Exception as e:
                print(f"[redis] Connection error setting viewer count: {e}. Writing to memory cache.")
                
        RedisManager._memory_cache[f"vms:stream:viewers:{stream_id}"] = str(count)

    @staticmethod
    async def acquire_lock(lock_name: str, expire_seconds: int = 10) -> bool:
        if redis_client:
            try:
                return bool(await redis_client.set(f"vms:lock:{lock_name}", "1", ex=expire_seconds, nx=True))
            except Exception as e:
                print(f"[redis] Connection error acquiring lock: {e}. Approving lock locally.")
                
        lock_key = f"vms:lock:{lock_name}"
        if lock_key in RedisManager._memory_cache:
            return False
        RedisManager._memory_cache[lock_key] = "1"
        return True

    @staticmethod
    async def release_lock(lock_name: str) -> None:
        if redis_client:
            try:
                await redis_client.delete(f"vms:lock:{lock_name}")
                return
            except Exception as e:
                print(f"[redis] Connection error releasing lock: {e}. Releasing lock locally.")
                
        RedisManager._memory_cache.pop(f"vms:lock:{lock_name}", None)

    @staticmethod
    async def increment_counter(name: str) -> int:
        if redis_client:
            try:
                return await redis_client.incr(f"vms:counter:{name}")
            except Exception as e:
                print(f"[redis] Connection error incrementing counter: {e}. Writing to memory cache.")
        
        current = int(RedisManager._memory_cache.get(f"vms:counter:{name}", 0))
        new_val = current + 1
        RedisManager._memory_cache[f"vms:counter:{name}"] = str(new_val)
        return new_val

    @staticmethod
    async def get_counter(name: str) -> int:
        if redis_client:
            try:
                val = await redis_client.get(f"vms:counter:{name}")
                return int(val) if val else 0
            except Exception as e:
                print(f"[redis] Connection error getting counter: {e}. Reading from memory cache.")
                
        return int(RedisManager._memory_cache.get(f"vms:counter:{name}", 0))

    @staticmethod
    async def get_last_push_seen(stream_id: str) -> float | None:
        if redis_client:
            try:
                val = await redis_client.get(f"vms:last_push_seen:{stream_id}")
                return float(val) if val else None
            except Exception:
                pass
        val = RedisManager._memory_cache.get(f"vms:last_push_seen:{stream_id}")
        return float(val) if val else None

    @staticmethod
    async def set_last_push_seen(stream_id: str, timestamp: float) -> None:
        if redis_client:
            try:
                await redis_client.set(f"vms:last_push_seen:{stream_id}", str(timestamp))
                return
            except Exception:
                pass
        RedisManager._memory_cache[f"vms:last_push_seen:{stream_id}"] = str(timestamp)

    @staticmethod
    async def clear_last_push_seen(stream_id: str) -> None:
        if redis_client:
            try:
                await redis_client.delete(f"vms:last_push_seen:{stream_id}")
                return
            except Exception:
                pass
        RedisManager._memory_cache.pop(f"vms:last_push_seen:{stream_id}", None)

def datetime_now_iso() -> str:
    from datetime import datetime
    return datetime.utcnow().isoformat()
