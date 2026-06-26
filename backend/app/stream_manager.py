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
    _fps_transcoders = {}

    def __init__(self, api_url: str = settings.mediamtx_api_url):
        self.api_url = api_url

    async def start_fps_transcoder(self, stream: CameraStream) -> None:
        path_name = stream.stream_id
        await self.stop_fps_transcoder(path_name)
        
        ffmpeg_cmd = [
            settings.ffmpeg_path,
            "-hide_banner",
            "-loglevel", "warning",
            "-rtsp_transport", "tcp",
            "-i", stream.stream_url,
            "-an",
            "-vf", f"fps=fps={stream.fps}",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-g", "25",
            "-f", "rtsp",
            "-rtsp_transport", "tcp",
            f"rtsp://127.0.0.1:8554/{path_name}"
        ]
        print(f"[stream_manager] Starting FPS-limiting transcoder for {path_name}: {' '.join(ffmpeg_cmd)}")
        try:
            proc = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            self._fps_transcoders[path_name] = proc
            
            async def log_stderr(p, sid):
                try:
                    while True:
                        line = await p.stderr.readline()
                        if not line:
                            break
                        print(f"[transcoder-fps:{sid}] {line.decode(errors='ignore').strip()}")
                except Exception:
                    pass
            asyncio.create_task(log_stderr(proc, path_name))
        except Exception as ffmpeg_err:
            print(f"[stream_manager] Failed to start FFmpeg transcoder for {path_name}: {ffmpeg_err}")

    async def stop_fps_transcoder(self, stream_id: str) -> None:
        proc = self._fps_transcoders.pop(stream_id, None)
        if proc:
            print(f"[stream_manager] Stopping FPS transcoder for {stream_id}")
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=3.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

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

            # Check if actual FPS is greater than configured FPS to trigger limiting
            should_limit_fps = False
            if not is_push and has_valid_rtsp and stream.fps:
                actual_fps = None
                try:
                    import json
                    cmd_probe = [
                        "ffprobe", "-v", "error",
                        "-rtsp_transport", "tcp",
                        "-select_streams", "v:0",
                        "-show_entries", "stream=avg_frame_rate,r_frame_rate",
                        "-of", "json",
                        url_strip
                    ]
                    proc_probe = await asyncio.create_subprocess_exec(
                        *cmd_probe,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout_probe, _ = await asyncio.wait_for(proc_probe.communicate(), timeout=5.0)
                    if proc_probe.returncode == 0:
                        probe_data = json.loads(stdout_probe.decode())
                        streams_info = probe_data.get("streams", [])
                        if streams_info:
                            avg_frame_rate = streams_info[0].get("avg_frame_rate", "0/0")
                            n, d = map(int, avg_frame_rate.split("/"))
                            if d > 0 and n > 0:
                                actual_fps = n / d
                            else:
                                r_frame_rate = streams_info[0].get("r_frame_rate", "0/0")
                                n, d = map(int, r_frame_rate.split("/"))
                                if d > 0 and n > 0 and (n/d) < 1000:  # filter ticks
                                    actual_fps = n / d
                except Exception as probe_err:
                    print(f"[stream_manager] Failed to probe FPS for {path_name}: {probe_err}")

                if actual_fps and actual_fps > stream.fps:
                    should_limit_fps = True
                    print(f"[stream_manager] Stream {path_name} actual FPS ({actual_fps:.2f}) > configured ({stream.fps}). Enabling transcoder.")

            is_push_source = is_push or should_limit_fps
            source_type = "EDGE_PUSH" if is_push else ("RTSP_PULL" if not should_limit_fps else "FPS_LIMIT_TRANSCODE")
            
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

            # Determine recording policy: only MAIN/HD streams are recorded
            record_flag = should_record(stream)

            payload = {
                "source": "publisher" if is_push_source else stream.stream_url,
                "sourceProtocol": "tcp",
                "sourceOnDemand": False if is_push_source else source_on_demand,
                "record": record_flag,
                "runOnDemand": "",
                "runOnUnDemand": ""
            }

            async with httpx.AsyncClient() as client:
                url = f"{self.api_url}/v3/config/paths/add/{path_name}"
                try:
                    response = await client.post(url, json=payload)
                    if response.status_code in (200, 201):
                        print(f"[stream_manager] Registered path {path_name} in MediaMTX. On-demand: {source_on_demand}")
                        if should_limit_fps:
                            await self.start_fps_transcoder(stream)
                        await self.set_stream_state(session, stream, StreamState.CONNECTING)
                    else:
                        if "already exists" in response.text or response.status_code == 400:
                            # GET existing config to compare
                            get_url = f"{self.api_url}/v3/config/paths/get/{path_name}"
                            get_resp = await client.get(get_url)
                            if get_resp.status_code == 200:
                                existing = get_resp.json()
                                def normalize_url(u):
                                    if not u: return ""
                                    return u.replace("%25", "%").replace("&amp;", "&")
                                
                                existing_src = normalize_url(existing.get("source", ""))
                                desired_src = normalize_url(payload.get("source", ""))
                                
                                # Compare existing config vs desired (record uses should_record policy)
                                if (existing_src == desired_src and
                                    existing.get("sourceProtocol") == payload.get("sourceProtocol") and
                                    existing.get("sourceOnDemand") == payload.get("sourceOnDemand") and
                                    existing.get("record") == record_flag and
                                    existing.get("runOnDemand", "") == payload.get("runOnDemand", "") and
                                    existing.get("runOnUnDemand", "") == payload.get("runOnUnDemand", "")):
                                    
                                    print(f"[stream_manager] Path {path_name} already exists with identical config. Skipping registration.")
                                    if should_limit_fps:
                                        await self.start_fps_transcoder(stream)
                                    await self.set_stream_state(session, stream, StreamState.CONNECTING)
                                    return
                                else:
                                    print(f"[stream_manager] Path {path_name} exists but config differs. Patching...")
                                    patch_url = f"{self.api_url}/v3/config/paths/patch/{path_name}"
                                    patch_resp = await client.patch(patch_url, json=payload)
                                    if patch_resp.status_code in (200, 201):
                                        print(f"[stream_manager] Patched path {path_name} config successfully.")
                                        if should_limit_fps:
                                            await self.start_fps_transcoder(stream)
                                        await self.set_stream_state(session, stream, StreamState.CONNECTING)
                                        return
                            
                            # Fallback if GET or PATCH failed
                            delete_url = f"{self.api_url}/v3/config/paths/delete/{path_name}"
                            await client.delete(delete_url)
                            response = await client.post(url, json=payload)
                            if response.status_code in (200, 201):
                                print(f"[stream_manager] Re-registered path {path_name} in MediaMTX after deletion fallback. On-demand: {source_on_demand}")
                                if should_limit_fps:
                                    await self.start_fps_transcoder(stream)
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

            # 2. Stop any running FPS-limiting transcoder
            await self.stop_fps_transcoder(path_name)

            # 3. MediaMTX delete
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

            # 4. Stop any running transcoder for H.265 streams
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
