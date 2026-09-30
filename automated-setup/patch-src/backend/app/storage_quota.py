"""Periodic recording quota; only completed, indexed footage is evicted."""
import asyncio
import time
from pathlib import Path
from sqlalchemy import select
from .config import settings
from .models import RecordingSegment
from .db import get_session


def recording_bytes(root):
    total = 0
    for path in root.rglob('*'):
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        except FileNotFoundError:
            pass
    return total


def delete_recording(root, relative_path):
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError('Recording path is outside storage root')
    try:
        size = path.stat().st_size
        path.unlink()
        return size
    except FileNotFoundError:
        return 0


async def enforce_recording_quota(session):
    limit = settings.recording_storage_limit_gb * 1024 ** 3
    root = Path(settings.recording_dir).resolve()
    if not limit or not root.exists():
        return
    used = await asyncio.to_thread(recording_bytes, root)
    if used <= limit:
        return
    target = int(limit * .9)
    cutoff = time.time() - max(120, settings.segment_time_seconds * 2)
    from .timeline_service import PlaybackTimelineService
    while used > target:
        result = await session.execute(select(RecordingSegment).where(RecordingSegment.end_ts < cutoff).order_by(RecordingSegment.start_ts).limit(200))
        segments = list(result.scalars().all())
        if not segments:
            break
        changed = []
        for segment in segments:
            try:
                removed = await asyncio.to_thread(delete_recording, root, segment.file_path)
            except (OSError, ValueError):
                continue
            used -= removed
            changed.append((segment.stream_id, segment.start_ts))
            await session.delete(segment)
            if used <= target:
                break
        await session.commit()
        for stream_id, start_ts in set(changed):
            await PlaybackTimelineService.invalidate_cache_for_timestamp(stream_id, start_ts)
        if not changed:
            break
    print(f'[storage] Recording usage after quota cleanup: {used / 1024 ** 3:.2f} GiB')


async def recording_quota_loop():
    while True:
        try:
            async for session in get_session():
                await enforce_recording_quota(session)
        except Exception as error:
            print(f'[storage] Quota cleanup failed: {type(error).__name__}')
        await asyncio.sleep(60)
