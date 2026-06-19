"""
TranscoderManager: Centralized on-demand H.265 -> H.264 transcoding service.

Architecture:
- One shared FFmpeg transcoder process per H.265 camera stream.
- Spawned on-demand when the first viewer connects.
- Reused by all subsequent viewers of the same stream.
- Gracefully terminated after a configurable grace period (default 60s)
  once all viewers disconnect.
- Capacity-limited to prevent CPU exhaustion on the server.
"""

import asyncio
from datetime import datetime
from typing import Dict, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import StreamTranscoder


class _TranscoderState:
    """In-memory state for a single running transcoder."""
    __slots__ = ("process", "stream_id", "startup_time", "active_viewers", "shutdown_task")

    def __init__(self, process: asyncio.subprocess.Process, stream_id: str, active_viewers: int = 1):
        self.process = process
        self.stream_id = stream_id
        self.startup_time = datetime.utcnow()
        self.active_viewers = active_viewers
        self.shutdown_task: Optional[asyncio.Task] = None


class TranscoderManager:
    """Manages shared FFmpeg transcoder processes for H.265 streams."""

    _transcoders: Dict[str, _TranscoderState] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def active_count(cls) -> int:
        """Returns the number of currently running transcoders."""
        return len(cls._transcoders)

    @classmethod
    async def ensure_transcoder(
        cls,
        stream_id: str,
        db_session: Optional[AsyncSession] = None,
        increment_viewer: bool = True
    ) -> str:
        """
        Ensures a shared transcoder is running for the given H.265 stream.
        Returns the transcoded path name (e.g. '{stream_id}_h264').
        """
        h264_path = f"{stream_id}_h264"

        async with cls._lock:
            state = cls._transcoders.get(stream_id)

            # If transcoder exists and is running, cancel any pending shutdown and reuse
            if state and state.process.returncode is None:
                if increment_viewer:
                    if state.shutdown_task and not state.shutdown_task.done():
                        state.shutdown_task.cancel()
                        state.shutdown_task = None
                        print(f"[transcoder] Cancelled pending shutdown for {stream_id}")
                    state.active_viewers += 1

                    # Update DB viewer count if db_session is provided
                    if db_session:
                        await cls._update_db_viewer_count(stream_id, db_session, delta=1)
                return h264_path

            # Capacity check
            if len(cls._transcoders) >= settings.max_active_transcoders:
                raise TranscoderCapacityError(
                    f"Maximum active transcoders ({settings.max_active_transcoders}) reached. "
                    f"Cannot start transcoder for {stream_id}."
                )

            # Register the h264 publisher path in MediaMTX
            await cls._register_h264_path(stream_id, h264_path)

            # Spawn FFmpeg transcoder process
            process = await cls._spawn_ffmpeg(stream_id, h264_path)
            
            initial_viewers = 1 if increment_viewer else 0
            cls._transcoders[stream_id] = _TranscoderState(process, stream_id, active_viewers=initial_viewers)

            # Update DB record if db_session is provided
            if db_session:
                await cls._upsert_db_record(stream_id, process.pid, "ACTIVE", db_session, viewer_count=initial_viewers)

            print(f"[transcoder] Started transcoder for {stream_id} (PID: {process.pid}, "
                  f"active: {len(cls._transcoders)})")

            if initial_viewers == 0:
                # If started statelessly (HLS), schedule a delayed shutdown to check readers
                cls._transcoders[stream_id].shutdown_task = asyncio.create_task(
                    cls._delayed_shutdown(stream_id, settings.transcoder_grace_period_seconds)
                )

            # Wait up to 5 seconds for the transcoded stream to become ready in MediaMTX
            # This prevents race conditions where the browser requests the stream before FFmpeg starts publishing
            ready = False
            async with httpx.AsyncClient() as client:
                for _ in range(25): # 25 * 0.2s = 5s
                    try:
                        resp = await client.get(f"{settings.mediamtx_api_url}/v3/paths/list?page=0&itemsPerPage=10000", timeout=1.0)
                        if resp.status_code == 200:
                            items = resp.json().get("items", {})
                            path_info = None
                            if isinstance(items, dict):
                                path_info = items.get(h264_path)
                            elif isinstance(items, list):
                                for item in items:
                                    if isinstance(item, dict) and item.get("name") == h264_path:
                                        path_info = item
                                        break
                            if path_info and path_info.get("ready") is True:
                                ready = True
                                break
                    except Exception as e:
                        print(f"[transcoder] Error checking readiness for {h264_path}: {e}")
                    await asyncio.sleep(0.2)
            
            if ready:
                print(f"[transcoder] Transcoded stream {h264_path} is ready and publishing.")
            else:
                print(f"[transcoder] Warning: Transcoded stream {h264_path} did not start publishing within 5s.")

            return h264_path

    @classmethod
    async def register_viewer_disconnect(cls, stream_id: str, db_session: Optional[AsyncSession] = None) -> None:
        """
        Called when a viewer disconnects from an H.265 stream.
        Decrements the viewer count and schedules shutdown if count reaches 0.
        """
        async with cls._lock:
            state = cls._transcoders.get(stream_id)
            if not state:
                return

            state.active_viewers = max(0, state.active_viewers - 1)
            print(f"[transcoder] Viewer disconnected from {stream_id}. Active viewers: {state.active_viewers}")

            if db_session:
                await cls._update_db_viewer_count(stream_id, db_session, delta=-1)

            if state.active_viewers <= 0:
                if not state.shutdown_task or state.shutdown_task.done():
                    grace = settings.transcoder_grace_period_seconds
                    print(f"[transcoder] No viewers for {stream_id}. "
                          f"Scheduling shutdown in {grace}s.")
                    state.shutdown_task = asyncio.create_task(
                        cls._delayed_shutdown(stream_id, grace)
                    )

    @classmethod
    async def _delayed_shutdown(cls, stream_id: str, delay_seconds: int) -> None:
        """Waits for the grace period, then stops the transcoder if no new viewers appeared."""
        try:
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            return

        async with cls._lock:
            state = cls._transcoders.get(stream_id)
            if not state:
                return
            
            # Check if there are active readers on the h264 path in MediaMTX
            h264_path = f"{stream_id}_h264"
            has_readers = False
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{settings.mediamtx_api_url}/v3/paths/list?page=0&itemsPerPage=10000", timeout=5.0)
                    if resp.status_code == 200:
                        paths_data = resp.json().get("items", {})
                        path_info = None
                        if isinstance(paths_data, dict):
                            path_info = paths_data.get(h264_path)
                        elif isinstance(paths_data, list):
                            for item in paths_data:
                                if isinstance(item, dict) and item.get("name") == h264_path:
                                    path_info = item
                                    break
                        if path_info:
                            readers = path_info.get("readers") or []
                            # Filter out internal HLS muxer which is always present
                            active_readers = [r for r in readers if isinstance(r, dict) and r.get("type") != "hlsMuxer"]
                            if len(active_readers) > 0:
                                has_readers = True
            except Exception as e:
                print(f"[transcoder] Error checking readers for {h264_path} during shutdown: {e}")

            # Double-check: process still alive and no new viewers (in-memory or MediaMTX readers)
            if state.active_viewers <= 0 and not has_readers:
                if state.process.returncode is None:
                    await cls._kill_process(state.process, stream_id)
                await cls._delete_h264_path(stream_id)
                cls._transcoders.pop(stream_id, None)
                print(f"[transcoder] Stopped transcoder for {stream_id} after {delay_seconds}s grace period.")
            else:
                if has_readers:
                    print(f"[transcoder] Postponing shutdown for {stream_id} because MediaMTX has active readers on {h264_path}")
                else:
                    print(f"[transcoder] Postponing shutdown for {stream_id} because active_viewers count is {state.active_viewers}")
                # Reschedule shutdown check since we still have viewers/readers
                state.shutdown_task = asyncio.create_task(
                    cls._delayed_shutdown(stream_id, delay_seconds)
                )

    @classmethod
    async def watchdog_check(cls, db_session: Optional[AsyncSession] = None) -> None:
        """
        Periodic watchdog (called every 15s by scheduler).
        Checks if any transcoder process has crashed while viewers are still connected.
        Auto-restarts crashed transcoders.
        """
        # Fetch active MediaMTX paths to check readers
        mediamtx_paths = {}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{settings.mediamtx_api_url}/v3/paths/list?page=0&itemsPerPage=10000", timeout=5.0)
                if resp.status_code == 200:
                    items = resp.json().get("items", {})
                    if isinstance(items, dict):
                        mediamtx_paths = items
                    elif isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict) and "name" in item:
                                mediamtx_paths[item["name"]] = item
        except Exception as e:
            print(f"[transcoder] Watchdog error fetching MediaMTX paths: {e}")

        async with cls._lock:
            dead_streams = []
            for stream_id, state in cls._transcoders.items():
                if state.process.returncode is not None:
                    dead_streams.append(stream_id)

            for stream_id in dead_streams:
                state = cls._transcoders.pop(stream_id)
                exit_code = state.process.returncode
                viewer_count = state.active_viewers
                
                h264_path = f"{stream_id}_h264"
                path_info = mediamtx_paths.get(h264_path)
                has_readers = False
                if path_info:
                    readers = path_info.get("readers") or []
                    # Filter out internal HLS muxer which is always present
                    active_readers = [r for r in readers if isinstance(r, dict) and r.get("type") != "hlsMuxer"]
                    has_readers = len(active_readers) > 0

                if viewer_count > 0 or has_readers:
                    print(f"[transcoder] WATCHDOG: Transcoder for {stream_id} crashed "
                          f"(exit code: {exit_code}), viewers/readers active. Restarting...")
                    try:
                        await cls._register_h264_path(stream_id, h264_path)
                        process = await cls._spawn_ffmpeg(stream_id, h264_path)
                        new_state = _TranscoderState(process, stream_id, active_viewers=max(viewer_count, 1 if has_readers else 0))
                        cls._transcoders[stream_id] = new_state
                        
                        if db_session:
                            await cls._upsert_db_record(
                                stream_id, process.pid, "ACTIVE", db_session,
                                viewer_count=new_state.active_viewers
                            )
                        print(f"[transcoder] WATCHDOG: Restarted transcoder for {stream_id} "
                              f"(new PID: {process.pid})")
                    except Exception as e:
                        print(f"[transcoder] WATCHDOG: Failed to restart transcoder for "
                              f"{stream_id}: {e}")
                        if db_session:
                            await cls._upsert_db_record(
                                stream_id, None, "CRASHED", db_session,
                                viewer_count=viewer_count, error_message=str(e)
                            )
                else:
                    print(f"[transcoder] WATCHDOG: Transcoder for {stream_id} exited "
                          f"(exit code: {exit_code}), no viewers/readers. Cleaning up.")
                    await cls._delete_h264_path(stream_id)
                    if db_session:
                        await cls._upsert_db_record(
                            stream_id, None, "INACTIVE", db_session, viewer_count=0
                        )

    @classmethod
    async def stop(cls, stream_id: str) -> None:
        """Alias for stop_transcoder as required by stream_manager."""
        await cls.stop_transcoder(stream_id)

    @classmethod
    async def stop_transcoder(cls, stream_id: str) -> None:
        """Force-stop a specific transcoder (e.g. when camera is decommissioned)."""
        async with cls._lock:
            state = cls._transcoders.pop(stream_id, None)
            if state:
                if state.shutdown_task and not state.shutdown_task.done():
                    state.shutdown_task.cancel()
                if state.process.returncode is None:
                    await cls._kill_process(state.process, stream_id)
                await cls._delete_h264_path(stream_id)
                print(f"[transcoder] Force-stopped transcoder for {stream_id}")

    @classmethod
    async def stop_all(cls) -> None:
        """Clean shutdown of all active transcoders (called on FastAPI shutdown)."""
        async with cls._lock:
            for stream_id, state in list(cls._transcoders.items()):
                if state.shutdown_task and not state.shutdown_task.done():
                    state.shutdown_task.cancel()
                if state.process.returncode is None:
                    await cls._kill_process(state.process, stream_id)
                await cls._delete_h264_path(stream_id)
            count = len(cls._transcoders)
            cls._transcoders.clear()
        print(f"[transcoder] Stopped all {count} active transcoders on shutdown.")

    # ─── Internal helpers ──────────────────────────────────────────────

    @classmethod
    async def _spawn_ffmpeg(cls, stream_id: str, h264_path: str) -> asyncio.subprocess.Process:
        """Spawns an FFmpeg process to transcode from the raw RTSP stream to H.264.
        
        Codec, preset, and tune are read from vms_policy (TRANSCODER_VCODEC,
        TRANSCODER_PRESET, TRANSCODER_TUNE) so they can be changed in one place.
        """
        from .config import TRANSCODER_VCODEC, TRANSCODER_PRESET, TRANSCODER_TUNE
        cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-i", f"rtsp://127.0.0.1:8554/{stream_id}",
            "-an",
            "-c:v", TRANSCODER_VCODEC,
            "-preset", TRANSCODER_PRESET,
            "-tune", TRANSCODER_TUNE,
            "-profile:v", "baseline",
            "-pix_fmt", "yuv420p",
            "-g", "25",
            "-keyint_min", "25",
            "-sc_threshold", "0",
            "-bf", "0",
            "-f", "rtsp",
            "-rtsp_transport", "tcp",
            f"rtsp://127.0.0.1:8554/{h264_path}"
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )

        async def log_stderr(proc):
            try:
                stderr_data = await proc.stderr.read()
                if stderr_data:
                    print(f"[transcoder] FFmpeg {stream_id} stderr:\n{stderr_data.decode().strip()}")
            except Exception as e:
                print(f"[transcoder] Error reading FFmpeg stderr for {stream_id}: {e}")

        asyncio.create_task(log_stderr(process))
        return process

    @classmethod
    async def _kill_process(cls, process: asyncio.subprocess.Process, stream_id: str) -> None:
        """Gracefully terminate an FFmpeg process."""
        try:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        except ProcessLookupError:
            pass
        except Exception as e:
            print(f"[transcoder] Error killing process for {stream_id}: {e}")

    @classmethod
    async def _register_h264_path(cls, stream_id: str, h264_path: str) -> None:
        """Registers the temporary h264 publisher path in MediaMTX."""
        payload = {
            "source": "publisher",
            "sourceOnDemand": False,
            "record": False,  # Do NOT record the transcoded stream
        }
        async with httpx.AsyncClient() as client:
            try:
                url = f"{settings.mediamtx_api_url}/v3/config/paths/add/{h264_path}"
                resp = await client.post(url, json=payload, timeout=5.0)
                if resp.status_code == 400 or "already exists" in resp.text:
                    patch_url = f"{settings.mediamtx_api_url}/v3/config/paths/patch/{h264_path}"
                    await client.patch(patch_url, json=payload, timeout=5.0)
            except Exception as e:
                print(f"[transcoder] Error registering MediaMTX path {h264_path}: {e}")

    @classmethod
    async def _delete_h264_path(cls, stream_id: str) -> None:
        """Removes the temporary h264 publisher path from MediaMTX."""
        h264_path = f"{stream_id}_h264"
        async with httpx.AsyncClient() as client:
            try:
                url = f"{settings.mediamtx_api_url}/v3/config/paths/delete/{h264_path}"
                await client.delete(url, timeout=5.0)
            except Exception as e:
                print(f"[transcoder] Error deleting MediaMTX path {h264_path}: {e}")

    @classmethod
    async def _upsert_db_record(
        cls,
        stream_id: str,
        pid: Optional[int],
        status: str,
        db_session: AsyncSession,
        viewer_count: int = 0,
        error_message: Optional[str] = None
    ) -> None:
        """Insert or update the stream_transcoders record."""
        try:
            res = await db_session.execute(
                select(StreamTranscoder).where(StreamTranscoder.stream_id == stream_id)
            )
            record = res.scalar_one_or_none()

            now = datetime.utcnow()
            if not record:
                record = StreamTranscoder(
                    stream_id=stream_id,
                    pid=pid,
                    status=status,
                    started_at=now if status == "ACTIVE" else None,
                    stopped_at=now if status != "ACTIVE" else None,
                    viewer_count=viewer_count,
                    error_message=error_message
                )
                db_session.add(record)
            else:
                record.pid = pid
                record.status = status
                record.viewer_count = viewer_count
                record.error_message = error_message
                if status == "ACTIVE":
                    record.started_at = now
                    record.stopped_at = None
                else:
                    record.stopped_at = now

            await db_session.commit()
        except Exception as e:
            await db_session.rollback()
            print(f"[transcoder] DB error updating transcoder record for {stream_id}: {e}")

    @classmethod
    async def _update_db_viewer_count(
        cls,
        stream_id: str,
        db_session: AsyncSession,
        delta: int
    ) -> int:
        """Atomically increment/decrement viewer count in DB. Returns new count."""
        try:
            res = await db_session.execute(
                select(StreamTranscoder).where(StreamTranscoder.stream_id == stream_id)
            )
            record = res.scalar_one_or_none()
            if record:
                record.viewer_count = max(0, record.viewer_count + delta)
                await db_session.commit()
                return record.viewer_count
        except Exception as e:
            await db_session.rollback()
            print(f"[transcoder] DB error updating viewer count for {stream_id}: {e}")
        return 0


class TranscoderCapacityError(Exception):
    """Raised when the maximum number of active transcoders is reached."""
    pass


# Global transcoder manager alias/instance
transcoder_manager = TranscoderManager()
