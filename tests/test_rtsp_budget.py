import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.rtsp_budget import (RTSPBudget, RTSPCapacityError, endpoint, shared_paths,
                             ingest_name, communicate_process, recovery_work)


class FakeMediaMTX:
    def __init__(self):
        self.paths = {}

    async def request(self, request):
        path = request.url.path
        if path.endswith('/list'):
            return httpx.Response(200, json={'items': [dict(p, name=n) for n, p in self.paths.items()]})
        action, name = path.split('/paths/')[1].split('/', 1)
        payload = json.loads(request.content) if request.content else {}
        if action == 'add':
            if name in self.paths:
                return httpx.Response(400, json={'error': 'already exists'})
            self.paths[name] = payload
        elif action == 'patch':
            self.paths[name].update(payload)
        elif action == 'delete':
            self.paths.pop(name, None)
        return httpx.Response(200, json={})


class SharedPathTests(unittest.TestCase):
    def test_duplicate_profiles_share_one_ingest_without_changing_record_policy(self):
        url = 'rtsp://user:secret@camera:554/main'
        paths, blocked = shared_paths({'first': {'source': url, 'record': True}, 'second': {'source': url, 'record': False}}, {}, 6)
        self.assertEqual(len(paths), 3)
        self.assertEqual(paths['first']['source'], paths['second']['source'])
        self.assertTrue(paths['first']['record'])
        self.assertFalse(paths['second']['record'])
        self.assertFalse(paths[ingest_name(url)]['record'])
        self.assertEqual(blocked, [])

    def test_existing_nvr_channels_survive_but_new_channels_wait(self):
        old = {f'cam{i}': {'source': f'rtsp://nvr/channel{i}'} for i in range(8)}
        desired = {**old, 'new': {'source': 'rtsp://nvr/new'}}
        paths, blocked = shared_paths(desired, old, 6)
        self.assertEqual(blocked, ['new'])
        self.assertEqual(sum(n.startswith('_ingest_') for n in paths), 8)

    def test_fresh_endpoint_cap_and_main_priority(self):
        paths, blocked = shared_paths({'cam_SUB': {'source': 'rtsp://cam/sub'}, 'cam_HD': {'source': 'rtsp://cam/main'}}, {}, 1)
        self.assertIn('cam_HD', paths)
        self.assertEqual(blocked, ['cam_SUB'])
        self.assertEqual(endpoint('rtsp://user:pass@CAM:554/path'), 'cam:554')
        self.assertIsNone(endpoint('rtsp://127.0.0.1:8554/relay'))


class BudgetTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = FakeMediaMTX()
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(self.server.request))
        self.budget = RTSPBudget(lambda: 6, 'http://mtx', self.client)

    async def asyncTearDown(self):
        await self.client.aclose()

    async def add(self, name, source):
        return await self.budget.mutate('POST', 'http://mtx/v3/config/paths/add/' + name, json={'source': source})

    async def test_concurrent_aliases_only_open_one_camera_ingest(self):
        responses = await asyncio.gather(*(self.add(str(i), 'rtsp://camera/main') for i in range(20)))
        self.assertTrue(all(r.status_code == 200 for r in responses))
        self.assertEqual(sum(endpoint(p.get('source')) is not None for p in self.server.paths.values()), 1)

    async def test_atomic_capacity_rejection_and_release(self):
        responses = await asyncio.gather(*(self.add(str(i), f'rtsp://camera/{i}') for i in range(7)))
        self.assertEqual([r.status_code for r in responses].count(200), 6)
        self.assertEqual([r.status_code for r in responses].count(429), 1)
        await self.budget.mutate('DELETE', 'http://mtx/v3/config/paths/delete/0')
        self.assertEqual((await self.add('retry', 'rtsp://camera/7')).status_code, 200)

    async def test_alias_reuse_at_capacity_and_last_alias_cleanup(self):
        self.budget.limit = lambda: 1
        await self.add('one', 'rtsp://camera/main')
        self.assertEqual((await self.add('two', 'rtsp://camera/main')).status_code, 200)
        await self.budget.mutate('DELETE', 'http://mtx/v3/config/paths/delete/one')
        self.assertIn(ingest_name('rtsp://camera/main'), self.server.paths)
        await self.budget.mutate('DELETE', 'http://mtx/v3/config/paths/delete/two')
        self.assertEqual(self.server.paths, {})

    async def test_temporary_connections_share_ingest_budget(self):
        self.budget.limit = lambda: 2
        await self.add('main', 'rtsp://camera/main')
        async with self.budget.connection(['rtsp://camera/playback']):
            with self.assertRaises(RTSPCapacityError):
                async with self.budget.connection(['rtsp://camera/probe']):
                    self.fail('capacity exceeded')
        self.assertFalse(self.budget.leases)

    async def test_camera_probe_reuses_existing_ingest(self):
        await self.add('main', 'rtsp://camera/main')
        process = AsyncMock()
        with patch('asyncio.create_subprocess_exec', new=AsyncMock(return_value=process)) as spawn:
            await self.budget.spawn('ffprobe', 'rtsp://camera/main')
            self.assertEqual(spawn.call_args.args[1], 'rtsp://127.0.0.1:8554/' + ingest_name('rtsp://camera/main'))
            self.assertFalse(self.budget.leases)
        await asyncio.gather(*self.budget.watchers)

    async def test_manual_and_scheduled_recovery_share_work_limits(self):
        active, peak = set(), 0
        async def job(camera):
            nonlocal peak
            async with recovery_work(camera):
                self.assertNotIn(camera, active)
                active.add(camera)
                peak = max(peak, len(active))
                await asyncio.sleep(0.01)
                active.remove(camera)
        await asyncio.gather(*(job(camera) for camera in ['a', 'a', 'b', 'c', 'd']))
        self.assertEqual(peak, 2)

    async def test_failed_spawn_and_process_exit_release_slots(self):
        with patch('asyncio.create_subprocess_exec', new=AsyncMock(side_effect=OSError('spawn failed'))):
            with self.assertRaises(OSError):
                await self.budget.spawn('ffprobe', 'rtsp://camera/main')
        self.assertFalse(self.budget.leases)
        process = await self.budget.spawn(sys.executable, '-c', 'pass', 'rtsp://camera/main')
        await process.wait()
        await asyncio.gather(*self.budget.watchers)
        self.assertFalse(self.budget.leases)

    async def test_timeout_reaps_process_and_releases_slot(self):
        process = await self.budget.spawn(sys.executable, '-c', 'import time; time.sleep(30)', 'rtsp://camera/main', stdout=asyncio.subprocess.PIPE)
        with self.assertRaises(asyncio.TimeoutError):
            await communicate_process(process, 0.05)
        await asyncio.gather(*self.budget.watchers)
        self.assertIsNotNone(process.returncode)
        self.assertFalse(self.budget.leases)

    async def test_unknown_inventory_fails_closed(self):
        self.budget.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
        try:
            with self.assertRaises(httpx.HTTPStatusError):
                async with self.budget.connection(['rtsp://camera/main']):
                    self.fail('unknown reservations must not admit connections')
        finally:
            await self.budget.client.aclose()


if __name__ == '__main__':
    unittest.main()
