import asyncio
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from .config import settings
from .models import CameraStream, StreamState
from .redis_client import RedisManager

class StreamManager:
    def __init__(self, api_url: str = settings.mediamtx_api_url):
        self.api_url = api_url

    async def add_stream(self, session: AsyncSession, stream: CameraStream) -> None:
        """
        Registers a camera stream path dynamically in MediaMTX.
        Transitions the stream state to CONNECTING.
        """
        path_name = stream.stream_id
        
        # If url is marked as publisher or empty, we treat it as an Edge Push (RTMP/WHIP publisher)
        is_push = "publisher" in stream.stream_url.lower() or not stream.stream_url.strip()
        
        payload = {
            "source": "publisher" if is_push else stream.stream_url,
            "sourceOnDemand": False,
            "record": True # Automatic local fragmented MP4 recording
        }

        async with httpx.AsyncClient() as client:
            url = f"{self.api_url}/v3/config/paths/add/{path_name}"
            try:
                response = await client.post(url, json=payload)
                if response.status_code in (200, 201):
                    print(f"[stream_manager] Registered path {path_name} in MediaMTX.")
                    await self.set_stream_state(session, stream, StreamState.CONNECTING)
                else:
                    # If already exists, we edit it to sync configuration
                    if "already exists" in response.text or response.status_code == 400:
                        edit_url = f"{self.api_url}/v3/config/paths/edit/{path_name}"
                        edit_resp = await client.post(edit_url, json=payload)
                        if edit_resp.status_code in (200, 201):
                            print(f"[stream_manager] Path {path_name} already existed. Updated config.")
                            await self.set_stream_state(session, stream, StreamState.CONNECTING)
                            return
                    print(f"[stream_manager] Failed to register path {path_name}: {response.text}")
                    await self.set_stream_state(session, stream, StreamState.ERROR, response.text)
            except Exception as e:
                print(f"[stream_manager] Connection error registering path {path_name}: {e}")
                await self.set_stream_state(session, stream, StreamState.ERROR, str(e))

    async def remove_stream(self, session: AsyncSession, stream: CameraStream) -> None:
        """
        Deletes a path configuration from MediaMTX and updates status to OFFLINE.
        """
        path_name = stream.stream_id
        async with httpx.AsyncClient() as client:
            url = f"{self.api_url}/v3/config/paths/delete/{path_name}"
            try:
                response = await client.delete(url)
                if response.status_code in (200, 204):
                    print(f"[stream_manager] Deleted path {path_name} from MediaMTX.")
                else:
                    print(f"[stream_manager] Failed to delete path {path_name}: {response.text}")
            except Exception as e:
                print(f"[stream_manager] Error deleting path {path_name}: {e}")

        await self.set_stream_state(session, stream, StreamState.OFFLINE)

    async def restart_stream(self, session: AsyncSession, stream: CameraStream) -> None:
        """
        Forces a reconnect/restart by deleting and re-registering the stream path.
        """
        print(f"[stream_manager] Restarting stream: {stream.stream_id}")
        await self.remove_stream(session, stream)
        await asyncio.sleep(0.5)
        await self.add_stream(session, stream)

    async def set_stream_state(self, session: AsyncSession, stream: CameraStream, state: StreamState, error_message: str | None = None) -> None:
        """
        Updates the stream state transition rules, caching the result in Redis
        and writing it permanently to the PostgreSQL database.
        """
        # Define valid state machine transitions to prevent illegal state jumps
        # e.g., if a stream is OFFLINE, we cannot jump to ONLINE directly without CONNECTING first
        current_state = stream.status
        if current_state == state:
            return

        stream.status = state
        stream.error_message = error_message
        await session.commit()

        # Update cache
        await RedisManager.set_stream_state(stream.stream_id, state.value, error_message)
        print(f"[stream_manager] Transitioned: {stream.stream_id} -> {state.value} (from {current_state.value})")

# Global stream manager instance
stream_manager = StreamManager()
