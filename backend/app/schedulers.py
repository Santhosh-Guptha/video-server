import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
import httpx
from sqlalchemy import select

from .config import settings
from .db import get_session
from .models import Camera, CameraStream, RecordingSegment, StreamState
from .redis_client import RedisManager
from .stream_manager import stream_manager

# In-memory tracking of attempted gap recovery timestamps to prevent infinite retries for failed/offline gaps
# Key format: (stream_id, int(start_ts))
attempted_gaps = set()

async def camera_scheduler_loop():
    """
    Background watchdog that ensures active camera streams are configured in MediaMTX
    and monitors their status, caching updates in Redis.
    """
    print("[scheduler] Starting camera status watchdog loop...")
    
    async with httpx.AsyncClient() as client:
        while True:
            try:
                # 1. Sync camera stream paths from Database to MediaMTX configuration
                async for session in get_session():
                    # Fetch all active camera streams
                    res = await session.execute(
                        select(CameraStream)
                        .join(Camera)
                        .where(Camera.active == True)
                    )
                    active_streams = list(res.scalars().all())
                    active_stream_ids = {stream.stream_id for stream in active_streams}

                    # Fetch existing configuration paths in MediaMTX
                    try:
                        paths_resp = await client.get(f"{settings.mediamtx_api_url}/v3/config/paths/list")
                        if paths_resp.status_code == 200:
                            mediamtx_paths_data = paths_resp.json().get("items", {})
                            mediamtx_paths = set()
                            if isinstance(mediamtx_paths_data, dict):
                                mediamtx_paths = set(mediamtx_paths_data.keys())
                            elif isinstance(mediamtx_paths_data, list):
                                mediamtx_paths = {item.get("name") for item in mediamtx_paths_data if isinstance(item, dict) and "name" in item}
                        else:
                            mediamtx_paths = set()
                            print(f"[scheduler] Failed to query MediaMTX paths list: {paths_resp.text}")
                    except Exception as e:
                        mediamtx_paths = set()
                        print(f"[scheduler] Connection error querying MediaMTX paths: {e}")

                    # Sync paths: Add missing ones
                    for stream in active_streams:
                        if stream.stream_id not in mediamtx_paths:
                            print(f"[scheduler] Registering missing stream path: {stream.stream_id}")
                            await stream_manager.add_stream(session, stream)

                    # 2. Query active streams status to update state machine
                    try:
                        streams_resp = await client.get(f"{settings.mediamtx_api_url}/v3/streams/list")
                        if streams_resp.status_code == 200:
                            active_mediamtx_streams_data = streams_resp.json().get("items", {})
                            active_mediamtx_streams = {}
                            if isinstance(active_mediamtx_streams_data, dict):
                                active_mediamtx_streams = active_mediamtx_streams_data
                            elif isinstance(active_mediamtx_streams_data, list):
                                for item in active_mediamtx_streams_data:
                                    if isinstance(item, dict) and "name" in item:
                                        active_mediamtx_streams[item["name"]] = item
                        else:
                            active_mediamtx_streams = {}
                            print(f"[scheduler] Failed to query active MediaMTX streams: {streams_resp.text}")
                    except Exception as e:
                        active_mediamtx_streams = {}
                        print(f"[scheduler] Connection error querying active streams: {e}")

                    # Transition states based on MediaMTX stream activity
                    for stream in active_streams:
                        stream_info = active_mediamtx_streams.get(stream.stream_id)
                        
                        if stream_info:
                            # Stream is actively pulling/pushing packets
                            # Check number of clients (readers)
                            readers = stream_info.get("readers", [])
                            clients_count = len(readers) if isinstance(readers, list) else 0
                            await RedisManager.set_viewer_count(stream.stream_id, clients_count)
                            
                            # Transition to ONLINE
                            if stream.status != StreamState.ONLINE:
                                await stream_manager.set_stream_state(session, stream, StreamState.ONLINE)
                        else:
                            # Stream is configured but not active/streaming
                            # If they are in CONNECTING or ONLINE but show inactive, they might be offline or reconnecting
                            if stream.status == StreamState.ONLINE:
                                await stream_manager.set_stream_state(session, stream, StreamState.RECONNECTING, "Source disconnected")
                            elif stream.status == StreamState.RECONNECTING:
                                # If stuck in reconnecting, restart path configuration to force a clean retry
                                print(f"[scheduler] Stream {stream.stream_id} is stuck reconnecting. Triggering path restart.")
                                await stream_manager.restart_stream(session, stream)

                    # Remove decommissioned paths from MediaMTX config
                    for path_name in mediamtx_paths:
                        if path_name != "all_others" and path_name not in active_stream_ids:
                            print(f"[scheduler] Decommissioning inactive path: {path_name}")
                            try:
                                await client.delete(f"{settings.mediamtx_api_url}/v3/config/paths/delete/{path_name}")
                            except Exception as ex:
                                print(f"[scheduler] Failed to delete path config {path_name}: {ex}")

            except Exception as e:
                print(f"[scheduler] Error in camera watchdog loop: {e}")

            await asyncio.sleep(settings.scheduler_interval_seconds)


