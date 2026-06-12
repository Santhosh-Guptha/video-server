import os
import re
import asyncio
from pathlib import Path
from datetime import datetime
from sqlalchemy import select, delete

from .models import RecordingSegment, Camera
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
                results.append({
                    "stream_id": stream_id,
                    "file_path": str(mp4),
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

    # 4. Fetch camera names map in a single query
    cam_res = await session.execute(select(Camera.stream_id, Camera.name))
    camera_names = {row[0]: row[1] for row in cam_res.all()}

    # 5. Insert new recording segments
    added_count = 0
    for item in scanned_files:
        path_str = item["file_path"]
        if path_str in indexed_paths:
            continue

        stream_id = item["stream_id"]
        camera_name = camera_names.get(stream_id, stream_id)
        
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
            end_ts = item["mtime"]
            start_ts = end_ts - settings.segment_time_seconds

        session.add(
            RecordingSegment(
                stream_id=stream_id,
                camera_name=camera_name,
                file_path=path_str,
                start_ts=start_ts,
                end_ts=end_ts
            )
        )
        added_count += 1

    if added_count > 0:
        await session.commit()
        print(f"[indexer] Indexed {added_count} new recording segments.")