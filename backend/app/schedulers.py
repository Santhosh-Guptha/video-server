import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from sqlalchemy import select

from .config import settings
from .db import get_session
from .models import Camera, RecordingSegment
from .media import media_manager

# In-memory tracking of attempted gap recovery timestamps to prevent infinite retries for failed/offline gaps
# Key format: (stream_id, int(start_ts))
attempted_gaps = set()

async def camera_scheduler_loop():
    """
    Background watchdog that ensures active cameras are continuously recording/streaming
    independently of frontend live view client connections.
    """
    print("[scheduler] Starting camera status watchdog loop...")
    while True:
        try:
            async for session in get_session():
                # Fetch all active cameras
                res = await session.execute(
                    select(Camera).where(Camera.active == True)
                )
                active_cameras = list(res.scalars().all())
                active_stream_ids = {cam.stream_id for cam in active_cameras}

                # 1. Start streams for active cameras if not running
                for camera in active_cameras:
                    stream_id = camera.stream_id
                    existing = media_manager.streams.get(stream_id)
                    is_running = (
                        existing
                        and existing.proc
                        and existing.proc.returncode is None
                    )

                    if not is_running:
                        try:
                            raw = json.loads(camera.raw_json)
                            username = raw.get("username")
                            password = raw.get("password")
                            rtsp_url = camera.rtsp_url.strip()

                            if not rtsp_url.startswith(("rtsp://", "rtsps://")):
                                rtsp_url = f"rtsp://{rtsp_url}"

                            if username and password:
                                protocol, rest = rtsp_url.split("://", 1)
                                encoded_username = quote(str(username), safe="")
                                encoded_password = quote(str(password), safe="")
                                rtsp_url = f"{protocol}://{encoded_username}:{encoded_password}@{rest}"

                            # Validate if camera is online/reachable before creating directories or launching FFmpeg
                            from urllib.parse import urlparse
                            import socket

                            def check_rtsp_reachable(url: str) -> bool:
                                try:
                                    parsed = urlparse(url)
                                    host = parsed.hostname
                                    port = parsed.port or 554
                                    if not host:
                                        return False
                                    with socket.create_connection((host, port), timeout=2.0):
                                        return True
                                except Exception:
                                    return False

                            is_reachable = await asyncio.to_thread(check_rtsp_reachable, rtsp_url)
                            if not is_reachable:
                                print(f"[scheduler] Camera '{stream_id}' is offline/unreachable. Skipping startup to avoid empty folder creation.")
                                continue

                            # Pre-create day-wise folders for today and tomorrow to avoid FFmpeg write errors
                            from datetime import timedelta
                            today_str = datetime.now().strftime("%Y-%m-%d")
                            tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                            stream_record_dir = Path(settings.recording_dir) / stream_id
                            (stream_record_dir / today_str).mkdir(parents=True, exist_ok=True)
                            (stream_record_dir / tomorrow_str).mkdir(parents=True, exist_ok=True)

                            print(f"[scheduler] Stream '{stream_id}' is not running. Starting background recorder...")
                            await media_manager.start_rtsp_stream(
                                stream_id,
                                rtsp_url,
                                settings.recording_dir,
                                settings.hls_dir
                            )
                        except Exception as e:
                            print(f"[scheduler] Failed to start stream for camera '{stream_id}': {e}")

                # 2. Stop streams for cameras that are no longer active
                running_stream_ids = list(media_manager.streams.keys())
                for sid in running_stream_ids:
                    if sid not in active_stream_ids:
                        print(f"[scheduler] Stopping stream '{sid}' because it is no longer marked active in database")
                        try:
                            await media_manager.stop(sid)
                        except Exception as e:
                            print(f"[scheduler] Failed to stop stream '{sid}': {e}")

        except Exception as e:
            print(f"[scheduler] Error in camera watchdog loop: {e}")

        await asyncio.sleep(settings.scheduler_interval_seconds)


