"""Shared upstream ingest and conservative RTSP admission for one backend process.

Configured MediaMTX sources reserve slots even while reconnecting or idle. This
prevents a recovery job from stealing a slot needed by an existing live stream.
External applications and other backend instances are outside this budget.
"""
import asyncio
import hashlib
import shlex
import re
from contextlib import suppress
from collections import Counter
from contextlib import asynccontextmanager
from urllib.parse import urlsplit, unquote

import httpx

INGEST_PREFIX = '_ingest_'


class RTSPCapacityError(RuntimeError):
    pass


def endpoint(url):
    try:
        parsed = urlsplit(str(url).strip())
        if parsed.scheme.lower() not in ('rtsp', 'rtsps') or not parsed.hostname:
            return None
        port = parsed.port or (322 if parsed.scheme.lower() == 'rtsps' else 554)
        if parsed.hostname.lower() in ('localhost', '127.0.0.1', '::1') and port == 8554:
            return None
        return f'{parsed.hostname.lower()}:{port}'
    except ValueError:
        return None


def ingest_name(url):
    return INGEST_PREFIX + hashlib.sha256(url.strip().encode()).hexdigest()[:32]


def relay_url(url):
    return f'rtsp://127.0.0.1:8554/{ingest_name(url)}'


def sources(payload):
    result = set()
    source = payload.get('source', '')
    if endpoint(source):
        result.add(source.strip())
    for hook in ('runOnInit', 'runOnDemand'):
        command = payload.get(hook, '')
        if command:
            for arg in shlex.split(command):
                if endpoint(arg):
                    result.add(arg.strip())
    return result


def ingest_config(url):
    return {'source': url, 'rtspTransport': 'tcp', 'sourceOnDemand': True,
            'sourceOnDemandStartTimeout': '20s', 'sourceOnDemandCloseAfter': '10s',
            'record': False, 'runOnInit': '', 'runOnDemand': '',
            'runOnRecordSegmentComplete': ''}


def relay_config(payload):
    result = dict(payload)
    for source in sources(payload):
        if result.get('source', '').strip() == source:
            result['source'] = relay_url(source)
        for hook in ('runOnInit', 'runOnDemand'):
            if result.get(hook):
                result[hook] = result[hook].replace(source, relay_url(source))
    return result


def shared_paths(desired, previous, limit):
    """Migrate existing sources without cutting them off when above a new cap."""
    wanted = {u for p in desired.values() for u in sources(p)}
    established = {u for p in previous.values() for u in sources(p)} & wanted
    admitted = set(established)
    counts = Counter(endpoint(u) for u in admitted)
    # Admit main streams first on a fresh endpoint. Existing paths keep priority.
    ordered = sorted(desired, key=lambda name: (not name.upper().endswith(('_HD', '_MAIN')), name))
    output, blocked = {}, []
    for name in ordered:
        payload = desired[name]
        needed = sources(payload) - admitted
        additions = Counter(endpoint(u) for u in needed)
        if any(counts[host] + number > limit for host, number in additions.items()):
            blocked.append(name)
            continue
        admitted.update(needed)
        counts.update(additions)
        output[name] = relay_config(payload)
    used = {u for name, p in desired.items() if name in output for u in sources(p)}
    output.update({ingest_name(u): ingest_config(u) for u in used})
    return output, blocked


