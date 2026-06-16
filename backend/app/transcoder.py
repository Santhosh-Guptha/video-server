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
import os
import signal
from datetime import datetime
from typing import Dict, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import StreamTranscoder


class _TranscoderState:
    """In-memory state for a single running transcoder."""
    __slots__ = ("process", "stream_id", "shutdown_task")

    def __init__(self, process: asyncio.subprocess.Process, stream_id: str):
        self.process = process
        self.stream_id = stream_id
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
    async def ensure_transcoder(cls, stream_id: str, db_session: AsyncSession) -> str:
        """
        Ensures a shared transcoder is running for the given H.265 stream.
        Returns the transcoded path name (e.g. '{stream_id}_h264').
        Raises an HTTPException-compatible error if capacity is exceeded.
        """
        h264_path = f"{stream_id}_h264"

        async with cls._lock:
            state = cls._transcoders.get(stream_id)

            # If transcoder exists and is running, cancel any pending shutdown and reuse
            if state and state.process.returncode is None:
                if state.shutdown_task and not state.shutdown_task.done():
                    state.shutdown_task.cancel()
                    state.shutdown_task = None
                    print(f"[transcoder] Cancelled pending shutdown for {stream_id}")
                # Increment viewer count in DB
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
            cls._transcoders[stream_id] = _TranscoderState(process, stream_id)

            # Update DB
            await cls._upsert_db_record(stream_id, process.pid, "ACTIVE", db_session, viewer_count=1)

            print(f"[transcoder] Started transcoder for {stream_id} (PID: {process.pid}, "
                  f"codec: {settings.transcoder_vcodec}, active: {len(cls._transcoders)})")

            return h264_path

    @classmethod
    async def register_viewer_disconnect(cls, stream_id: str, db_session: AsyncSession) -> None:
        """
        Called when a viewer disconnects from an H.265 stream.
        Decrements the viewer count and schedules shutdown if count reaches 0.
        """
        async with cls._lock:
            viewer_count = await cls._update_db_viewer_count(stream_id, db_session, delta=-1)

            if viewer_count <= 0:
                state = cls._transcoders.get(stream_id)
                if state and (not state.shutdown_task or state.shutdown_task.done()):
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
            # Double-check: process still alive and no new viewers
            if state.process.returncode is None:
                await cls._kill_process(state.process, stream_id)
                del cls._transcoders[stream_id]

            # Clean up MediaMTX h264 path
            await cls._delete_h264_path(stream_id)

        # Update DB outside lock
        from .db import get_session as _get_session
        async for session in _get_session():
            await cls._upsert_db_record(stream_id, None, "INACTIVE", session, viewer_count=0)
            break

        print(f"[transcoder] Stopped transcoder for {stream_id} after {delay_seconds}s grace period. "
              f"Active: {len(cls._transcoders)}")

    @classmethod
    async def watchdog_check(cls, db_session: AsyncSession) -> None:
        """
        Periodic watchdog (called every 15s by scheduler).
        Checks if any transcoder process has crashed while viewers are still connected.
        Auto-restarts crashed transcoders.
        """
        async with cls._lock:
            dead_streams = []
            for stream_id, state in cls._transcoders.items():
                if state.process.returncode is not None:
                    dead_streams.append(stream_id)

            for stream_id in dead_streams:
                state = cls._transcoders.pop(stream_id)
                exit_code = state.process.returncode

                # Check DB for viewer count
                res = await db_session.execute(
                    select(StreamTranscoder).where(StreamTranscoder.stream_id == stream_id)
                )
                record = res.scalar_one_or_none()
                viewer_count = record.viewer_count if record else 0

                if viewer_count > 0:
                    print(f"[transcoder] WATCHDOG: Transcoder for {stream_id} crashed "
                          f"(exit code: {exit_code}), {viewer_count} viewer(s) still connected. "
                          f"Restarting...")
                    try:
                        h264_path = f"{stream_id}_h264"
                        await cls._register_h264_path(stream_id, h264_path)
                        process = await cls._spawn_ffmpeg(stream_id, h264_path)
                        cls._transcoders[stream_id] = _TranscoderState(process, stream_id)
                        await cls._upsert_db_record(
                            stream_id, process.pid, "ACTIVE", db_session,
                            viewer_count=viewer_count
                        )
                        print(f"[transcoder] WATCHDOG: Restarted transcoder for {stream_id} "
                              f"(new PID: {process.pid})")
                    except Exception as e:
                        print(f"[transcoder] WATCHDOG: Failed to restart transcoder for "
                              f"{stream_id}: {e}")
                        await cls._upsert_db_record(
                            stream_id, None, "CRASHED", db_session,
                            viewer_count=viewer_count, error_message=str(e)
                        )
                else:
                    print(f"[transcoder] WATCHDOG: Transcoder for {stream_id} exited "
                          f"(exit code: {exit_code}), no viewers. Cleaning up.")
                    await cls._delete_h264_path(stream_id)
                    await cls._upsert_db_record(
                        stream_id, None, "INACTIVE", db_session, viewer_count=0
                    )

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
        """Spawns an FFmpeg process to transcode from the raw RTSP stream to H.264."""
        input_url = f"rtsp://127.0.0.1:8554/{stream_id}"
        output_url = f"rtsp://127.0.0.1:8554/{h264_path}"

        cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-i", input_url,
            "-c:v", settings.transcoder_vcodec,
            "-preset", settings.transcoder_preset,
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-f", "rtsp",
            output_url
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
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