async def camera_gap_recovery_loop():
    """
    Scans the database for recording gaps in the last 24 hours.
    Downloads the missing chunks from the camera's playback RTSP URL concurrently.
    """
    print("[recovery] Starting recording gap recovery loop...")
    semaphore = asyncio.Semaphore(3) # Limit to 3 concurrent downloads

    while True:
        try:
            await asyncio.sleep(settings.recovery_interval_seconds)

            gaps_to_recover = []
            async for session in get_session():
                # Get all active streams that are currently ONLINE
                res = await session.execute(
                    select(CameraStream)
                    .join(Camera)
                    .where(Camera.active == True)
                    .where(CameraStream.status == StreamState.ONLINE)
                )
                active_streams = list(res.scalars().all())

                for stream in active_streams:
                    stream_id = stream.stream_id
                    rtsp_url = stream.stream_url.strip()
                    # Skip edge push or invalid RTSP urls
                    if not rtsp_url.startswith(("rtsp://", "rtsps://")):
                        continue

                    # Query segments in the last 24 hours
                    now = time.time()
                    twenty_four_hours_ago = now - (24 * 3600)
                    seg_res = await session.execute(
                        select(RecordingSegment)
                        .where(RecordingSegment.stream_id == stream_id)
                        .where(RecordingSegment.start_ts >= twenty_four_hours_ago)
                        .order_by(RecordingSegment.start_ts.asc())
                    )
                    segments = list(seg_res.scalars().all())

                    if not segments:
                        continue

                    # Check for gaps between consecutive segments
                    for i in range(len(segments) - 1):
                        current_seg = segments[i]
                        next_seg = segments[i + 1]
                        
                        gap_start = current_seg.end_ts
                        gap_end = next_seg.start_ts
                        gap_duration = gap_end - gap_start

                        if gap_duration >= (1.2 * settings.segment_time_seconds):
                            temp_start = gap_start
                            while temp_start + settings.segment_time_seconds <= gap_end:
                                gap_key = (stream_id, int(temp_start))
                                if gap_key not in attempted_gaps:
                                    attempted_gaps.add(gap_key)
                                    gaps_to_recover.append({
                                        "stream_id": stream_id,
                                        "rtsp_url": rtsp_url,
                                        "raw_json": stream.camera.name, # Using camera name or default
                                        "start_ts": temp_start,
                                        "end_ts": temp_start + settings.segment_time_seconds
                                    })
                                temp_start += settings.segment_time_seconds

            if not gaps_to_recover:
                continue

            print(f"[recovery] Found {len(gaps_to_recover)} missing segments to recover across all active cameras.")

            async def download_task(task):
                stream_id = task["stream_id"]
                temp_start = task["start_ts"]
                temp_end = task["end_ts"]
                base_rtsp = task["rtsp_url"]

                dt_start = datetime.fromtimestamp(temp_start)
                dt_end = datetime.fromtimestamp(temp_end)

                start_iso = dt_start.strftime("%Y%m%dT%H%M%SZ")
                end_iso = dt_end.strftime("%Y%m%dT%H%M%SZ")
                start_time_local = dt_start.strftime("%Y_%m_%d_%H_%M_%S")
                end_time_local = dt_end.strftime("%Y_%m_%d_%H_%M_%S")

                recovery_url = settings.recovery_rtsp_template.format(
                    rtsp_url=base_rtsp,
                    start_iso=start_iso,
                    end_iso=end_iso,
                    start_time_local=start_time_local,
                    end_time_local=end_time_local
                )

                day_str = dt_start.strftime("%Y-%m-%d")
                stream_record_dir = Path(settings.recording_dir) / stream_id / day_str
                stream_record_dir.mkdir(parents=True, exist_ok=True)
                filename = f"{dt_start.strftime('%Y%m%d_%H%M%S')}_recovered.mp4"
                output_path = stream_record_dir / filename

                async with semaphore:
                    print(f"[recovery] [{stream_id}] Downloading gap segment: {filename}...")
                    cmd = [
                        settings.ffmpeg_path,
                        "-hide_banner",
                        "-loglevel", "warning",
                        "-rtsp_transport", "tcp",
                        "-i", recovery_url,
                        "-t", str(settings.segment_time_seconds),
                        "-c", "copy",
                        str(output_path)
                    ]

                    try:
                        proc = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        await asyncio.wait_for(proc.wait(), timeout=settings.segment_time_seconds * 2)
                        if proc.returncode == 0:
                            print(f"[recovery] [{stream_id}] Successfully recovered gap segment: {filename}")
                        else:
                            print(f"[recovery] [{stream_id}] FFmpeg failed with exit code {proc.returncode} for clip: {filename}")
                            if output_path.exists():
                                output_path.unlink()
                    except asyncio.TimeoutError:
                        print(f"[recovery] [{stream_id}] Timeout downloading gap clip: {filename}")
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        if output_path.exists():
                            output_path.unlink()
                    except Exception as e:
                        print(f"[recovery] [{stream_id}] Error running FFmpeg for recovery: {e}")
                        if output_path.exists():
                            output_path.unlink()

            await asyncio.gather(*(download_task(task) for task in gaps_to_recover))

        except Exception as e:
            print(f"[recovery] Error in gap recovery loop: {e}")


