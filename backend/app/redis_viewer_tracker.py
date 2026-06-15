import json
from .redis_client import RedisManager, redis_client

class RedisViewerTracker:
    # Local fallback dictionary matching Redis key structure
    _memory_viewers = {}
    _memory_health = {}

    @staticmethod
    async def add_viewer_session(stream_id: str, session_id: str, session_details: dict) -> int:
        """Adds a session to the stream's active viewers list and stores details."""
        details_serialized = json.dumps(session_details)
        
        # 1. Cache session details
        sess_key = f"vms:sessions:{session_id}"
        viewers_key = f"vms:viewers:{stream_id}"
        
        if redis_client:
            try:
                await redis_client.set(sess_key, details_serialized)
                await redis_client.sadd(viewers_key, session_id)
                count = await redis_client.scard(viewers_key)
                # Sync total count to stream state as well
                await RedisManager.set_viewer_count(stream_id, count)
                return count
            except Exception as e:
                print(f"[viewer_tracker] Redis error adding session: {e}. Falling back to memory.")
                
        # In-memory fallback
        RedisViewerTracker._memory_viewers.setdefault(sess_key, details_serialized)
        viewers_set = RedisViewerTracker._memory_viewers.setdefault(viewers_key, set())
        viewers_set.add(session_id)
        count = len(viewers_set)
        await RedisManager.set_viewer_count(stream_id, count)
        return count

    @staticmethod
    async def remove_viewer_session(stream_id: str, session_id: str) -> int:
        """Removes a session from the active viewers list."""
        sess_key = f"vms:sessions:{session_id}"
        viewers_key = f"vms:viewers:{stream_id}"
        
        if redis_client:
            try:
                await redis_client.delete(sess_key)
                await redis_client.srem(viewers_key, session_id)
                count = await redis_client.scard(viewers_key)
                await RedisManager.set_viewer_count(stream_id, count)
                return count
            except Exception as e:
                print(f"[viewer_tracker] Redis error removing session: {e}. Falling back to memory.")
                
        # In-memory fallback
        RedisViewerTracker._memory_viewers.pop(sess_key, None)
        viewers_set = RedisViewerTracker._memory_viewers.get(viewers_key, set())
        viewers_set.discard(session_id)
        count = len(viewers_set)
        await RedisManager.set_viewer_count(stream_id, count)
        return count

    @staticmethod
    async def get_viewer_count(stream_id: str) -> int:
        """Returns the number of active viewers on a stream."""
        viewers_key = f"vms:viewers:{stream_id}"
        if redis_client:
            try:
                return await redis_client.scard(viewers_key)
            except Exception:
                pass
        return len(RedisViewerTracker._memory_viewers.get(viewers_key, set()))

    @staticmethod
    async def get_active_sessions(stream_id: str) -> list[str]:
        """Returns list of active session IDs on a stream."""
        viewers_key = f"vms:viewers:{stream_id}"
        if redis_client:
            try:
                members = await redis_client.smembers(viewers_key)
                return list(members) if members else []
            except Exception:
                pass
        return list(RedisViewerTracker._memory_viewers.get(viewers_key, set()))

    @staticmethod
    async def set_stream_health(stream_id: str, status: str, error_message: str | None = None):
        """Caches active stream health metrics."""
        health_key = f"vms:stream-health:{stream_id}"
        payload = {
            "status": status,
            "error_message": error_message,
            "timestamp": datetime_now_iso()
        }
        serialized = json.dumps(payload)
        if redis_client:
            try:
                await redis_client.set(health_key, serialized)
                return
            except Exception:
                pass
        RedisViewerTracker._memory_health[health_key] = serialized

    @staticmethod
    async def get_stream_health(stream_id: str) -> dict:
        """Reads stream health state from cache."""
        health_key = f"vms:stream-health:{stream_id}"
        data = None
        if redis_client:
            try:
                data = await redis_client.get(health_key)
            except Exception:
                pass
        if not data:
            data = RedisViewerTracker._memory_health.get(health_key)
            
        if data:
            return json.loads(data)
        return {"status": "REGISTERED", "error_message": None, "timestamp": datetime_now_iso()}

def datetime_now_iso() -> str:
    from datetime import datetime
    return datetime.utcnow().isoformat()
