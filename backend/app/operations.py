"""Fleet operations: bounded batches, diagnostics, metadata and policy backups."""
import asyncio
import copy
import time
from typing import Literal
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from . import control_policy as control
from .config import settings
from .db import get_session
from .server_control import inventory, read_controls, apply_runtime

router = APIRouter(prefix='/api/control', tags=['fleet operations'])


def check_revision(expected):
    if expected is not None and expected != control.revision():
        raise HTTPException(409, 'Settings changed in another session. Refresh before applying your change.')


async def reconcile(session):
    try:
        await apply_runtime(session)
    except Exception:
        control.record_runtime_result(False)
        raise HTTPException(503, 'Policy saved; media service reconciliation failed. Refresh status and use Retry apply.')
    control.record_runtime_result(True)


class BulkAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    camera_ids: list[str] = Field(min_length=1, max_length=500)
    action: Literal['live_on', 'live_off', 'recording_on', 'recording_off', 'ignore', 'unignore', 'retention']
    retention_days: int | None = Field(default=None, ge=1, le=365, strict=True)
    revision: int = Field(ge=0, strict=True)

    @field_validator('camera_ids')
    @classmethod
    def unique_ids(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('Duplicate camera IDs are not allowed')
        return value


@router.post('/bulk')
async def bulk_action(payload: BulkAction, session=Depends(get_session)):
    async with control.lock:
        check_revision(payload.revision)
        known = {str(c.id) for c in await inventory(session)}
        if set(payload.camera_ids) - known:
            raise HTTPException(404, 'Some selected cameras no longer exist. No changes were made.')
        changes = {'live_on': {'live': True}, 'live_off': {'live': False},
                   'recording_on': {'recording': True}, 'recording_off': {'recording': False},
                   'ignore': {'ignored': True}, 'unignore': {'ignored': False},
                   'retention': {'retention_days': payload.retention_days}}[payload.action]
        value = copy.deepcopy(control.state)
        for camera_id in payload.camera_ids:
            value.setdefault('cameras', {}).setdefault(camera_id, {}).update(changes)
        if payload.action != 'retention':
            value['runtime'] = {'status': 'pending', 'time': time.time()}
        control.commit(value, 'bulk.' + payload.action, f'{len(payload.camera_ids)} cameras',
                       {'camera_ids': payload.camera_ids, **changes})
        # Retention is read directly by cleanup; do not interrupt live streams.
        if payload.action != 'retention':
            await reconcile(session)
    return await read_controls(session)


class CameraMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')
    site: str = Field(default='', max_length=100)
    notes: str = Field(default='', max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=12)
    favorite: bool = False
    revision: int = Field(ge=0, strict=True)

    @field_validator('tags')
    @classmethod
    def clean_tags(cls, value):
        tags = list(dict.fromkeys(t.strip() for t in value if t.strip()))
        if any(len(t) > 40 for t in tags):
            raise ValueError('Tags must be at most 40 characters')
        return tags


@router.put('/cameras/{camera_id}/metadata')
async def update_metadata(camera_id: str, payload: CameraMetadata, session=Depends(get_session)):
    async with control.lock:
        check_revision(payload.revision)
        if camera_id not in {str(c.id) for c in await inventory(session)}:
            raise HTTPException(404, 'Camera not found')
        value = copy.deepcopy(control.state)
        value.setdefault('cameras', {}).setdefault(camera_id, {}).update(payload.model_dump(exclude={'revision'}))
        control.commit(value, 'camera.metadata', camera_id, {'fields': ['site', 'tags', 'notes', 'favorite']})
    return await read_controls(session)


@router.post('/reconcile')
async def retry_apply(session=Depends(get_session)):
    async with control.lock:
        await reconcile(session)
    return await read_controls(session)


@router.get('/activity')
async def activity():
    return {'items': list(reversed(control.state.get('activity', []))), 'limit': 500}


@router.get('/backup')
async def backup_policy(session=Depends(get_session)):
    cameras = await inventory(session)
    # Explicit allowlist: no RTSP URLs, credentials, upstream query strings or notes.
    fields = [*control.DEFAULT, 'site', 'tags', 'favorite']
    return {'format': 'video-server-policy', 'version': 1, 'created_at': time.time(),
            'revision': control.revision(),
            'server': {key: control.state.get('server', {}).get(key, True) for key in ['live', 'recording']},
            'cameras': [{'id': str(c.id), 'name': c.name,
                         'policy': {k: control.policy(str(c.id))[k] for k in fields if k in control.policy(str(c.id))}}
                        for c in cameras]}


class RestorablePolicy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ignored: bool
    live: bool
    recording: bool
    retention_days: int | None = Field(default=None, ge=1, le=365, strict=True)
    site: str = Field(default='', max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=12)
    favorite: bool = False

    @field_validator('tags')
    @classmethod
    def tags_valid(cls, value):
        return CameraMetadata.clean_tags(value)


class BackupCamera(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(max_length=255)
    policy: RestorablePolicy


class BackupServer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    live: bool
    recording: bool


class PolicyBackup(BaseModel):
    model_config = ConfigDict(extra='forbid')
    format: Literal['video-server-policy']
    version: Literal[1]
    created_at: float = Field(ge=0, allow_inf_nan=False)
    revision: int = Field(ge=0)
    server: BackupServer
    cameras: list[BackupCamera] = Field(min_length=1, max_length=5000)

    @field_validator('cameras')
    @classmethod
    def no_duplicate_cameras(cls, value):
        if len({c.id for c in value}) != len(value):
            raise ValueError('Duplicate cameras in backup')
        return value


class RestoreRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    document: PolicyBackup
    revision: int = Field(ge=0, strict=True)
    confirm: bool = False


@router.post('/backup/preview')
async def preview_restore(payload: RestoreRequest, session=Depends(get_session)):
    check_revision(payload.revision)
    known = {str(c.id) for c in await inventory(session)}
    unknown = [c.id for c in payload.document.cameras if c.id not in known]
    return {'cameras': len(payload.document.cameras), 'unknown': unknown,
            'server': payload.document.server.model_dump(), 'can_restore': not unknown}


@router.post('/backup/restore')
async def restore_backup(payload: RestoreRequest, session=Depends(get_session)):
    if not payload.confirm:
        raise HTTPException(400, 'Preview and confirm the policy restore first')
    async with control.lock:
        preview = await preview_restore(payload, session)
        if not preview['can_restore']:
            raise HTTPException(409, 'Backup contains cameras absent from this server. No changes were made.')
        value = copy.deepcopy(control.state)
        value.setdefault('server', {}).update(payload.document.server.model_dump())
        for camera in payload.document.cameras:
            # Preserve recovery deletion cutoffs and private notes from this server.
            value.setdefault('cameras', {}).setdefault(camera.id, {}).update(camera.policy.model_dump())
        value['runtime'] = {'status': 'pending', 'time': time.time()}
        control.commit(value, 'policy.restore', f'{len(payload.document.cameras)} cameras', {'backup_created_at': payload.document.created_at})
        await reconcile(session)
    return await read_controls(session)


@router.get('/diagnostics')
async def diagnostics():
    started = time.monotonic()
    async def media():
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(settings.mediamtx_api_url + '/v3/paths/list?itemsPerPage=10000')
                response.raise_for_status()
            paths = response.json().get('items', [])
            public = [p for p in paths if not p.get('name', '').startswith('_ingest_')]
            return {'status': 'ok', 'ready_paths': sum(bool(p.get('ready')) for p in public),
                    'configured_paths': len(public), 'latency_ms': round((time.monotonic()-started)*1000)}
        except Exception:
            return {'status': 'unavailable', 'message': 'Media service did not respond. Verify MediaMTX and retry.'}
    async def cache():
        from .redis_client import redis_client
        try:
            if redis_client is None:
                raise RuntimeError()
            await asyncio.wait_for(redis_client.ping(), timeout=3)
            return {'status': 'ok'}
        except Exception:
            return {'status': 'degraded', 'message': 'Redis is unavailable; some features use an in-memory fallback.'}
    media_result, cache_result = await asyncio.gather(media(), cache())
    from .transcoder import transcoder_manager
    return {'checked_at': time.time(), 'media': media_result, 'cache': cache_result,
            'transcoders': len(transcoder_manager._transcoders), 'transcoder_limit': settings.max_active_transcoders,
            'recovery_jobs': len(control.jobs), 'storage_limit_gib': settings.recording_storage_limit_gb,
            'runtime': control.state.get('runtime', {'status': 'unknown'}),
            'turn_configured': bool(settings.turn_server_url)}


@router.get('/deployment-readiness')
async def deployment_readiness(mode: Literal['onprem', 'hosted'] = 'onprem'):
    from .deployment_readiness import report
    return report(settings, mode)
