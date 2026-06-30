import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .config import settings
from .db import get_session
from .models import Camera, CameraStream, RecordingSegment, StreamState
from .providers import get_playback_recovery_provider
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
    from .stream_manager import _mtx_request
    
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
                    paths_resp = await _mtx_request("GET", f"{settings.mediamtx_api_url}/v3/config/paths/list?page=0&itemsPerPage=10000")
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
                    paths_status_resp = await _mtx_request("GET", f"{settings.mediamtx_api_url}/v3/paths/list?page=0&itemsPerPage=10000")
                    if paths_status_resp.status_code == 200:
                        active_mediamtx_paths_data = paths_status_resp.json().get("items", {})
                        active_mediamtx_paths = {}
                        if isinstance(active_mediamtx_paths_data, dict):
                            active_mediamtx_paths = active_mediamtx_paths_data
                        elif isinstance(active_mediamtx_paths_data, list):
                            for item in active_mediamtx_paths_data:
                                if isinstance(item, dict) and "name" in item:
                                    active_mediamtx_paths[item["name"]] = item
                    else:
                        active_mediamtx_paths = {}
                        print(f"[scheduler] Failed to query active MediaMTX paths: {paths_status_resp.text}")
                except Exception as e:
                    active_mediamtx_paths = {}
                    print(f"[scheduler] Connection error querying active paths: {e}")

                # Transition states based on MediaMTX stream activity
                for stream in active_streams:
                    stream_info = active_mediamtx_paths.get(stream.stream_id)
                    
                    ready_status = stream_info and stream_info.get("ready") is True
                    # A stream is considered ONLINE if its path is active and ready (publisher is streaming)
                    if ready_status:
                        # Stream is actively pulling/pushing packets
                        # Check number of clients (readers)
                        readers = stream_info.get("readers", [])
                        # Filter out internal HLS muxer from viewer counts
                        active_readers = [r for r in readers if isinstance(r, dict) and r.get("type") != "hlsMuxer"] if isinstance(readers, list) else []
                        clients_count = len(active_readers)
                        await RedisManager.set_viewer_count(stream.stream_id, clients_count)
                        
                        # Dynamic codec detection based on active MediaMTX tracks
                        tracks = stream_info.get("tracks") or []
                        if isinstance(tracks, list):
                            has_h265 = any(isinstance(t, str) and t.upper().startswith("H265") for t in tracks)
                            has_h264 = any(isinstance(t, str) and t.upper().startswith("H264") for t in tracks)
                            
                            detected_codec = None
                            if has_h265:
                                detected_codec = "H265"
                            elif has_h264:
                                detected_codec = "H264"
                                
                            if detected_codec and stream.codec != detected_codec:
                                print(f"[scheduler] Dynamically detected {detected_codec} codec for stream {stream.stream_id} (tracks: {tracks}, was: {stream.codec})")
                                stream.codec = detected_codec
                                await session.commit()
                        
                        # Transition to ONLINE
                        if stream.status != StreamState.ONLINE:
                            await stream_manager.set_stream_state(session, stream, StreamState.ONLINE)
                        
                        # Reset pull failure tracking
                        if stream.pull_failed_since is not None:
                            stream.pull_failed_since = None
                            await session.commit()
                    else:
                        # Stream is configured but not active/streaming
                        
                        # Run watchdog recovery loops for AUTO mode
                        if stream.stream_mode == "AUTO":
                            # Push heartbeat watchdog moved to camera_watchdog.edge_push_watchdog_loop()
                            # which handles EDGE_PUSH → RTSP_PULL reversion with proper PATCH-only
                            # MediaMTX updates and the new centralized EDGE_PUSH_HEARTBEAT_TIMEOUT.
                            pass

                        # If they are in CONNECTING or ONLINE but show inactive, they might be offline or connecting
                        if stream.status == StreamState.ONLINE:
                            # For active EDGE_PUSH streams, keep ONLINE if the TCP socket is still connected
                            from .edge_receiver import active_connections
                            if stream.stream_id in active_connections:
                                continue
                            await stream_manager.set_stream_state(session, stream, StreamState.CONNECTING, "Source disconnected")
                        elif stream.status == StreamState.CONNECTING:
                            # Only restart if it has been stuck in CONNECTING for a while (e.g. 60 seconds)
                            # AND (it is always-on OR it has active readers).
                            now = datetime.utcnow()
                            updated_at_naive = stream.updated_at.replace(tzinfo=None) if stream.updated_at else now
                            elapsed = (now - updated_at_naive).total_seconds()
                            
                            if elapsed >= 60:
                                # Determine if it's on-demand
                                is_on_demand = True
                                if stream.always_on:
                                    is_on_demand = False
                                elif stream.last_viewed:
                                    last_viewed_naive = stream.last_viewed.replace(tzinfo=None)
                                    if (now - last_viewed_naive).total_seconds() < 900:
                                        is_on_demand = False
                                
                                # Get readers count if stream_info exists
                                readers_count = 0
                                if stream_info:
                                    readers = stream_info.get("readers", [])
                                    # Filter out internal HLS muxer
                                    active_readers = [r for r in readers if isinstance(r, dict) and r.get("type") != "hlsMuxer"] if isinstance(readers, list) else []
                                    readers_count = len(active_readers)
                                
                                # We only restart if someone is actively trying to watch it and it is stuck
                                if readers_count > 0:
                                    print(f"[scheduler] Stream {stream.stream_id} is stuck connecting (elapsed: {elapsed:.1f}s, readers: {readers_count}). Triggering path restart.")
                                    await stream_manager.restart_stream(session, stream)

                # Remove decommissioned paths from MediaMTX config
                for path_name in mediamtx_paths:
                    if path_name != "all_others" and path_name not in active_stream_ids:
                        # Skip transcoder helper paths
                        if path_name.endswith("_h264"):
                            continue
                        print(f"[scheduler] Decommissioning inactive path: {path_name}")
                        try:
                            await _mtx_request("DELETE", f"{settings.mediamtx_api_url}/v3/config/paths/delete/{path_name}")
                        except Exception as ex:
                            print(f"[scheduler] Failed to delete path config {path_name}: {ex}")

        except Exception as e:
            print(f"[scheduler] Error in camera watchdog loop: {e}")

        await asyncio.sleep(settings.scheduler_interval_seconds)


