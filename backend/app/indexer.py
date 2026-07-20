import os
import re
import asyncio
from pathlib import Path
from datetime import datetime
from sqlalchemy import select, delete

from .models import RecordingSegment, CameraStream
from .config import settings

def scan_files_sync(recording_dir):
    """
    Synchronous filesystem walk to gather files and statistics.
    Executed in a background thread to prevent blocking the async event loop.
    """
    root = Path(recording_dir)
    if not root.exists():
        return []
    results = []
    for stream_dir in root.iterdir():
        if not stream_dir.is_dir():
            continue
        stream_id = stream_dir.name
        for mp4 in stream_dir.rglob("*.mp4"):
            try:
                stat = mp4.stat()
                # Store relative path (stream_id/date/filename) to be dynamically resolvable
                parts = mp4.parts
                rel_path = "/".join(parts[-3:])
                results.append({
                    "stream_id": stream_id,
                    "file_path": rel_path,
                    "mtime": stat.st_mtime,
                    "name": mp4.name
                })
            except Exception:
                pass
    return results

async def index_recordings(session, recording_dir):
    # 1. Scan filesystem in a background thread to keep event loop free
    scanned_files = await asyncio.to_thread(scan_files_sync, recording_dir)
    
    # 2. Get all currently indexed file paths in a single query
    res = await session.execute(select(RecordingSegment.file_path))
    indexed_paths = set(res.scalars().all())

    # 3. Clean up orphaned database entries in bulk chunks
    scanned_paths = {item["file_path"] for item in scanned_files}
    orphaned_paths = indexed_paths - scanned_paths
    if orphaned_paths:
        print(f"[indexer] Removing {len(orphaned_paths)} orphaned database segments...")
        orphaned_list = list(orphaned_paths)
        for i in range(0, len(orphaned_list), 500):
            chunk = orphaned_list[i:i+500]
            await session.execute(
                delete(RecordingSegment).where(RecordingSegment.file_path.in_(chunk))
            )
        await session.commit()

    # 4. Fetch active cameras and their streams to build camera ID -> stream ID mapping
    from .models import Camera
    from sqlalchemy.orm import selectinload
    from sqlalchemy import func
    
    stmt = (
        select(Camera)
        .options(selectinload(Camera.streams))
        .where(Camera.active == True)
    )
    res = await session.execute(stmt)
    active_cameras = res.scalars().all()
    
    camera_id_to_stream_id = {}
    for cam in active_cameras:
        cam_id = cam.server_camera_id or cam.name
        if not cam_id:
            continue
        
        best_stream = None
        if cam.streams:
            pref = settings.preferred_profile.upper() if hasattr(settings, "preferred_profile") else "HD"
            if pref in ("NORMAL", "SUB"):
                target = "SUB"
                fallback = "MAIN"
            else:
                target = "MAIN"
                fallback = "SUB"
            
            def sort_key(s):
                profile_upper = (s.profile_type.value if hasattr(s.profile_type, 'value') else str(s.profile_type)).upper()
                is_preferred = (profile_upper == target or 
                                (target == "SUB" and profile_upper == "NORMAL") or
                                (target == "MAIN" and profile_upper == "HD"))
                is_fallback = (profile_upper == fallback or 
                               (fallback == "SUB" and profile_upper == "NORMAL") or
                               (fallback == "MAIN" and profile_upper == "HD"))
                if is_preferred:
                    return 0
                elif is_fallback:
                    return 1
                return 2
            sorted_streams = sorted(cam.streams, key=sort_key)
            best_stream = sorted_streams[0]
            
        if best_stream:
            camera_id_to_stream_id[cam_id.lower()] = best_stream.stream_id

    # 5. Insert new recording segments
    added_count = 0
    for item in scanned_files:
        path_str = item["file_path"]
        if path_str in indexed_paths:
            continue

        folder_cam_id = item["stream_id"]
        matched_stream_id = camera_id_to_stream_id.get(folder_cam_id.lower())
        
        # Support fallback to legacy stream_id folder names
        if not matched_stream_id:
            stream_res = await session.execute(
                select(CameraStream).where(func.lower(CameraStream.stream_id) == folder_cam_id.lower())
            )
            found_stream = stream_res.scalar_one_or_none()
            if found_stream:
                matched_stream_id = found_stream.stream_id
                
        if not matched_stream_id:
            continue
            
        # Re-assign the matched database stream_id to be stored in the database segment row
        stream_id = matched_stream_id
        
        # Try dual-timestamp format first: YYYYMMDD_HHMMSS_HHMMSS
        match_dual = re.search(r"(\d{8})_(\d{6})_(\d{6})", item["name"])
        if match_dual:
            try:
                date_str, start_time_str, end_time_str = match_dual.groups()
                dt_start = datetime.strptime(f"{date_str}_{start_time_str}", "%Y%m%d_%H%M%S")
                dt_end = datetime.strptime(f"{date_str}_{end_time_str}", "%Y%m%d_%H%M%S")
                start_ts = dt_start.timestamp()
                end_ts = dt_end.timestamp()
            except Exception:
                end_ts = item["mtime"]
                start_ts = end_ts - settings.segment_time_seconds
        else:
            match = re.search(r"(\d{8})_(\d{6})", item["name"])
            if match:
                try:
                    date_str, time_str = match.groups()
                    dt = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
                    start_ts = dt.timestamp()
                    end_ts = start_ts + settings.segment_time_seconds
                except Exception:
                    end_ts = item["mtime"]
                    start_ts = end_ts - settings.segment_time_seconds
            else:
                # Try 4-digit minutes format
                match_min = re.search(r"(\d{8})_(\d{4})", item["name"])
                if match_min:
                    try:
                        date_str, time_str = match_min.groups()
                        dt = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M")
                        start_ts = dt.timestamp()
                        end_ts = start_ts + settings.segment_time_seconds
                    except Exception:
                        end_ts = item["mtime"]
                        start_ts = end_ts - settings.segment_time_seconds
                else:
                    end_ts = item["mtime"]
                    start_ts = end_ts - settings.segment_time_seconds

        session.add(
            RecordingSegment(
                stream_id=stream_id,
                file_path=path_str,
                start_ts=start_ts,
                end_ts=end_ts
            )
        )
        added_count += 1

    if added_count > 0:
        await session.commit()
        print(f"[indexer] Indexed {added_count} new recording segments.")