class RTSPBudget:
    def __init__(self, limit, api_url, client=None):
        self.limit = limit
        self.api_url = api_url.rstrip('/')
        self.client = client
        self.lock = asyncio.Lock()
        self.paths = None
        self.leases = Counter()
        self.watchers = set()
        self.blocked = set()

    async def _client(self):
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=5.0)
        return self.client

    async def _load(self):
        if self.paths is not None:
            return
        response = await (await self._client()).get(self.api_url + '/v3/config/paths/list?itemsPerPage=10000')
        response.raise_for_status()  # Fail closed if existing reservations are unknown.
        data = response.json()
        if data.get('pageCount', 1) > 1:
            raise RTSPCapacityError('RTSP inventory exceeds the admission snapshot size')
        items = data.get('items', [])
        self.paths = items if isinstance(items, dict) else {p['name']: p for p in items}

    def _counts(self):
        # Count paths, not just URLs, until the migration has removed duplicates.
        counts = Counter()
        for payload in self.paths.values():
            counts.update(endpoint(u) for u in sources(payload))
        return counts

    def _check(self, additions):
        used = self._counts() + self.leases
        if any(used[host] + number > self.limit() for host, number in additions.items()):
            raise RTSPCapacityError('RTSP capacity is full; existing streams keep their slots. Retry after a slot is released.')

    async def mutate(self, method, url, **kwargs):
        async with self.lock:
            await self._load()
            client = await self._client()
            name = unquote(url.split('/paths/', 1)[1].split('/', 1)[1].split('?', 1)[0])
            payload = dict(kwargs.get('json') or {})
            if method in ("POST", "PATCH"):
                from .control_policy import path_policy
                payload = path_policy(name, payload)
                if payload is None:
                    return httpx.Response(403, json={"error": "Camera stopped by operator"}, request=httpx.Request(method, url))
                kwargs["json"] = payload
            try:
                if method in ('POST', 'PATCH'):
                    # A no-op/source update reuses the helper, even at capacity.
                    missing = {source for source in sources(payload) if ingest_name(source) not in self.paths}
                    self._check(Counter(endpoint(source) for source in missing))
                    for source in missing:
                        helper = ingest_name(source)
                        if helper not in self.paths:
                            self._check(Counter({endpoint(source): 1}))
                            response = await client.post(self.api_url + '/v3/config/paths/add/' + helper, json=ingest_config(source))
                            response.raise_for_status()
                            self.paths[helper] = ingest_config(source)
                    if 'json' in kwargs:
                        kwargs['json'] = relay_config(payload)
                response = await client.request(method, url, **kwargs)
                if response.is_success:
                    if method == 'DELETE':
                        self.paths.pop(name, None)
                    else:
                        self.paths[name] = {**self.paths.get(name, {}), **kwargs.get('json', {})}
                    self.blocked.discard(name)
                await self._prune(client)
                return response
            except RTSPCapacityError as exc:
                self.blocked.add(name)
                return httpx.Response(429, json={'error': str(exc)}, request=httpx.Request(method, url), headers={'Retry-After': '10'})
            except BaseException:
                self.paths = None  # An interrupted HTTP write may have succeeded.
                raise

    async def _prune(self, client):
        referenced = set()
        for name, payload in self.paths.items():
            if name.startswith(INGEST_PREFIX):
                continue
            for key in ('source', 'runOnInit', 'runOnDemand'):
                referenced.update(re.findall(r'_ingest_[0-9a-f]{32}', str(payload.get(key, ''))))
        for helper in list(self.paths):
            if helper.startswith(INGEST_PREFIX) and helper not in referenced:
                response = await client.delete(self.api_url + '/v3/config/paths/delete/' + helper)
                if response.is_success or response.status_code == 404:
                    self.paths.pop(helper, None)

    @asynccontextmanager
    async def connection(self, urls):
        additions = Counter(endpoint(url) for url in urls if endpoint(url))
        if not additions:
            yield
            return
        async with self.lock:
            await self._load()
            self._check(additions)
            # A separate small process budget reserves CPU for live decoding.
            if sum(self.leases.values()) + sum(additions.values()) > 2:
                raise RTSPCapacityError('Background RTSP capacity is full; retry later')
            self.leases.update(additions)
        try:
            yield
        finally:
            async with self.lock:
                self.leases.subtract(additions)
                self.leases += Counter()

    async def spawn(self, *args, **kwargs):
        from .control_policy import sources as known_sources, allowed
        for arg in args:
            owners = known_sources.get(str(arg), set())
            if owners and not any(allowed(owner, "connect") for owner in owners):
                raise RTSPCapacityError("Camera ignored by operator")
        if any(endpoint(arg) for arg in args):
            async with self.lock:
                await self._load()
                # Probes/live readers of a registered source use its shared feed.
                is_probe = str(args[0]).replace('\\', '/').split('/')[-1] in ('ffprobe', 'ffprobe.exe')
                args = tuple(relay_url(arg) if endpoint(arg) and ingest_name(arg) in self.paths and
                             (is_probe or (i > 0 and args[i - 1] == '-i')) else arg for i, arg in enumerate(args))
        lease = self.connection([arg for arg in args if endpoint(arg)])
        await lease.__aenter__()
        try:
            process = await asyncio.create_subprocess_exec(*args, **kwargs)
        except BaseException:
            await lease.__aexit__(None, None, None)
            raise
        async def release_when_exited():
            try:
                await process.wait()
            except asyncio.CancelledError:
                if process.returncode is None:
                    with suppress(ProcessLookupError):
                        process.kill()
                    await process.wait()
                raise
            finally:
                await lease.__aexit__(None, None, None)
        watcher = asyncio.create_task(release_when_exited())
        self.watchers.add(watcher)
        watcher.add_done_callback(self.watchers.discard)
        return process

    async def snapshot(self):
        async with self.lock:
            await self._load()
            counts = self._counts()
            return {'limit_per_endpoint': self.limit(), 'shared_ingests': sum(n.startswith(INGEST_PREFIX) for n in self.paths),
                    'blocked_paths': sorted(self.blocked),
                    'endpoints': [{'endpoint': host, 'reserved_ingests': counts[host], 'temporary_connections': self.leases[host],
                                   'at_capacity': counts[host] + self.leases[host] >= self.limit()}
                                  for host in sorted(counts.keys() | self.leases.keys())]}


def _limit():
    from .config import settings
    return settings.rtsp_connections_per_endpoint


from .config import settings
rtsp_budget = RTSPBudget(_limit, settings.mediamtx_api_url)
spawn_media_process = rtsp_budget.spawn

_recovery_slots = asyncio.Semaphore(2)
_recovery_locks = {}


@asynccontextmanager
async def recovery_work(stream_id):
    # Shared by manual, short-segment and periodic recovery. Acquire before
    # opening a database session, and serialize writes for the same camera.
    async with _recovery_locks.setdefault(stream_id, asyncio.Lock()):
        async with _recovery_slots:
            from . import control_policy as control
            if not control.allowed(stream_id, "recording"):
                raise RTSPCapacityError("Recording stopped by operator")
            task = asyncio.current_task()
            control.jobs[task] = stream_id
            try:
                yield
            finally:
                control.jobs.pop(task, None)


async def communicate_process(process, timeout):
    """Drain output and reap timed-out/cancelled children before returning capacity."""
    try:
        return await asyncio.wait_for(process.communicate(), timeout)
    finally:
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
            await process.communicate()