async def camera_archive_cleanup_loop():
    """
    Background loop that deletes recording files and DB references older than the stream's configured archive days.
    """
    print("[cleanup] Starting camera archive cleanup loop...")
    while True:
        try:
            async for session in get_session():
                # Query all camera streams
                res = await session.execute(select(CameraStream).join(Camera))
                streams = list(res.scalars().all())

                for stream in streams:
                    # Parse archiveDays from parent camera raw_json if present
                    try:
                        raw = json.loads(stream.camera.raw_json) if hasattr(stream.camera, "raw_json") else {}
                    except Exception:
                        raw = {}

                    archive_days = raw.get("archiveDays")
                    if archive_days is None:
                        continue

                    try:
                        archive_days = int(archive_days)
                    except ValueError:
                        continue

                    if archive_days <= 0:
                        continue

                    cutoff_ts = time.time() - (archive_days * 24 * 3600)
                    
                    # Query segments older than the cutoff
                    seg_res = await session.execute(
                        select(RecordingSegment)
                        .where(RecordingSegment.stream_id == stream.stream_id)
                        .where(RecordingSegment.end_ts < cutoff_ts)
                    )
                    old_segments = list(seg_res.scalars().all())

                    if old_segments:
                        print(f"[cleanup] Found {len(old_segments)} old segments to clean up for stream '{stream.stream_id}' (Keep duration: {archive_days} days)")
                        
                        deleted_count = 0
                        for seg in old_segments:
                            # 1. Remove physical file
                            file_path = Path(seg.file_path)
                            try:
                                if file_path.exists():
                                    file_path.unlink()
                                deleted_count += 1
                            except Exception as e:
                                print(f"[cleanup] Failed to delete file {seg.file_path}: {e}")

                            # 2. Remove DB segment record
                            await session.delete(seg)

                        await session.commit()
                        print(f"[cleanup] Successfully deleted {deleted_count} files and database records for '{stream.stream_id}'")

                        # 3. Clean up empty date subdirectories
                        try:
                            cam_rec_dir = Path(settings.recording_dir) / stream.stream_id
                            if cam_rec_dir.exists():
                                for sub in cam_rec_dir.iterdir():
                                    if sub.is_dir() and not any(sub.iterdir()):
                                        sub.rmdir()
                                        print(f"[cleanup] Removed empty directory: {sub}")
                        except Exception as ex:
                            print(f"[cleanup] Failed to clean up empty subdirectories: {ex}")

                # Clean up empty parent directories for decommissioned streams
                try:
                    for parent_dir in [Path(settings.recording_dir), Path(settings.hls_dir)]:
                        if parent_dir.exists():
                            for stream_dir in parent_dir.iterdir():
                                if stream_dir.is_dir():
                                    stream_id = stream_dir.name
                                    # Check if active in database
                                    stream_exists = any(stream.stream_id == stream_id for stream in streams)
                                    if not stream_exists:
                                        # Delete folder if empty
                                        def is_dir_empty_recursive(d: Path) -> bool:
                                            for item in d.iterdir():
                                                if item.is_file():
                                                    return False
                                                if item.is_dir() and not is_dir_empty_recursive(item):
                                                    return False
                                            return True
                                        
                                        if is_dir_empty_recursive(stream_dir):
                                            import shutil
                                            shutil.rmtree(stream_dir)
                                            print(f"[cleanup] Removed empty camera directory for non-existent stream: {stream_dir}")
                except Exception as ex:
                    print(f"[cleanup] Error cleaning empty camera directories: {ex}")

        except Exception as e:
            print(f"[cleanup] Error in archive cleanup loop: {e}")

        await asyncio.sleep(settings.cleanup_interval_seconds)
