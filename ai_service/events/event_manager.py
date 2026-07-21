import asyncio
import time
import uuid
import json
from typing import List, Dict, Set, Any
from fastapi import WebSocket
from ..schemas import AIEvent, BoundingBox
from ..database import save_ai_event, get_recent_ai_events

class EventManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        # Capture the main thread event loop running the WebSocket connection
        self.loop = asyncio.get_running_loop()
        print(f"[EventManager] WebSocket connected. Captured event loop: {self.loop}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_event(self, event_data: Dict[str, Any]):
        """Broadcast event to all connected WebSocket UI clients."""
        if not self.active_connections:
            return

        message = json.dumps({"type": "ai_event", "data": event_data})
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.add(connection)

        for conn in disconnected:
            self.disconnect(conn)

    def process_and_emit(
        self,
        camera_id: str,
        camera_name: str,
        event_type: str,
        label: str,
        confidence: float,
        bbox: Dict[str, float],
        zone_id: str = None,
        details: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        formatted_time = time.strftime("%Y-%m-%d %H:%M:%S")
        event_id = f"evt-{uuid.uuid4().hex[:10]}"

        event_dict = {
            "event_id": event_id,
            "camera_id": camera_id,
            "camera_name": camera_name,
            "event_type": event_type,
            "timestamp": time.time(),
            "formatted_time": formatted_time,
            "confidence": confidence,
            "label": label,
            "bbox": bbox,
            "zone_id": zone_id,
            "details": details or {},
            "snapshot_url": f"/api/ai/events/{event_id}/snapshot"
        }

        # ─── 1. Save to DB Synchronously ───────────────────────────
        try:
            save_ai_event(event_dict)
        except Exception as e:
            print(f"[EventManager] SQLite save error: {e}")

        # ─── 2. Thread-Safe WebSocket Broadcast ────────────────────
        if self.loop and self.loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self.broadcast_event(event_dict), self.loop)
            except Exception as e:
                print(f"[EventManager] Thread-safe broadcast error: {e}")
        else:
            # Fallback if loop is not set but we are in main loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.broadcast_event(event_dict))
            except Exception:
                pass

        return event_dict

event_manager = EventManager()
