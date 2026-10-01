"""Operator intent, independent of upstream inventory and runtime stream health."""
import asyncio
import json
import os
from pathlib import Path

FILE = Path(__file__).parent / 'configs' / 'server_controls.json'
DEFAULT = {'ignored': False, 'live': True, 'recording': True, 'retention_days': None}
state = json.loads(FILE.read_text()) if FILE.exists() else {'server': {'live': True, 'recording': True}, 'cameras': {}}
aliases = {}
sources = {}
jobs = {}
lock = asyncio.Lock()


def save():
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix('.tmp')
    with tmp.open('w') as output:
        json.dump(state, output, indent=2)
        output.flush()
        os.fsync(output.fileno())
    tmp.replace(FILE)


def register(camera):
    key = str(camera.id)
    names = [key, camera.server_camera_id, camera.name, str(camera.source_camera_id)]
    names.extend(s.stream_id for s in camera.streams)
    for name in names:
        if name:
            aliases[name] = key
            aliases[name + '_h264'] = key
    for stream in camera.streams:
        if stream.stream_url:
            sources.setdefault(stream.stream_url, set()).add(key)


def policy(identifier):
    key = aliases.get(str(identifier), str(identifier))
    return {**DEFAULT, **state.get('cameras', {}).get(key, {})}


def allowed(identifier, purpose='live'):
    value = policy(identifier)
    if value['ignored']:
        return False
    server = state.get('server', {})
    if purpose == 'connect':
        return allowed(identifier, 'live') or allowed(identifier, 'recording')
    return bool(value[purpose] and server.get(purpose, True))


def recording_after(identifier):
    return policy(identifier).get('deleted_before', 0)


def path_policy(name, payload):
    if not allowed(name, 'connect'):
        return None
    result = dict(payload)
    if not allowed(name, 'recording'):
        result['record'] = False
        # An always-on recording source can sleep while nobody is viewing it.
        if result.get('source', '').startswith(('rtsp://', 'rtsps://')):
            result['sourceOnDemand'] = True
    return result


async def cancel_recovery(identifier=None):
    tasks = [task for task, stream in list(jobs.items()) if identifier is None or aliases.get(stream, stream) == str(identifier)]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
