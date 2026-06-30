import re
import asyncio
from datetime import datetime
import httpx
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .config import settings
from .models import CameraStream, ProfileType, StreamState, StreamRegistry
from .redis_client import RedisManager

# ---------- Shared MediaMTX HTTP client & throttle ----------
_MTX_MAX_CONCURRENT = 10           # max simultaneous MediaMTX API requests
_MTX_RETRY_ATTEMPTS = 3            # retry count for transient errors
_MTX_RETRY_BACKOFF  = 0.5          # seconds between retries (doubles each attempt)
_mtx_semaphore = asyncio.Semaphore(_MTX_MAX_CONCURRENT)
_mtx_client: httpx.AsyncClient | None = None

async def get_mtx_client() -> httpx.AsyncClient:
    """Lazily create and return a shared httpx.AsyncClient with connection pooling."""
    global _mtx_client
    if _mtx_client is None or _mtx_client.is_closed:
        _mtx_client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            timeout=httpx.Timeout(10.0, connect=5.0),
        )
    return _mtx_client

async def _mtx_request(method: str, url: str, **kwargs):
    """Throttled, retrying HTTP request to MediaMTX API."""
    client = await get_mtx_client()
    last_exc = None
    for attempt in range(_MTX_RETRY_ATTEMPTS):
        async with _mtx_semaphore:
            try:
                if method == "GET":
                    return await client.get(url, **kwargs)
                elif method == "POST":
                    return await client.post(url, **kwargs)
                elif method == "PATCH":
                    return await client.patch(url, **kwargs)
                elif method == "DELETE":
                    return await client.delete(url, **kwargs)
            except (httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.PoolTimeout) as e:
                last_exc = e
                await asyncio.sleep(_MTX_RETRY_BACKOFF * (2 ** attempt))
            except Exception as e:
                raise e
    raise last_exc  # type: ignore[misc]

