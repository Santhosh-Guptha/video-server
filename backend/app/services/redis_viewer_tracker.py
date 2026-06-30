import json
from ..redis_client import RedisManager, redis_client

class RedisViewerTracker:
    # Fallback storage for when Redis connection is down
    _memory_viewers = {}
    _memory_counts = {}

    ADD_SESSION_LUA = """
    local viewers_set = KEYS[1]
    local count_key = KEYS[2]
    local session_id = ARGV[1]
    
    if redis.call("SISMEMBER", viewers_set, session_id) == 0 then
        redis.call("SADD", viewers_set, session_id)
        local count = redis.call("INCR", count_key)
        return count
    else
        local val = redis.call("GET", count_key)
        return val and tonumber(val) or 0
    end
    """

    REMOVE_SESSION_LUA = """
    local viewers_set = KEYS[1]
    local count_key = KEYS[2]
    local session_id = ARGV[1]
    
    if redis.call("SISMEMBER", viewers_set, session_id) == 1 then
        redis.call("SREM", viewers_set, session_id)
        local new_count = redis.call("DECR", count_key)
        if new_count < 0 then
            redis.call("SET", count_key, 0)
            new_count = 0
        end
        return new_count
    else
        local val = redis.call("GET", count_key)
        return val and tonumber(val) or 0
    end
    """

    @classmethod
    async def add_viewer_session(cls, stream_id: str, session_id: str, session_details: dict) -> int:
        """Atomically registers a session, caches metadata, and increments count in Redis."""
        sess_key = f"vms:sessions:{session_id}"
        viewers_set = f"vms:viewers:{stream_id}"
        count_key = f"vms:viewer_count:{stream_id}"
        details_serialized = json.dumps(session_details)
        
        if redis_client:
            try:
                # Store session details with 60-second TTL
                await redis_client.set(sess_key, details_serialized, ex=60)
                
                # Execute atomic addition via Lua script
                count = await redis_client.eval(cls.ADD_SESSION_LUA, 2, viewers_set, count_key, session_id)
                # Keep vms:stream:viewers count in sync for legacy compatibility
                await RedisManager.set_viewer_count(stream_id, count)
                return count
            except Exception as e:
                print(f"[viewer_tracker] Redis error during atomic add: {e}. Falling back to memory.")
                
        # In-memory fallback
        cls._memory_viewers.setdefault(viewers_set, set()).add(session_id)
        count = len(cls._memory_viewers[viewers_set])
        cls._memory_counts[count_key] = count
        await RedisManager.set_viewer_count(stream_id, count)
        return count

    @classmethod
    async def remove_viewer_session(cls, stream_id: str, session_id: str) -> int:
        """Atomically removes a session and decrements count in Redis (protects against double-decrement)."""
        sess_key = f"vms:sessions:{session_id}"
        viewers_set = f"vms:viewers:{stream_id}"
        count_key = f"vms:viewer_count:{stream_id}"
        
        if redis_client:
            try:
                await redis_client.delete(sess_key)
                # Execute atomic removal via Lua script
                count = await redis_client.eval(cls.REMOVE_SESSION_LUA, 2, viewers_set, count_key, session_id)
                await RedisManager.set_viewer_count(stream_id, count)
                return count
            except Exception as e:
                print(f"[viewer_tracker] Redis error during atomic remove: {e}. Falling back to memory.")
                
        # In-memory fallback
        viewers = cls._memory_viewers.get(viewers_set, set())
        if session_id in viewers:
            viewers.discard(session_id)
            count = len(viewers)
            cls._memory_counts[count_key] = count
            await RedisManager.set_viewer_count(stream_id, count)
            return count
        return cls._memory_counts.get(count_key, 0)

    @classmethod
    async def get_viewer_count(cls, stream_id: str) -> int:
        """Fetch the atomic viewer count for a stream."""
        count_key = f"vms:viewer_count:{stream_id}"
        if redis_client:
            try:
                val = await redis_client.get(count_key)
                return int(val) if val else 0
            except Exception:
                pass
        return cls._memory_counts.get(count_key, 0)
