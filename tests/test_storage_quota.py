import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app import storage_quota as quota
from app.db import Base
from app.models import RecordingSegment

class StorageQuotaTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_completed_files_and_indexes_evicted_recent_preserved(self):
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = SimpleNamespace(recording_dir=directory, recording_storage_limit_gb=1, segment_time_seconds=60)
                async with async_sessionmaker(engine)() as session:
                    for name, age in [('old.mp4',600),('middle.mp4',400),('active.mp4',10)]:
                        with (root/name).open('wb') as output:
                            output.truncate(600 * 1024 ** 2)
                        session.add(RecordingSegment(stream_id='camera',file_path=name,start_ts=time.time()-age-60,end_ts=time.time()-age))
                    await session.commit()
                    with patch.object(quota,'settings',config), patch('app.timeline_service.PlaybackTimelineService.invalidate_cache_for_timestamp',new_callable=AsyncMock):
                        await quota.enforce_recording_quota(session)
                    self.assertFalse((root/'old.mp4').exists())
                    self.assertFalse((root/'middle.mp4').exists())
                    self.assertTrue((root/'active.mp4').exists())
                    self.assertEqual(list((await session.execute(select(RecordingSegment.file_path))).scalars()),['active.mp4'])
        finally:
            await engine.dispose()

    def test_deletion_rejects_paths_outside_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.assertRaises(ValueError):
                quota.delete_recording(root,'../unrelated.mp4')
