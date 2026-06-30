import json
import asyncio
from typing import Callable, Dict, List
from ..redis_client import redis_client

class EventBus:
    _listeners: Dict[str, List[Callable]] = {}

    @classmethod
    def subscribe(cls, event_type: str, callback: Callable) -> None:
        """Subscribe a handler to local events."""
        cls._listeners.setdefault(event_type, []).append(callback)

    @classmethod
    async def publish(cls, event_type: str, data: dict) -> None:
        """Publish event locally and push to Redis Streams for distributed workers."""
        # 1. Dispatch locally in-memory
        if event_type in cls._listeners:
            for cb in cls._listeners[event_type]:
                try:
                    if asyncio.iscoroutinefunction(cb):
                        asyncio.create_task(cb(data))
                    else:
                        cb(data)
                except Exception as e:
                    print(f"[event_bus] Error dispatching event {event_type}: {e}")

        # 2. Publish to Redis stream if connected
        if redis_client:
            try:
                payload = {
                    "event_type": event_type,
                    "data": json.dumps(data)
                }
                # XADD key * fields
                await redis_client.xadd("vms:system_events", payload, maxlen=10000, approximate=True)
            except Exception as e:
                print(f"[event_bus] Redis Stream publish failed: {e}")
