"""Operator intent, independent of upstream inventory and runtime stream health."""
import asyncio
import json
import os
import copy
import time
from pathlib import Path

FILE = Path(__file__).parent / 'configs' / 'server_controls.json'
DEFAULT = {'ignored': False, 'live': True, 'recording': True, 'retention_days': None}
state = json.loads(FILE.read_text()) if FILE.exists() else {'server': {'live': True, 'recording': True}, 'cameras': {}}
aliases = {}
sources = {}
jobs = {}
lock = asyncio.Lock()


def save():
    write_state(state)


def write_state(value):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix('.tmp')
    with tmp.open('w') as output:
        json.dump(value, output, indent=2)
        output.flush()
        os.fsync(output.fileno())
    tmp.replace(FILE)


def revision():
    return state.get('revision', 0)


def commit(value, action, target, details=None):
    """Publish only after a successful atomic write; failed saves change nothing."""
    next_state = copy.deepcopy(value)
    next_state['revision'] = revision() + 1
    next_state['activity'] = (state.get('activity', []) + [{
        'time': time.time(), 'action': action, 'target': target,
        'details': details or {}, 'revision': next_state['revision'],
    }])[-500:]
    write_state(next_state)
    state.clear()
    state.update(next_state)


def record_runtime_result(ok):
    value = copy.deepcopy(state)
    value['runtime'] = {'status': 'applied' if ok else 'failed', 'time': time.time()}
    write_state(value)
    state.clear()
    state.update(value)


def register(camera):
    key = str(camera.id)
    names = [key, camera.server_camera_id, camera.name, str(camera.source_camera_id)]
    names.extend(s.stream_id for s in camera.streams)
    for name in names:
        if name:
            for alias in (name, name + '_h264'):
                # Duplicate display names must never apply one camera's policy
                # to a different camera. Explicit stream IDs remain usable.
                aliases[alias] = key if alias not in aliases or aliases[alias] == key else None
    for stream in camera.streams:
        if stream.stream_url:
            sources.setdefault(stream.stream_url, set()).add(key)


def policy(identifier):
    key = aliases.get(str(identifier), str(identifier))
    return {**DEFAULT, **state.get('cameras', {}).get(key, {})}


def allowed(identifier, purpose='live'):
    if str(identifier) in aliases and aliases[str(identifier)] is None:
        return False
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
