import ast
import asyncio
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app import upstream
from fastapi import HTTPException

class RestoreSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_upstream_and_cache_does_not_return_empty_inventory(self):
        def unavailable(request):
            raise httpx.ConnectError('offline', request=request)
        client = httpx.AsyncClient(transport=httpx.MockTransport(unavailable))
        with tempfile.TemporaryDirectory() as directory, patch.object(upstream, '__file__', str(Path(directory)/'upstream.py')), patch.object(upstream.httpx, 'AsyncClient', return_value=client):
            with self.assertRaises(HTTPException) as error:
                await upstream.fetch_upstream_cameras()
            self.assertEqual(error.exception.status_code, 503)

    async def test_turn_health_accepts_transport_query(self):
        source = ROOT / 'backend/app/health_monitor.py'
        function = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'check_coturn_health')
        async def handle(reader, writer):
            writer.close()
            await writer.wait_closed()
        server = await asyncio.start_server(handle, '127.0.0.1', 0)
        async with server:
            port = server.sockets[0].getsockname()[1]
            namespace = {'asyncio': asyncio, 'urlsplit': urlsplit, 'settings': SimpleNamespace(turn_server_url=f'turn:127.0.0.1:{port}?transport=tcp')}
            exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
            self.assertTrue(await namespace['check_coturn_health']())