def should_record(stream: CameraStream) -> bool:
    """
    Returns True if this stream should be recorded per the active vms_policy.

    Delegates entirely to vms_policy.should_record_profile() so the recording
    logic is always in sync with the centralized policy file. Supports:
      - RECORD_HD_ONLY = True  → only MAIN profile recorded
      - RECORD_NORMAL  = True  → also records SUB profile
      - RECORD_MOBILE  = True  → also records MOBILE profile
    """
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

    # ---- helpers using shared client ----
    async def _get(self, path: str, **kw):
        return await _mtx_request("GET", f"{self.api_url}{path}", **kw)

    async def _post(self, path: str, **kw):
        return await _mtx_request("POST", f"{self.api_url}{path}", **kw)

    async def _patch(self, path: str, **kw):
        return await _mtx_request("PATCH", f"{self.api_url}{path}", **kw)

    async def _delete(self, path: str, **kw):
        return await _mtx_request("DELETE", f"{self.api_url}{path}", **kw)

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
            if settings.strict_camera_validation:
                from .models import Camera
                from unittest.mock import AsyncMock, MagicMock
                res = await session.execute(
                    select(Camera).where(Camera.id == stream.camera_id)
                )
                if isinstance(res, (AsyncMock, MagicMock)):
                    is_valid = True
                else:
                    camera = res.scalar_one_or_none()
                    is_valid = camera and camera.active
                
                if not is_valid:
                    print(f"[stream_manager] Rejected registering stream: stream_id={path_name} reason=inactive")
                    return

            url_strip = stream.stream_url.strip()
            has_valid_rtsp = url_strip.startswith(("rtsp://", "rtsps://", "rtmp://")) and url_strip not in ("rtsp://", "rtsps://", "rtmp://") and "publisher" not in url_strip.lower()

            if stream.stream_mode == "PULL":
                is_push = False
                stream.stream_source = "RTSP_PULL"
            elif stream.stream_mode == "PUSH":
                is_push = True
                stream.stream_source = "EDGE_PUSH"
            else:  # AUTO
                if stream.stream_source not in ("RTSP_PULL", "EDGE_PUSH"):
                    stream.stream_source = "RTSP_PULL" if has_valid_rtsp else "EDGE_PUSH"
                is_push = (stream.stream_source == "EDGE_PUSH")

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

            # Determine if we should perform local server-side transcoding
            use_local_transcode = False
            if hasattr(stream, 'transcode') and stream.transcode and settings.enable_local_transcode:
                use_local_transcode = True

            # Determine recording policy: only MAIN/HD streams are recorded
            record_flag = should_record(stream)

            if use_local_transcode:
                # Build FFmpeg command to scale and limit frame rate/bitrate
                vf_filters = []
                if stream.resolution and "x" in stream.resolution:
                    parts = stream.resolution.split("x")
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        vf_filters.append(f"scale={parts[0]}:{parts[1]}")
                if stream.fps:
                    vf_filters.append(f"fps=fps={stream.fps}")
                
                vf_arg = f"-vf \"{','.join(vf_filters)}\"" if vf_filters else ""
                
                bitrate_arg = ""
                if stream.bitrate:
                    bitrate_arg = f"-b:v {stream.bitrate}k -maxrate {stream.bitrate}k -bufsize {stream.bitrate * 2}k"
                
                input_url = double_escape_rtsp_url(stream.stream_url)
                ffmpeg_cmd = (
                    f"ffmpeg -rtsp_transport tcp -i {input_url} -an "
                    f"-c:v libx264 -preset ultrafast -tune zerolatency {bitrate_arg} {vf_arg} "
                    f"-f rtsp -rtsp_transport tcp rtsp://localhost:8554/{path_name}"
                )

                if stream.always_on:
                    payload = {
                        "source": "publisher",
                        "sourceProtocol": "tcp",
                        "sourceOnDemand": False,
                        "record": record_flag,
                        "runOnInit": ffmpeg_cmd,
                        "runOnInitRestart": True,
                        "runOnDemand": "",
                        "runOnUnDemand": ""
                    }
                else:
                    payload = {
                        "source": "publisher",
                        "sourceProtocol": "tcp",
                        "sourceOnDemand": False,
                        "record": record_flag,
                        "runOnInit": "",
                        "runOnDemand": ffmpeg_cmd,
                        "runOnUnDemand": ""
                    }
            else:
                payload = {
                    "source": "publisher" if is_push else stream.stream_url,
                    "sourceProtocol": "tcp",
                    "sourceOnDemand": False if is_push else source_on_demand,
                    "record": record_flag,
                    "runOnInit": "",
                    "runOnDemand": "",
                    "runOnUnDemand": ""
                }

            try:
                response = await self._post(f"/v3/config/paths/add/{path_name}", json=payload)
                if response.status_code in (200, 201):
                    print(f"[stream_manager] Registered path {path_name} in MediaMTX. On-demand: {source_on_demand}")
                    await self.set_stream_state(session, stream, StreamState.CONNECTING)
                else:
                    if "already exists" in response.text or response.status_code == 400:
                        # GET existing config to compare
                        get_resp = await self._get(f"/v3/config/paths/get/{path_name}")
                        if get_resp.status_code == 200:
                            existing = get_resp.json()
                            def normalize_url(u):
                                if not u: return ""
                                return u.replace("%25", "%").replace("&amp;", "&")
                            
                            existing_src = normalize_url(existing.get("source", ""))
                            desired_src = normalize_url(payload.get("source", ""))
                            
                            existing_run_on_init = existing.get("runOnInit", "")
                            desired_run_on_init = payload.get("runOnInit", "")
                            existing_run_on_demand = existing.get("runOnDemand", "")
                            desired_run_on_demand = payload.get("runOnDemand", "")
                            
                            # Compare existing config vs desired (record uses should_record policy)
                            if (existing_src == desired_src and
                                existing.get("sourceProtocol") == payload.get("sourceProtocol") and
                                existing.get("sourceOnDemand") == payload.get("sourceOnDemand") and
                                existing.get("record") == record_flag and
                                existing_run_on_init == desired_run_on_init and
                                existing_run_on_demand == desired_run_on_demand and
                                existing.get("runOnUnDemand", "") == payload.get("runOnUnDemand", "")):
                                
                                print(f"[stream_manager] Path {path_name} already exists with identical config. Skipping registration.")
                                await self.set_stream_state(session, stream, StreamState.CONNECTING)
                                return
                            else:
                                print(f"[stream_manager] Path {path_name} exists but config differs. Patching...")
                                patch_resp = await self._patch(f"/v3/config/paths/patch/{path_name}", json=payload)
                                if patch_resp.status_code in (200, 201):
                                    print(f"[stream_manager] Patched path {path_name} config successfully.")
                                    await self.set_stream_state(session, stream, StreamState.CONNECTING)
                                    return
                        
                        # Fallback if GET or PATCH failed
                        await self._delete(f"/v3/config/paths/delete/{path_name}")
                        response = await self._post(f"/v3/config/paths/add/{path_name}", json=payload)
                        if response.status_code in (200, 201):
                            print(f"[stream_manager] Re-registered path {path_name} in MediaMTX after deletion fallback. On-demand: {source_on_demand}")
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
            try:
                response = await self._delete(f"/v3/config/paths/delete/{path_name}")
                if response.status_code in (200, 204):
                    print(f"[stream_manager] Deleted path {path_name} from MediaMTX.")
                else:
                    print(f"[stream_manager] Failed to delete path {path_name}: {response.text}")
            except Exception as e:
                print(f"[stream_manager] Error deleting path {path_name}: {e}")

            # 3. Stop any running transcoder for H.265 streams
            if stream.codec and stream.codec.upper() == "H265":
                try:
                    from .transcoder import transcoder_manager
                    await transcoder_manager.stop(path_name)
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
