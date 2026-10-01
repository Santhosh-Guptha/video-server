import asyncio
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app import control_policy as policy
from app import server_control as api
from app.db import Base
from app.models import RecordingSegment
from app.rtsp_budget import RTSPBudget, recovery_work, RTSPCapacityError
from fastapi import HTTPException


class ControlTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state_patch = patch.object(policy, 'state', {'server': {'live': True, 'recording': True}, 'cameras': {}})
        self.state_patch.start()
        self.alias_patch = patch.object(policy, 'aliases', {'cam_HD': 'camera', 'cam': 'camera', 'cam_HD_h264': 'camera'})
        self.alias_patch.start()

    def tearDown(self):
        self.alias_patch.stop()
        self.state_patch.stop()

    def test_ignore_survives_save_and_source_registration(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(policy, 'FILE', Path(directory)/'policy.json'):
            policy.state['cameras']['camera'] = {'ignored': True}
            policy.save()
            policy.register(SimpleNamespace(id='camera', server_camera_id='cam', name='Camera', source_camera_id=1, streams=[SimpleNamespace(stream_id='cam_HD', stream_url='')]))
            for purpose in ['live', 'recording', 'connect']:
                self.assertFalse(policy.allowed('cam_HD', purpose))
            self.assertTrue(json.loads(policy.FILE.read_text())['cameras']['camera']['ignored'])

    def test_live_and_recording_are_independent_and_global_stop_preserves_choices(self):
        policy.state['cameras']['camera'] = {'live': False, 'recording': True}
        self.assertFalse(policy.allowed('cam_HD', 'live'))
        self.assertTrue(policy.allowed('cam_HD', 'connect'))
        policy.state['server']['recording'] = False
        self.assertFalse(policy.allowed('cam_HD', 'connect'))
        policy.state['server']['recording'] = True
        self.assertTrue(policy.allowed('cam_HD', 'recording'))
        self.assertFalse(policy.allowed('cam_HD', 'live'))

    async def test_dynamic_recreation_of_ignored_path_is_denied(self):
        policy.state['cameras']['camera'] = {'ignored': True}
        client = AsyncMock()
        budget = RTSPBudget(lambda: 6, 'http://mtx', client)
        budget.paths = {}
        response = await budget.mutate('POST', 'http://mtx/v3/config/paths/add/cam_HD', json={'source': 'rtsp://camera/live'})
        self.assertEqual(response.status_code, 403)
        client.request.assert_not_called()
        client.post.assert_not_called()

    async def test_registration_uses_profile_path_instead_of_parent_alias(self):
        from app.stream_manager import StreamManager
        import httpx
        manager = StreamManager('http://mtx')
        camera = SimpleNamespace(id='camera', server_camera_id='cam', name='Camera')
        stream = SimpleNamespace(stream_id='cam_HD', camera=camera, camera_id='camera', stream_url='rtsp://camera/live', stream_mode='AUTO')
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = object()
        session.execute.return_value = result
        with patch('app.stream_manager.RedisManager.acquire_lock', AsyncMock(return_value=True)), patch('app.stream_manager.RedisManager.release_lock', AsyncMock()), patch('app.stream_manager.should_record_stream', AsyncMock(return_value=True)), patch('app.stream_manager.EventBus.publish', AsyncMock()), patch.object(manager, '_post', AsyncMock(return_value=httpx.Response(200))) as post, patch.object(manager, 'set_stream_state', AsyncMock()):
            await manager.add_stream(session, stream)
            self.assertEqual(post.call_args.args[0], '/v3/config/paths/add/cam_HD')

    async def test_stopping_recording_cancels_recovery_and_blocks_new_jobs(self):
        entered = asyncio.Event()
        async def work():
            async with recovery_work('cam_HD'):
                entered.set()
                await asyncio.Event().wait()
        task = asyncio.create_task(work())
        await entered.wait()
        policy.state['cameras']['camera'] = {'recording': False}
        await policy.cancel_recovery('camera')
        self.assertTrue(task.cancelled())
        with self.assertRaises(RTSPCapacityError):
            async with recovery_work('cam_HD'):
                self.fail('Disabled recovery must not start')

    async def test_scoped_deletion_protects_recent_files_and_other_camera(self):
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                camera = SimpleNamespace(id='camera', streams=[SimpleNamespace(stream_id='cam_HD')])
                config = SimpleNamespace(recording_dir=directory, segment_time_seconds=60)
                async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                    for stream, name, age in [('cam_HD', 'old.mp4', 600), ('cam_HD', 'recent.mp4', 10), ('other', 'other.mp4', 600)]:
                        (root/name).write_bytes(b'video')
                        session.add(RecordingSegment(stream_id=stream, file_path=name, start_ts=time.time()-age-60, end_ts=time.time()-age))
                    await session.commit()
                    with patch.object(api, 'inventory', AsyncMock(return_value=[camera])), patch.object(api, 'settings', config), patch.object(policy, 'FILE', root/'policy.json'), patch('app.timeline_service.PlaybackTimelineService.invalidate_cache_for_timestamp', AsyncMock()):
                        request = api.DeleteRequest(camera_id='camera', before=time.time(), confirm=True)
                        with self.assertRaises(HTTPException) as error:
                            await api.delete_recordings(request, session)
                        self.assertEqual(error.exception.status_code, 409)
                        policy.state['cameras']['camera'] = {'recording': False}
                        preview = await api.preview_delete(request, session)
                        self.assertEqual(preview['segments'], 1)
                        result = await api.delete_recordings(request, session)
                        self.assertEqual(result['deleted'], 1)
                        self.assertFalse((root/'old.mp4').exists())
                        self.assertTrue((root/'recent.mp4').exists())
                        self.assertTrue((root/'other.mp4').exists())
                        self.assertGreater(policy.recording_after('cam_HD'), 0)
                        self.assertEqual(len(list((await session.execute(select(RecordingSegment))).scalars())), 2)
        finally:
            await engine.dispose()
