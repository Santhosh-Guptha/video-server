import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from pydantic import ValidationError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app import operations as ops, control_policy as control
from app.camera_playback import ArchiveSettings, archive_settings


class ArchiveSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_persistence_effective_state_and_stale_rejection(self):
        camera = SimpleNamespace(id='one', name='One', make=None, active=True, streams=[SimpleNamespace(stream_id='one_HD', profile_type=SimpleNamespace(value='MAIN'), resolution='1920x1080')])
        with tempfile.TemporaryDirectory() as directory, patch.object(control, 'FILE', Path(directory)/'policy.json'), patch.object(control, 'state', {'server': {'live': True, 'recording': True}, 'cameras': {}}), patch.object(ops, 'inventory', AsyncMock(return_value=[camera])), patch.object(ops.settings, 'enable_sd_card_on_demand', True):
            result = await ops.update_archive('one', ops.ArchiveUpdate(revision=0, adapter='unv', stream_id='one_HD', max_minutes=3), None)
            self.assertEqual(result['revision'], 1)
            self.assertTrue(result['effective_enabled'])
            self.assertTrue(result['adapter_available'])
            self.assertEqual(archive_settings('one').max_minutes, 3)
            self.assertTrue(control.FILE.exists())
            with self.assertRaises(HTTPException) as error:
                await ops.update_archive('one', ops.ArchiveUpdate(revision=0), None)
            self.assertEqual(error.exception.status_code, 409)
            with self.assertRaises(HTTPException) as error:
                await ops.update_archive('one', ops.ArchiveUpdate(revision=1, stream_id='other_camera_HD'), None)
            self.assertEqual(error.exception.status_code, 422)
            self.assertEqual(control.revision(), 1)
            backup = await ops.backup_policy(None)
            self.assertEqual(backup['cameras'][0]['policy']['archive']['adapter'], 'unv')
            control.state['server']['live'] = False
            control.state['server']['recording'] = False
            self.assertFalse((await ops.read_archive('one', None))['effective_enabled'])

    def test_strict_bounds_and_unknown_fields(self):
        for value in [{'max_minutes': 16}, {'max_minutes': 1.5}, {'first_data_timeout': 0}, {'idle_timeout': 61}, {'adapter': 'anything'}, {'password': 'secret'}]:
            with self.assertRaises(ValidationError):
                ArchiveSettings(**value)

    async def test_camera_disabled_setting_enforced_before_connecting(self):
        from unittest.mock import MagicMock
        from app import main
        stream = SimpleNamespace(camera_id='one', stream_url='rtsp://host/c1/live')
        camera = SimpleNamespace(id='one', name='One', make='UNV', active=True)
        session = MagicMock()
        session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=camera)))
        with patch.object(control, 'state', {'server': {}, 'cameras': {'one': {'archive': {'enabled': False}}}}), patch.object(main.settings, 'enable_sd_card_on_demand', True), patch('app.webrtc.resolve_stream_by_identifier', AsyncMock(return_value=stream)), patch.object(main, 'spawn_media_process', AsyncMock()) as spawn:
            with self.assertRaises(HTTPException) as error:
                await main.download_sd_card_stream('one', 100, 200, session, source='camera', adapter='unv')
            self.assertEqual(error.exception.status_code, 403)
            spawn.assert_not_called()