async def get_file_duration_async(file_path: str, semaphore: asyncio.Semaphore) -> float:
    """Uses ffprobe asynchronously to extract the duration of a video file."""
    import os
    import json
    ffprobe_path = "ffprobe"
    ffmpeg_path = settings.ffmpeg_path
    if "/" in ffmpeg_path or "\\" in ffmpeg_path:
        dirname = os.path.dirname(ffmpeg_path)
        basename = os.path.basename(ffmpeg_path)
        ext = os.path.splitext(basename)[1]
        ffprobe_path = os.path.join(dirname, f"ffprobe{ext}")

    cmd = [
        ffprobe_path,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        file_path
    ]
    async with semaphore:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
            if proc.returncode == 0:
                data = json.loads(stdout.decode())
                duration_str = data.get("format", {}).get("duration")
                if duration_str:
                    return float(duration_str)
        except Exception:
            pass
    return float(settings.segment_time_seconds)

async def scan_filesystem_gaps(stream_id: str, start_ts: float, end_ts: float) -> list[tuple[float, float]]:
    import re
    from pathlib import Path
    
    stream_dir = Path(settings.recording_dir) / stream_id
    segments_to_check = []
    
    if stream_dir.exists():
        for mp4 in stream_dir.rglob("*.mp4"):
            name = mp4.name
            try:
                file_size = mp4.stat().st_size
                if file_size == 0:
                    continue
            except Exception:
                continue

            match = re.search(r"(\d{8})_(\d{6})", name)
            if match:
                try:
                    date_str, time_str = match.groups()
                    dt = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
                    f_start = dt.timestamp()
                    if f_start + settings.segment_time_seconds >= start_ts and f_start <= end_ts:
                        segments_to_check.append({
                            "start_ts": f_start,
                            "path": str(mp4),
                            "size": file_size
                        })
                except Exception:
                    pass
            else:
                match_min = re.search(r"(\d{8})_(\d{4})", name)
                if match_min:
                    try:
                        date_str, time_str = match_min.groups()
                        dt = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M")
                        f_start = dt.timestamp()
                        if f_start + settings.segment_time_seconds >= start_ts and f_start <= end_ts:
                            segments_to_check.append({
                                "start_ts": f_start,
                                "path": str(mp4),
                                "size": file_size
                            })
                    except Exception:
                        pass

    if not segments_to_check:
        return []

    # Query file durations. For files >= 2MB, assume full segment duration to optimize speed.
    semaphore = asyncio.Semaphore(15)
    
    async def get_segment_duration(seg):
        if seg["size"] >= 2 * 1024 * 1024:
            return seg["start_ts"], float(settings.segment_time_seconds)
        dur = await get_file_duration_async(seg["path"], semaphore)
        return seg["start_ts"], dur

    tasks = [get_segment_duration(seg) for seg in segments_to_check]
    results = await asyncio.gather(*tasks)
    
    # Map to segment boundaries
    segments = [(f_start, f_start + dur) for f_start, dur in results]
    segments.sort(key=lambda x: x[0])

    # Filter segments to the requested time window and clip them
    active_segs = []
    for s_start, s_end in segments:
        if s_end > start_ts and s_start < end_ts:
            active_segs.append((max(s_start, start_ts), min(s_end, end_ts)))

    # Detect gaps between files (threshold set to 1.0s to capture all short segments)
    gaps = []
    current_time = start_ts
    
    for s_start, s_end in active_segs:
        if s_start > current_time:
            gap_duration = s_start - current_time
            if gap_duration >= 1.0:
                gaps.append((current_time, s_start))
        current_time = max(current_time, s_end)
        
    if current_time < end_ts:
        gap_duration = end_ts - current_time
        if gap_duration >= 1.0:
            gaps.append((current_time, end_ts))

    return gaps

