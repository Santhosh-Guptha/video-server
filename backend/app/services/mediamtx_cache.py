import time
from typing import Dict, Any, Optional

class MediaMTXCache:
    _cache: Dict[str, Dict[str, Any]] = {}
    _ttl: float = 30.0  # default 30 seconds

    @classmethod
    def get(cls, key: str) -> Optional[Any]:
        """Fetch item from cache if still valid."""
        item = cls._cache.get(key)
        if item:
            if time.time() - item["timestamp"] < cls._ttl:
                return item["data"]
            else:
                cls._cache.pop(key, None)
        return None

    @classmethod
    def set(cls, key: str, data: Any) -> None:
        """Cache data payload with current timestamp."""
        cls._cache[key] = {
            "data": data,
            "timestamp": time.time()
        }

    @classmethod
    def invalidate(cls, key: str) -> None:
        """Manually clear a cached key."""
        cls._cache.pop(key, None)

    @classmethod
    def clear_all(cls) -> None:
        """Empty the cache."""
        cls._cache.clear()
