import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.camera_playback import validate_interval, camera_url


class CameraPlaybackTests(unittest.IsolatedAsyncioTestCase):
    def test_invalid_or_unbounded_intervals(self):
        for start, end in [(1, 1), (2, 1), (-1, 1), (0, 901), (float('nan'), 3), (0, float('inf'))]:
            with self.assertRaises(HTTPException):
                validate_interval(start, end)
        validate_interval(0, 900)

    def test_channel_and_epoch_preserved(self):
        stream = SimpleNamespace(stream_url='rtsp://user:secret@host:554/c7/s0/live')
        self.assertEqual(camera_url('UNV', stream, 100, 200), 'rtsp://user:secret@host:554/c7/b100/e200/replay/')

    def test_unknown_make_or_channel_not_guessed(self):
        for make, url in [('Unknown', 'rtsp://host/c1'), ('UNV', 'rtsp://host/live'), ('UNV', 'http://host/c1')]:
            with self.assertRaises(HTTPException):
                camera_url(make, SimpleNamespace(stream_url=url), 100, 200)

    async def test_camera_only_skips_recordings_and_releases_process(self):
        from app import main
        camera = SimpleNamespace(id='camera', name='Private camera', make='UNV', active=True)
        stream = SimpleNamespace(camera_id='camera', stream_url='rtsp://user:secret@host/c7/live')
        session = MagicMock()
        session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=camera)))
        process = MagicMock(returncode=None)
        process.stdout.read = AsyncMock(side_effect=[b'first', b''])
        process.wait = AsyncMock(return_value=0)
        with patch.object(main.settings, 'enable_sd_card_on_demand', True), patch('app.webrtc.resolve_stream_by_identifier', AsyncMock(return_value=stream)), patch.object(main.control_policy, 'allowed', return_value=True), patch.object(main, 'spawn_media_process', AsyncMock(return_value=process)) as spawn:
            response = await main.download_sd_card_stream('camera', 100, 200, session, source='camera', disposition='inline')
            self.assertEqual(response.headers['x-playback-source'], 'camera')
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(session.execute.await_count, 1)  # Only camera metadata, never RecordingSegment.
            self.assertEqual([part async for part in response.body_iterator], [b'first'])
            process.kill.assert_called_once()
            process.wait.assert_awaited()
            args = spawn.call_args.args
            self.assertIn('rtsp://user:secret@host/c7/b100/e200/replay/', args)
            self.assertEqual(args[args.index('-t') + 1], '100')

    async def test_empty_camera_fails_before_success_headers(self):
        from app import main
        stream = SimpleNamespace(camera_id='camera', stream_url='rtsp://host/c1/live')
        camera = SimpleNamespace(id='camera', name='Camera', make='UNV', active=True)
        session = MagicMock()
        session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=camera)))
        process = MagicMock(returncode=1)
        process.stdout.read = AsyncMock(return_value=b'')
        process.wait = AsyncMock(return_value=1)
        with patch.object(main.settings, 'enable_sd_card_on_demand', True), patch('app.webrtc.resolve_stream_by_identifier', AsyncMock(return_value=stream)), patch.object(main.control_policy, 'allowed', return_value=True), patch.object(main, 'spawn_media_process', AsyncMock(return_value=process)):
            with self.assertRaises(HTTPException) as error:
                await main.download_sd_card_stream('camera', 100, 200, session, source='camera')
            self.assertEqual(error.exception.status_code, 502)
            process.wait.assert_awaited()


if __name__ == '__main__':
    unittest.main()
