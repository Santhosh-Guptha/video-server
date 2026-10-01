import copy
import json
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


class OperationsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(control, 'state', {'server': {'live': True, 'recording': True}, 'cameras': {}}),
                        patch.object(control, 'FILE', Path(self.temp.name)/'policy.json'),
                        patch.object(control, 'aliases', {}), patch.object(control, 'sources', {}),
                        patch.object(ops, 'inventory', AsyncMock(return_value=[SimpleNamespace(id='one', name='One'), SimpleNamespace(id='two', name='Two')])),
                        patch.object(ops, 'read_controls', AsyncMock(return_value={'ok': True}))]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    async def test_unknown_camera_rejects_entire_batch_without_partial_changes(self):
        with self.assertRaises(HTTPException) as error:
            await ops.bulk_action(ops.BulkAction(camera_ids=['one', 'missing'], action='ignore', revision=0), None)
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(control.state['cameras'], {})
        self.assertFalse(control.FILE.exists())

    async def test_bulk_retention_is_atomic_and_does_not_restart_streams(self):
        with patch.object(ops, 'reconcile', AsyncMock()) as apply:
            await ops.bulk_action(ops.BulkAction(camera_ids=['one', 'two'], action='retention', retention_days=7, revision=0), None)
            apply.assert_not_called()
        saved = json.loads(control.FILE.read_text())
        self.assertEqual(saved['revision'], 1)
        self.assertEqual(saved['cameras']['one']['retention_days'], 7)
        self.assertEqual(saved['cameras']['two']['retention_days'], 7)
        self.assertEqual(saved['activity'][0]['action'], 'bulk.retention')
        with self.assertRaises(HTTPException) as error:
            await ops.bulk_action(ops.BulkAction(camera_ids=['one'], action='ignore', revision=0), None)
        self.assertEqual(error.exception.status_code, 409)
        self.assertNotIn('ignored', control.state['cameras']['one'])

    def test_failed_disk_write_does_not_publish_new_state(self):
        original = copy.deepcopy(control.state)
        updated = copy.deepcopy(original)
        updated['server']['live'] = False
        with patch.object(control, 'write_state', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                control.commit(updated, 'server.policy', 'server')
        self.assertEqual(control.state, original)

    async def test_policy_export_excludes_credentials_urls_notes_and_deletion_markers(self):
        control.state['server']['upstream_url'] = 'https://example.test/?token=secret'
        control.state['cameras']['one'] = {'ignored': True, 'site': 'North', 'notes': 'private notes', 'stream_url': 'rtsp://user:secret@host', 'deleted_before': 123}
        result = await ops.backup_policy(None)
        text = json.dumps(result)
        for value in ['secret', 'private notes', 'deleted_before', 'upstream_url', 'stream_url']:
            self.assertNotIn(value, text)
        self.assertEqual(result['cameras'][0]['policy']['site'], 'North')

    def test_metadata_and_batch_validation(self):
        value = ops.CameraMetadata(tags=[' East ', 'East', '', 'gate'], revision=0)
        self.assertEqual(value.tags, ['East', 'gate'])
        with self.assertRaises(ValidationError):
            ops.BulkAction(camera_ids=['one', 'one'], action='ignore', revision=0)
        with self.assertRaises(ValidationError):
            ops.CameraMetadata(tags=['x'*41], revision=0)

    def test_duplicate_names_cannot_bypass_ignored_camera_policy(self):
        for key in ['one', 'two']:
            control.register(SimpleNamespace(id=key, server_camera_id=key, name='Entrance', source_camera_id=key, streams=[SimpleNamespace(stream_id=key+'_HD', stream_url='')]))
        control.state['cameras']['one'] = {'ignored': True}
        self.assertFalse(control.allowed('Entrance'))
        self.assertFalse(control.allowed('one_HD'))
        self.assertTrue(control.allowed('two_HD'))

    async def test_runtime_failure_keeps_saved_intent_and_reports_failure(self):
        with patch.object(ops, 'apply_runtime', AsyncMock(side_effect=RuntimeError('offline'))):
            with self.assertRaises(HTTPException) as error:
                await ops.bulk_action(ops.BulkAction(camera_ids=['one'], action='ignore', revision=0), None)
        self.assertEqual(error.exception.status_code, 503)
        self.assertTrue(control.state['cameras']['one']['ignored'])
        self.assertEqual(control.state['runtime']['status'], 'failed')

    async def test_restore_roundtrip_preserves_deletion_cutoff_and_source_url(self):
        control.state['server']['upstream_url'] = 'https://source.test/api'
        control.state['cameras']['one'] = {'ignored': True, 'deleted_before': 123, 'notes': 'Keep me'}
        backup = await ops.backup_policy(None)
        control.state['cameras']['one']['ignored'] = False
        request = ops.RestoreRequest(document=backup, revision=0, confirm=True)
        with patch.object(ops, 'reconcile', AsyncMock()):
            await ops.restore_backup(request, None)
        self.assertTrue(control.state['cameras']['one']['ignored'])
        self.assertEqual(control.state['cameras']['one']['deleted_before'], 123)
        self.assertEqual(control.state['cameras']['one']['notes'], 'Keep me')
        self.assertEqual(control.state['server']['upstream_url'], 'https://source.test/api')

    async def test_restore_requires_confirmation_and_rejects_unknown_ids(self):
        backup = await ops.backup_policy(None)
        with self.assertRaises(HTTPException) as error:
            await ops.restore_backup(ops.RestoreRequest(document=backup, revision=0), None)
        self.assertEqual(error.exception.status_code, 400)
        backup['cameras'][0]['id'] = 'missing'
        with self.assertRaises(HTTPException) as error:
            await ops.restore_backup(ops.RestoreRequest(document=backup, revision=0, confirm=True), None)
        self.assertEqual(error.exception.status_code, 409)
        self.assertFalse(control.FILE.exists())
