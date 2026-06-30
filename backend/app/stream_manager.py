import re
import asyncio
from datetime import datetime
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .config import settings
from .models import CameraStream, ProfileType, StreamState, StreamRegistry
from .redis_client import RedisManager
from .events.event_bus import EventBus
from .registries.stream_registry import StreamRegistry as StreamRegistrySvc

# ---------- Shared MediaMTX HTTP client ----------
_mtx_client: httpx.AsyncClient | None = None

async def get_mtx_client() -> httpx.AsyncClient:
    global _mtx_client
    if _mtx_client is None or _mtx_client.is_closed:
        _mtx_client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            timeout=httpx.Timeout(10.0, connect=5.0),
        )
    return _mtx_client

async def _mtx_request(method: str, url: str, **kwargs):
    client = await get_mtx_client()
    try:
        if method == "GET":
            return await client.get(url, **kwargs)
        elif method == "POST":
            return await client.post(url, **kwargs)
        elif method == "PATCH":
            return await client.patch(url, **kwargs)
        elif method == "DELETE":
            return await client.delete(url, **kwargs)
    except Exception as e:
        raise e

def should_record(stream: CameraStream) -> bool:
    from .config import should_record_profile
    return should_record_profile(stream.profile_type.value if hasattr(stream.profile_type, 'value') else str(stream.profile_type))

def double_escape_rtsp_url(url: str) -> str:
    if not url or not url.startswith(("rtsp://", "rtsps://", "rtmp://")):
        return url
    if "@" not in url:
        return url
    parts = url.split("://", 1)
    if len(parts) < 2:
        return url
    scheme, rest = parts
    user_host = rest.rsplit("@", 1)
    if len(user_host) < 2:
        return url
    userinfo, host = user_host
    escaped_userinfo = re.sub(r'%([0-9a-fA-F]{2})', r'%25\1', userinfo)
    return f"{scheme}://{escaped_userinfo}@{host}"

class StreamManager:
    def __init__(self, api_url: str = settings.mediamtx_api_url):
        self.api_url = api_url

    async def _get(self, path: str, **kw):
        return await _mtx_request("GET", f"{self.api_url}{path}", **kw)

    async def _post(self, path: str, **kw):
        return await _mtx_request("POST", f"{self.api_url}{path}", **kw)

    async def _patch(self, path: str, **kw):
        return await _mtx_request("PATCH", f"{self.api_url}{path}", **kw)

    async def _delete(self, path: str, **kw):
        return await _mtx_request("DELETE", f"{self.api_url}{path}", **kw)

    async def add_stream(self, session: AsyncSession, stream: CameraStream) -> None:
        """Registers a camera stream path permanently in MediaMTX with sourceOnDemand = True."""
        path_name = stream.stream_id
        lock_name = f"stream:{path_name}"
        
        # Acquire Lock
        acquired = await RedisManager.acquire_lock(lock_name, expire_seconds=30)
        if not acquired:
            print(f"[stream_manager] Lock busy for stream {path_name}")
            return

        try:
            url_strip = stream.stream_url.strip()
            is_push = stream.stream_mode == "PUSH" or (stream.stream_mode == "AUTO" and "publisher" in url_strip.lower())
            
            # 1. Ensure path exists in DB Registry
            res = await session.execute(
                select(StreamRegistry).where(StreamRegistry.stream_id == path_name)
            )
            registry_entry = res.scalar_one_or_none()
            if not registry_entry:
                registry_entry = StreamRegistry(
                    stream_id=path_name,
                    mediamtx_node="node1",
                    source_type="EDGE_PUSH" if is_push else "RTSP_PULL",
                    recording_enabled=True,
                    status="REGISTERED",
                    last_seen=datetime.utcnow()
                )
                session.add(registry_entry)
                await session.commit()

            # 2. Add configuration to MediaMTX
            payload = {
                "source": "publisher" if is_push else stream.stream_url,
                "sourceProtocol": "tcp",
                "sourceOnDemand": True,  # Keep permanent, connect RTSP on-demand
                "record": should_record(stream),
                "runOnInit": "",
                "runOnDemand": "",
                "runOnUnDemand": ""
            }

            resp = await self._post(f"/v3/config/paths/add/{path_name}", json=payload)
            if resp.status_code in (200, 201):
                print(f"[stream_manager] Permanently registered path {path_name} in MediaMTX with sourceOnDemand = True")
                await self.set_stream_state(session, stream, StreamState.CONNECTING)
                await EventBus.publish("stream_started", {"stream_id": path_name})
            elif resp.status_code == 400 or "already exists" in resp.text:
                # Patch configuration to ensure it matches
                await self._patch(f"/v3/config/paths/patch/{path_name}", json=payload)
                await self.set_stream_state(session, stream, StreamState.CONNECTING)
        finally:
            await RedisManager.release_lock(lock_name)

    async def remove_stream(self, session: AsyncSession, stream: CameraStream) -> None:
        """Removes a path configuration from MediaMTX (only if camera is deleted/disabled)."""
        path_name = stream.stream_id
        lock_name = f"stream:{path_name}"
        
        acquired = await RedisManager.acquire_lock(lock_name, expire_seconds=30)
        if not acquired:
            return

        try:
            # 1. MediaMTX delete
            resp = await self._delete(f"/v3/config/paths/delete/{path_name}")
            if resp.status_code in (200, 204):
                print(f"[stream_manager] Deleted path {path_name} from MediaMTX.")
                await EventBus.publish("stream_closed", {"stream_id": path_name})
            
            # 2. Stop transcoder if active
            if stream.codec and stream.codec.upper() == "H265":
                from .transcoder import transcoder_manager
                await transcoder_manager.stop(path_name)

            await self.set_stream_state(session, stream, StreamState.OFFLINE)
        finally:
            await RedisManager.release_lock(lock_name)

    async def restart_stream(self, session: AsyncSession, stream: CameraStream) -> None:
        """Forces path reconfiguration restart."""
        await self.remove_stream(session, stream)
        await asyncio.sleep(0.5)
        await self.add_stream(session, stream)

    async def set_stream_state(self, session: AsyncSession, stream: CameraStream, state: StreamState, error_message: str | None = None) -> None:
        """Transitions state in DB and cache."""
        if stream.status == state:
            return
        stream.status = state
        stream.error_message = error_message
        await session.commit()
        await RedisManager.set_stream_state(stream.stream_id, state.value, error_message)

stream_manager = StreamManager()
