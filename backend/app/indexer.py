from pathlib import Path
from datetime import datetime
from sqlalchemy import select

from .models import RecordingSegment, Camera
from .config import settings


async def index_recordings(session, recording_dir):

    root = Path(recording_dir)

    for stream_dir in root.iterdir():

        if not stream_dir.is_dir():
            continue

        stream_id = stream_dir.name

        cam = await session.execute(
            select(Camera).where(
                Camera.stream_id == stream_id
            )
        )

        camera = cam.scalar_one_or_none()

        camera_name = (
            camera.name
            if camera
            else stream_id
        )

        for mp4 in stream_dir.glob("*.mp4"):

            existing = await session.execute(
                select(RecordingSegment).where(
                    RecordingSegment.file_path == str(mp4)
                )
            )

            if existing.scalar_one_or_none():
                continue

            stat = mp4.stat()

            import re
            match = re.search(r"(\d{8})_(\d{6})", mp4.name)
            if match:
                try:
                    date_str, time_str = match.groups()
                    dt = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
                    start_ts = dt.timestamp()
                    end_ts = start_ts + settings.segment_time_seconds
                except Exception:
                    end_ts = stat.st_mtime
                    start_ts = end_ts - settings.segment_time_seconds
            else:
                end_ts = stat.st_mtime
                start_ts = end_ts - settings.segment_time_seconds

            session.add(
                RecordingSegment(
                    stream_id=stream_id,
                    camera_name=camera_name,
                    file_path=str(mp4),
                    start_ts=start_ts,
                    end_ts=end_ts
                )
            )

    await session.commit()