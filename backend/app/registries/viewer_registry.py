from typing import Optional, Dict
import json
from ..redis_client import redis_client

class ViewerRegistry:
    @staticmethod
    async def get_session_details(session_id: str) -> Optional[Dict]:
        """Fetch cached metadata and details for a active viewer session."""
        if redis_client:
            try:
                data = await redis_client.get(f"vms:sessions:{session_id}")
                if data:
                    return json.loads(data)
            except Exception as e:
                print(f"[viewer_registry] Redis lookup failed for session {session_id}: {e}")
        return None

    @staticmethod
    async def refresh_heartbeat(session_id: str, stream_id: str) -> None:
        """Refreshes the sliding expiration of the session key in Redis cache (heartbeat)."""
        if redis_client:
            try:
                sess_key = f"vms:sessions:{session_id}"
                # Extend TTL by 60 seconds
                await redis_client.expire(sess_key, 60)
            except Exception as e:
                print(f"[viewer_registry] Heartbeat refresh failed for session {session_id}: {e}")
