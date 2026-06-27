import asyncio
from typing import Dict, List, Callable, Any, Awaitable

class EventBus:
    _listeners: Dict[str, List[Callable[[Any], Awaitable[None]]]] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def subscribe(cls, event_type: str, callback: Callable[[Any], Awaitable[None]]):
        """Subscribes an async callback to a specific event type."""
        async with cls._lock:
            if event_type not in cls._listeners:
                cls._listeners[event_type] = []
            if callback not in cls._listeners[event_type]:
                cls._listeners[event_type].append(callback)
            print(f"[event_bus] Subscribed listener to event: {event_type}")

    @classmethod
    async def unsubscribe(cls, event_type: str, callback: Callable[[Any], Awaitable[None]]):
        """Unsubscribes an async callback from an event type."""
        async with cls._lock:
            if event_type in cls._listeners and callback in cls._listeners[event_type]:
                cls._listeners[event_type].remove(callback)
                print(f"[event_bus] Unsubscribed listener from event: {event_type}")

    @classmethod
    async def publish(cls, event_type: str, data: Any):
        """Publishes an event to all subscribed listeners asynchronously without blocking."""
        listeners = []
        async with cls._lock:
            if event_type in cls._listeners:
                listeners = list(cls._listeners[event_type])
        
        if not listeners:
            return

        async def run_callback(cb, event_data):
            try:
                await cb(event_data)
            except Exception as e:
                print(f"[event_bus] Error in event listener for {event_type}: {e}")

        # Spawn task to run listeners asynchronously so the caller is never blocked!
        # This guarantees "Never let any component in this architecture block the live streaming request"
        for cb in listeners:
            asyncio.create_task(run_callback(cb, data))
