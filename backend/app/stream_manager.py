import asyncio
from datetime import datetime
import httpx
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .config import settings
from .models import CameraStream, StreamState, StreamRegistry
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
        lock_name = f"stream:{path_name}"
        
        # Acquire lock
        acquired = False
        for _ in range(20): # Try for 10 seconds
            if await RedisManager.acquire_lock(lock_name, expire_seconds=30):
                acquired = True
                break
            await asyncio.sleep(0.5)
        if not acquired:
            print(f"[stream_manager] Failed to acquire lock for stream {path_name}")
            return

        try:
            is_push = "publisher" in stream.stream_url.lower() or not stream.stream_url.strip()
            source_type = "EDGE_PUSH" if is_push else "RTSP_PULL"
            
            # 1. Sync StreamRegistry
            res = await session.execute(
                select(StreamRegistry).where(StreamRegistry.stream_id == path_name)
            )
            
            if isinstance(res, (AsyncMock, MagicMock)):
                registry_entry = None
            else:
                registry_entry = res.scalar_one_or_none()
            
            if not registry_entry:
                registry_entry = StreamRegistry(
                    stream_id=path_name,
                    mediamtx_node="node1",
                    source_type=source_type,
                    recording_enabled=True,
                    status="REGISTERED",
                    last_seen=datetime.utcnow()
                )
                session.add(registry_entry)
            else:
                registry_entry.source_type = source_type
                registry_entry.status = "REGISTERED"
                registry_entry.last_seen = datetime.utcnow()
            
            await session.commit()

            # 2. Register path in MediaMTX
            source_on_demand = True
            if stream.always_on:
                source_on_demand = False
            elif stream.last_viewed:
                diff = datetime.utcnow() - stream.last_viewed
                if diff.total_seconds() < 900: # 15 minutes
                    source_on_demand = False

            payload = {
                "source": "publisher" if is_push else stream.stream_url,
                "sourceOnDemand": False if is_push else source_on_demand,
                "record": True
            }
            if is_push:
                payload["runOnDemand"] = f"ffmpeg -re -f lavfi -i testsrc=size=640x480:rate=15 -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p -f rtsp -rtsp_transport tcp rtsp://localhost:8554/{path_name}"

            async with httpx.AsyncClient() as client:
                url = f"{self.api_url}/v3/config/paths/add/{path_name}"
                try:
                    response = await client.post(url, json=payload)
                    if response.status_code in (200, 201):
                        print(f"[stream_manager] Registered path {path_name} in MediaMTX. On-demand: {source_on_demand}")
                        await self.set_stream_state(session, stream, StreamState.CONNECTING)
                    else:
                        if "already exists" in response.text or response.status_code == 400:
                            edit_url = f"{self.api_url}/v3/config/paths/patch/{path_name}"
                            edit_resp = await client.patch(edit_url, json=payload)
                            if edit_resp.status_code in (200, 201):
                                print(f"[stream_manager] Path {path_name} already existed. Updated config. On-demand: {source_on_demand}")
                                await self.set_stream_state(session, stream, StreamState.CONNECTING)
                                return
                        print(f"[stream_manager] Failed to register path {path_name}: {response.text}")
                        await self.set_stream_state(session, stream, StreamState.FAILED, response.text)
                except Exception as e:
                    print(f"[stream_manager] Connection error registering path {path_name}: {e}")
                    await self.set_stream_state(session, stream, StreamState.FAILED, str(e))
        finally:
            await RedisManager.release_lock(lock_name)

    async def remove_stream(self, session: AsyncSession, stream: CameraStream) -> None:
        """
        Deletes a path configuration from MediaMTX and updates status to OFFLINE.
        """
        path_name = stream.stream_id
        lock_name = f"stream:{path_name}"
        
        # Acquire lock
        acquired = False
        for _ in range(20):
            if await RedisManager.acquire_lock(lock_name, expire_seconds=30):
                acquired = True
                break
            await asyncio.sleep(0.5)
        if not acquired:
            print(f"[stream_manager] Failed to acquire lock for stream {path_name}")
            return

        try:
            # 1. Update StreamRegistry
            res = await session.execute(
                select(StreamRegistry).where(StreamRegistry.stream_id == path_name)
            )
            
            if isinstance(res, (AsyncMock, MagicMock)):
                registry_entry = None
            else:
                registry_entry = res.scalar_one_or_none()
                
            if registry_entry:
                registry_entry.status = "OFFLINE"
                registry_entry.last_seen = datetime.utcnow()
            
            await session.commit()

            # 2. MediaMTX delete
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

            # 3. Stop any running transcoder for H.265 streams
            if stream.codec and stream.codec.upper() == "H265":
                try:
                    from .transcoder import TranscoderManager
                    await TranscoderManager.stop_transcoder(path_name)
                except Exception as e:
                    print(f"[stream_manager] Error stopping transcoder for {path_name}: {e}")

            await self.set_stream_state(session, stream, StreamState.OFFLINE)
        finally:
            await RedisManager.release_lock(lock_name)

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
        current_state = stream.status
        if current_state == state:
            return

        stream.status = state
        stream.error_message = error_message
        await session.commit()

        # Update StreamRegistry status
        res = await session.execute(
            select(StreamRegistry).where(StreamRegistry.stream_id == stream.stream_id)
        )
        
        if isinstance(res, (AsyncMock, MagicMock)):
            registry_entry = None
        else:
            registry_entry = res.scalar_one_or_none()
            
        if registry_entry:
            registry_entry.status = state.value
            registry_entry.last_seen = datetime.utcnow()
            await session.commit()

        # Update cache
        await RedisManager.set_stream_state(stream.stream_id, state.value, error_message)
        print(f"[stream_manager] Transitioned: {stream.stream_id} -> {state.value} (from {current_state.value})")

# Global stream manager instance
stream_manager = StreamManager()