async def camera_gap_recovery_loop():
    """
    Scans the database for recording gaps (e.g. missing 60s segments) in the last 24 hours.
    Downloads the missing chunks from the camera's playback RTSP URL concurrently.
    """
    print("[recovery] Starting recording gap recovery loop...")
    semaphore = asyncio.Semaphore(3) # Limit to 3 concurrent downloads to prevent CPU/network overload

    while True:
        try:
            # Let the system stabilize first or sleep
            await asyncio.sleep(settings.recovery_interval_seconds)

            # 1. Gather all gaps to recover using a short-lived DB session
            gaps_to_recover = []
            async for session in get_session():
                # Get all active cameras
                res = await session.execute(
                    select(Camera).where(Camera.active == True)
                )
                active_cameras = list(res.scalars().all())

                for camera in active_cameras:
                    stream_id = camera.stream_id
                    rtsp_url = camera.rtsp_url.strip()
                    if not rtsp_url:
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

                        # If gap is larger than 1.2 * segment_time_seconds, attempt recovery
                        if gap_duration >= (1.2 * settings.segment_time_seconds):
                            temp_start = gap_start
                            while temp_start + settings.segment_time_seconds <= gap_end:
                                gap_key = (stream_id, int(temp_start))
                                if gap_key not in attempted_gaps:
                                    attempted_gaps.add(gap_key)
                                    gaps_to_recover.append({
                                        "stream_id": stream_id,
                                        "rtsp_url": rtsp_url,
                                        "raw_json": camera.raw_json,
                                        "start_ts": temp_start,
                                        "end_ts": temp_start + settings.segment_time_seconds
                                    })
                                temp_start += settings.segment_time_seconds

            if not gaps_to_recover:
                continue

            print(f"[recovery] Found {len(gaps_to_recover)} missing segments to recover across all active cameras.")

            # 2. Define download task helper
            async def download_task(task):
                stream_id = task["stream_id"]
                temp_start = task["start_ts"]
                temp_end = task["end_ts"]
                raw_json = task["raw_json"]
                base_rtsp = task["rtsp_url"]

                dt_start = datetime.fromtimestamp(temp_start)
                dt_end = datetime.fromtimestamp(temp_end)

                start_iso = dt_start.strftime("%Y%m%dT%H%M%SZ")
                end_iso = dt_end.strftime("%Y%m%dT%H%M%SZ")
                start_time_local = dt_start.strftime("%Y_%m_%d_%H_%M_%S")
                end_time_local = dt_end.strftime("%Y_%m_%d_%H_%M_%S")

                try:
                    raw = json.loads(raw_json)
                except Exception:
                    raw = {}
                username = raw.get("username")
                password = raw.get("password")
                
                if not base_rtsp.startswith(("rtsp://", "rtsps://")):
                    base_rtsp = f"rtsp://{base_rtsp}"
                if username and password:
                    try:
                        protocol, rest = base_rtsp.split("://", 1)
                        encoded_username = quote(str(username), safe="")
                        encoded_password = quote(str(password), safe="")
                        base_rtsp = f"{protocol}://{encoded_username}:{encoded_password}@{rest}"
                    except Exception:
                        pass

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
                        # Wait for download to finish (giving it 2x segment time limit)
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

            # 3. Run all download tasks concurrently with semaphore limit
            await asyncio.gather(*(download_task(task) for task in gaps_to_recover))

        except Exception as e:
            print(f"[recovery] Error in gap recovery loop: {e}")


async def camera_archive_cleanup_loop():
    """
    Background loop that deletes recording files and DB references older than the camera's configured archive days.
    """
    print("[cleanup] Starting camera archive cleanup loop...")
    while True:
        try:
            async for session in get_session():
                # Query all cameras
                res = await session.execute(select(Camera))
                cameras = list(res.scalars().all())

                for camera in cameras:
                    try:
                        raw = json.loads(camera.raw_json)
                    except Exception:
                        continue

                    # Check if archiveDays is configured
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
                        .where(RecordingSegment.stream_id == camera.stream_id)
                        .where(RecordingSegment.end_ts < cutoff_ts)
                    )
                    old_segments = list(seg_res.scalars().all())

                    if old_segments:
                        print(f"[cleanup] Found {len(old_segments)} old segments to clean up for camera '{camera.stream_id}' (Keep duration: {archive_days} days)")
                        
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
                        print(f"[cleanup] Successfully deleted {deleted_count} files and database records for '{camera.stream_id}'")

                        # 3. Clean up empty date subdirectories
                        try:
                            cam_rec_dir = Path(settings.recording_dir) / camera.stream_id
                            if cam_rec_dir.exists():
                                for sub in cam_rec_dir.iterdir():
                                    if sub.is_dir() and not any(sub.iterdir()):
                                        sub.rmdir()
                                        print(f"[cleanup] Removed empty directory: {sub}")
                        except Exception as ex:
                            print(f"[cleanup] Failed to clean up empty subdirectories: {ex}")

                # Clean up empty parent camera directories for inactive/unreachable/deleted cameras
                try:
                    for parent_dir in [Path(settings.recording_dir), Path(settings.hls_dir)]:
                        if parent_dir.exists():
                            for stream_dir in parent_dir.iterdir():
                                if stream_dir.is_dir():
                                    stream_id = stream_dir.name
                                    existing = media_manager.streams.get(stream_id)
                                    is_running = (
                                        existing
                                        and existing.proc
                                        and existing.proc.returncode is None
                                    )
                                    if not is_running:
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
                                            print(f"[cleanup] Removed empty camera directory for non-streaming camera: {stream_dir}")
                except Exception as ex:
                    print(f"[cleanup] Error cleaning empty camera directories: {ex}")

        except Exception as e:
            print(f"[cleanup] Error in archive cleanup loop: {e}")

        await asyncio.sleep(settings.cleanup_interval_seconds)