async def camera_gap_recovery_loop():
    """
    Scans the filesystem for recording gaps in the last 24 hours.
    Downloads the missing chunks from the camera's playback RTSP URL concurrently.
    """
    print("[recovery] Starting recording gap recovery loop...")
    semaphore = asyncio.Semaphore(3) # Limit to 3 concurrent downloads

    # Short delay on startup to allow backend initialization
    await asyncio.sleep(5.0)

    while True:
        try:
            gaps_to_recover = []
            async for session in get_session():
                # Get all active streams that are currently ONLINE
                res = await session.execute(
                    select(CameraStream)
                    .options(selectinload(CameraStream.camera))
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

                    # Query gaps in the last 24 hours directly from the filesystem
                    now = time.time()
                    twenty_four_hours_ago = now - (24 * 3600)
                    gaps = await scan_filesystem_gaps(stream_id, twenty_four_hours_ago, now)

                    # Align gaps to 1-minute segment boundaries (any minute containing a gap should be recovered)
                    seg_time = settings.segment_time_seconds
                    for gap_start, gap_end in gaps:
                        start_minute = int((gap_start // seg_time) * seg_time)
                        end_minute = int((gap_end // seg_time) * seg_time)
                        for temp_start in range(start_minute, end_minute + int(seg_time), int(seg_time)):
                            gap_key = (stream_id, int(temp_start))
                            if gap_key not in attempted_gaps:
                                attempted_gaps.add(gap_key)
                                
                                # Build recovery URL using vendor framework
                                make_val = stream.camera.make if stream.camera else None
                                provider = get_playback_recovery_provider(make_val)
                                next_end = temp_start + seg_time
                                recovery_url = provider.build_playback_url(stream, temp_start, next_end)

                                gaps_to_recover.append({
                                    "stream_id": stream_id,
                                    "recovery_url": recovery_url,
                                    "start_ts": temp_start,
                                    "end_ts": next_end
                                })

            if not gaps_to_recover:
                await asyncio.sleep(60.0)
                continue

            print(f"[recovery] Found {len(gaps_to_recover)} missing segments to recover across all active cameras.")

            async def download_task(task):
                stream_id = task["stream_id"]
                temp_start = task["start_ts"]
                temp_end = task["end_ts"]
                recovery_url = task["recovery_url"]

                dt_start = datetime.fromtimestamp(temp_start)
                day_str = dt_start.strftime("%Y-%m-%d")
                stream_record_dir = Path(settings.recording_dir) / stream_id / day_str
                stream_record_dir.mkdir(parents=True, exist_ok=True)
                filename = f"{dt_start.strftime('%Y%m%d_%H%M')}_recovered.mp4"
                output_path = stream_record_dir / filename

                # Pre-check file existence and completeness
                if output_path.exists() and output_path.stat().st_size > 0:
                    is_complete = False
                    try:
                        dur = await get_file_duration_async(str(output_path), semaphore)
                        if dur >= settings.segment_time_seconds - 5.0:
                            is_complete = True
                    except Exception:
                        pass

                    if is_complete:
                        print(f"[recovery] [{stream_id}] File already exists and is complete, skipping download: {filename}")
                        try:
                            async for insert_session in get_session():
                                parts = Path(output_path).parts
                                relative_path = "/".join(parts[-3:])
                                stmt_check = select(RecordingSegment).where(
                                    RecordingSegment.stream_id == stream_id,
                                    RecordingSegment.file_path == relative_path
                                )
                                res_check = await insert_session.execute(stmt_check)
                                existing_seg = res_check.scalar_one_or_none()
                                if not existing_seg:
                                    new_seg = RecordingSegment(
                                        stream_id=stream_id,
                                        file_path=relative_path,
                                        start_ts=temp_start,
                                        end_ts=temp_end
                                    )
                                    insert_session.add(new_seg)
                                    await insert_session.commit()
                                    print(f"[recovery] [{stream_id}] Indexed existing segment: {filename}")
                        except Exception as e:
                            print(f"[recovery] [{stream_id}] Failed to index existing segment: {e}")
                        return
                    else:
                        print(f"[recovery] [{stream_id}] File exists but is incomplete (duration < 55s), deleting to re-download: {filename}")
                        try:
                            output_path.unlink()
                        except Exception:
                            pass

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
                            # Index the recovered segment immediately
                            try:
                                async for insert_session in get_session():
                                     parts = Path(output_path).parts
                                     relative_path = "/".join(parts[-3:])
                                     stmt_check = select(RecordingSegment).where(
                                         RecordingSegment.stream_id == stream_id,
                                         RecordingSegment.file_path == relative_path
                                     )
                                     res_check = await insert_session.execute(stmt_check)
                                     existing_seg = res_check.scalar_one_or_none()
                                     if not existing_seg:
                                         new_seg = RecordingSegment(
                                             stream_id=stream_id,
                                             file_path=relative_path,
                                             start_ts=temp_start,
                                             end_ts=temp_end
                                         )
                                         insert_session.add(new_seg)
                                         await insert_session.commit()
                                         print(f"[recovery] [{stream_id}] Indexed recovered segment immediately: {filename}")
                            except Exception as index_err:
                                print(f"[recovery] [{stream_id}] Failed to index recovered segment: {index_err}")
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

            # Group tasks by stream_id to process them sequentially per camera (to prevent overloading the camera RTSP playback sessions)
            tasks_by_stream = {}
            for task in gaps_to_recover:
                stream_id = task["stream_id"]
                if stream_id not in tasks_by_stream:
                    tasks_by_stream[stream_id] = []
                tasks_by_stream[stream_id].append(task)

            async def process_stream_queue(stream_tasks):
                for task in stream_tasks:
                    await download_task(task)

            await asyncio.gather(*(process_stream_queue(stream_tasks) for stream_tasks in tasks_by_stream.values()))

        except Exception as e:
            print(f"[recovery] Error in gap recovery loop: {e}")

        # --- Edge Push Filesystem Re-Index ---
        # For edge push streams, scan the recording directory for files on disk
        # that are NOT yet indexed in the database (written by MediaMTX but missed
        # by the webhook due to crashes/timeouts/race conditions).
        try:
            async for session in get_session():
                res = await session.execute(
                    select(CameraStream)
                    .options(selectinload(CameraStream.camera))
                    .join(Camera)
                    .where(Camera.active == True)
                )
                all_streams = list(res.scalars().all())

                for stream in all_streams:
                    rtsp_url = stream.stream_url.strip()
                    # Only process edge push streams (empty or publisher URL)
                    is_push = not rtsp_url or "publisher" in rtsp_url.lower()
                    if not is_push:
                        continue

                    stream_id = stream.stream_id
                    # Scan today's recording directory
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    stream_rec_dir = Path(settings.recording_dir) / stream_id / today_str
                    if not stream_rec_dir.exists():
                        continue

                    # Get all indexed file paths for this stream today
                    now = time.time()
                    day_start_ts = datetime.strptime(today_str, "%Y-%m-%d").timestamp()
                    seg_res = await session.execute(
                        select(RecordingSegment.file_path)
                        .where(RecordingSegment.stream_id == stream_id)
                        .where(RecordingSegment.start_ts >= day_start_ts)
                    )
                    indexed_paths = set(seg_res.scalars().all())

                    # Scan directory for mp4 files not yet indexed
                    reindexed_count = 0
                    for mp4_file in sorted(stream_rec_dir.glob("*.mp4")):
                        parts = mp4_file.parts
                        relative_path = "/".join(parts[-3:])
                        
                        if relative_path in indexed_paths:
                            continue

                        # Skip 0-byte files
                        try:
                            if mp4_file.stat().st_size == 0:
                                continue
                        except Exception:
                            continue

                        # Parse timestamp from filename
                        match = re.search(r"(\d{8})_(\d{6})", mp4_file.name)
                        if match:
                            try:
                                date_str_m, time_str_m = match.groups()
                                dt = datetime.strptime(f"{date_str_m}_{time_str_m}", "%Y%m%d_%H%M%S")
                                start_ts = dt.timestamp()
                                end_ts = start_ts + settings.segment_time_seconds
                            except Exception:
                                end_ts = mp4_file.stat().st_mtime
                                start_ts = end_ts - settings.segment_time_seconds
                        else:
                            # Try 4-digit minutes format
                            match_min = re.search(r"(\d{8})_(\d{4})", mp4_file.name)
                            if match_min:
                                try:
                                    date_str_m, time_str_m = match_min.groups()
                                    dt = datetime.strptime(f"{date_str_m}_{time_str_m}", "%Y%m%d_%H%M")
                                    start_ts = dt.timestamp()
                                    end_ts = start_ts + settings.segment_time_seconds
                                except Exception:
                                    end_ts = mp4_file.stat().st_mtime
                                    start_ts = end_ts - settings.segment_time_seconds
                            else:
                                end_ts = mp4_file.stat().st_mtime
                                start_ts = end_ts - settings.segment_time_seconds

                        # Index the file
                        new_seg = RecordingSegment(
                            stream_id=stream_id,
                            file_path=relative_path,
                            start_ts=start_ts,
                            end_ts=end_ts
                        )
                        session.add(new_seg)
                        reindexed_count += 1

                    if reindexed_count > 0:
                        await session.commit()
                        print(f"[recovery] [{stream_id}] Re-indexed {reindexed_count} unindexed edge push recording files from disk")
                        # Invalidate timeline cache
                        try:
                            from .timeline_service import PlaybackTimelineService
                            await PlaybackTimelineService.invalidate_cache(stream_id, today_str)
                        except Exception:
                            pass

        except Exception as e:
            print(f"[recovery] Error in edge push filesystem re-index: {e}")

        await asyncio.sleep(settings.recovery_interval_seconds)


async def check_and_evict_low_disk_space(session):
    """
    Checks free disk space and deletes the oldest recording segments
    across all cameras/streams if free space drops below threshold.
    """
    if not settings.enable_low_disk_eviction:
        return
    import shutil
    try:
        recording_dir = Path(settings.recording_dir)
        if not recording_dir.exists():
            return
        
        usage = shutil.disk_usage(recording_dir)
        free_gb = usage.free / (1024 ** 3)
        
        if free_gb >= settings.low_disk_space_threshold_gb:
            return
            
        print(f"[cleanup] DISK SPACE CRITICALLY LOW: {free_gb:.2f} GB free (Threshold: {settings.low_disk_space_threshold_gb} GB). Starting emergency eviction...")
        
        # Keep deleting until we hit target_free_space_gb
        while free_gb < settings.target_free_space_gb:
            # Fetch the 50 oldest segments across ALL cameras
            res = await session.execute(
                select(RecordingSegment)
                .order_by(RecordingSegment.start_ts.asc())
                .limit(50)
            )
            old_segments = list(res.scalars().all())
            
            if not old_segments:
                print("[cleanup] Emergency eviction: No more segments found to delete, stopping.")
                break
                
            deleted_count = 0
            for seg in old_segments:
                file_path = Path(seg.file_path)
                if not file_path.is_absolute():
                    file_path = recording_dir / seg.file_path
                try:
                    if file_path.exists():
                        file_path.unlink()
                    deleted_count += 1
                except Exception:
                    pass
                
                await session.delete(seg)
                
            await session.commit()
            print(f"[cleanup] Emergency eviction deleted {deleted_count} oldest segments.")
            
            # Re-check space
            usage = shutil.disk_usage(recording_dir)
            free_gb = usage.free / (1024 ** 3)
            print(f"[cleanup] Free space now: {free_gb:.2f} GB (Target: {settings.target_free_space_gb} GB)")
            
            # Short sleep to prevent CPU spin
            await asyncio.sleep(0.1)
            
    except Exception as e:
        print(f"[cleanup] Error during emergency disk eviction: {e}")


async def camera_archive_cleanup_loop():
    """
    Background loop that deletes recording files and DB references older than the stream's configured archive days.
    """
    print("[cleanup] Starting camera archive cleanup loop...")
    from .config import ENABLE_RETENTION, DEFAULT_RETENTION_DAYS

    while True:
        try:
            if not ENABLE_RETENTION:
                await asyncio.sleep(settings.cleanup_interval_seconds)
                continue

            async for session in get_session():
                # Run emergency low disk space eviction first
                await check_and_evict_low_disk_space(session)

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
                        archive_days = DEFAULT_RETENTION_DAYS
                    else:
                        try:
                            archive_days = int(archive_days)
                        except ValueError:
                            archive_days = DEFAULT_RETENTION_DAYS

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
                            if not file_path.is_absolute():
                                file_path = Path(settings.recording_dir) / seg.file_path
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


async def webrtc_session_watchdog_loop():
    """
    Background watchdog that periodically cleans up WebRTC sessions that are no longer
    active on MediaMTX.
    """
    print("[scheduler] Starting WebRTC session watchdog loop...")
    from .session_manager import webrtc_session_watchdog_cleanup
    while True:
        try:
            async for session in get_session():
                await webrtc_session_watchdog_cleanup(session)
        except Exception as e:
            print(f"[scheduler] Error in WebRTC session watchdog: {e}")
        await asyncio.sleep(10)


async def transcoder_watchdog_loop():
    """
    Background watchdog that periodically checks if any H.265 transcoder processes
    have crashed while viewers are still connected, and auto-restarts them.
    Runs every 15 seconds.
    """
    print("[scheduler] Starting transcoder watchdog loop...")
    from .transcoder import transcoder_manager
    while True:
        try:
            async for session in get_session():
                await transcoder_manager.watchdog_check(session)
        except Exception as e:
            print(f"[scheduler] Error in transcoder watchdog: {e}")
        await asyncio.sleep(15)
