import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.source_url import valid_camera_source
from app.transcoder import TranscoderManager
from app.services.webrtc_service import WebRTCService


class SourceUrlTests(unittest.TestCase):
    def test_rejects_incomplete_or_malformed_upstream_sources(self):
        for url in (None, "", "rtsp://", "rtsp://user@", "rtsp://188.13513.156:554/live", "rtsp://host:99999/live", "publisher"):
            with self.subTest(url=url):
                self.assertFalse(valid_camera_source(url))

    def test_accepts_camera_sources(self):
        for url in ("rtsp://user:pass@192.168.5.65:554/Streaming/Channels/101", "rtsps://camera.example/live", "rtmp://camera.example/live"):
            with self.subTest(url=url):
                self.assertTrue(valid_camera_source(url))


class TranscoderStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_different_streams_start_concurrently(self):
        TranscoderManager._transcoders.clear()
        TranscoderManager._starting.clear()
        active = 0
        peak = 0

        async def register(*args):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.03)
            active -= 1

        class Process:
            returncode = None
            pid = 123

        async def request(*args, **kwargs):
            return httpx.Response(200, json={"ready": True})

        with patch.object(TranscoderManager, "_register_h264_path", side_effect=register), patch.object(TranscoderManager, "_spawn_ffmpeg", new_callable=AsyncMock, return_value=Process()), patch("app.transcoder._get_mtx_request", return_value=request):
            paths = await asyncio.gather(TranscoderManager.ensure_transcoder("one"), TranscoderManager.ensure_transcoder("two"))
        self.assertEqual(paths, ["one_h264", "two_h264"])
        self.assertEqual(peak, 2)
        TranscoderManager._transcoders.clear()


class CompatibilityFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_unusable_hd_conversion_uses_ready_h264_sibling(self):
        source = SimpleNamespace(camera_id=7)
        normal = SimpleNamespace(stream_id="camera_normal", profile_type="NORMAL")
        result = MagicMock()
        result.scalars.return_value.all.return_value = [normal]
        session = SimpleNamespace(execute=AsyncMock(return_value=result))
        with patch.object(WebRTCService, "_path_codecs", new_callable=AsyncMock, return_value={"H264"}):
            selected = await WebRTCService._compatible_camera_fallback(source, "camera_hd", session)
        self.assertEqual(selected, "camera_normal")

if __name__ == "__main__":
    unittest.main()