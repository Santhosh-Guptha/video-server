"""Persistent server/camera operations and explicit, scoped recording deletion."""
import asyncio
import copy
import shutil
import time
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from . import control_policy as control
from .config import settings
from .db import get_session
from .models import Camera, RecordingSegment
from .storage_quota import delete_recording

router = APIRouter(prefix='/api/control', tags=['server control'])


class CameraPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int | None = Field(default=None, ge=0, strict=True)
    ignored: bool = False
    live: bool = True
    recording: bool = True
    retention_days: int | None = Field(default=None, ge=1, le=365)


class ServerPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    live: bool
    recording: bool
    upstream_url: str
    revision: int | None = Field(default=None, ge=0, strict=True)

    @field_validator('upstream_url')
    @classmethod
    def valid_url(cls, value):
        parsed = urlsplit(value.strip())
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Use an HTTP(S) camera configuration URL without embedded credentials')
        return value.strip()


async def inventory(session):
    result = await session.execute(select(Camera).options(selectinload(Camera.streams)).order_by(Camera.name))
    cameras = list(result.scalars().all())
    control.aliases.clear()
    control.sources.clear()
    for camera in cameras:
        control.register(camera)
    return cameras


async def apply_runtime(session):
    from .main import configure_mediamtx_cameras_in_yaml, invalidate_cameras_cache
    from .rtsp_budget import rtsp_budget
    from .transcoder import transcoder_manager
    from .stream_manager import _mtx_request
    cameras = await inventory(session)
    # End blocked viewers even when the same source must remain for recording.
    response = await _mtx_request('GET', settings.mediamtx_api_url + '/v3/webrtcsessions/list?itemsPerPage=10000')
    response.raise_for_status()
    for item in response.json().get('items', []):
        if not control.allowed(item.get('path', ''), 'live'):
            kicked = await _mtx_request('POST', settings.mediamtx_api_url + '/v3/webrtcsessions/kick/' + item['id'])
            if kicked.status_code not in (200, 404):
                kicked.raise_for_status()
    for camera in cameras:
        if not control.allowed(str(camera.id), 'recording'):
            await control.cancel_recovery(str(camera.id))
        if not control.allowed(str(camera.id), 'live'):
            for name in [camera.server_camera_id, *(s.stream_id for s in camera.streams)]:
                if name:
                    await transcoder_manager.stop(name)
    # Persisted policy is applied both to YAML and every subsequent path mutation.
    await configure_mediamtx_cameras_in_yaml(session)
    rtsp_budget.paths = None
    await invalidate_cameras_cache()


@router.get('')
async def read_controls(session=Depends(get_session)):
    cameras = await inventory(session)
    rows = await session.execute(select(RecordingSegment.stream_id, func.count(), func.min(RecordingSegment.start_ts), func.max(RecordingSegment.end_ts)).group_by(RecordingSegment.stream_id))
    recordings = {row[0]: {'segments': row[1], 'oldest': row[2], 'newest': row[3]} for row in rows}
    disk = await asyncio.to_thread(shutil.disk_usage, Path(settings.recording_dir).resolve())
    return {'revision': control.revision(), 'checked_at': time.time(), 'runtime': control.state.get('runtime', {'status': 'unknown'}), 'server': {**control.state.get('server', {}), 'upstream_url': settings.upstream_camera_api_url},
            'disk': {'free': disk.free, 'total': disk.total},
            'cameras': [{'id': str(c.id), 'name': c.name, 'source': c.camera_source, 'active': c.active,
                         'policy': control.policy(str(c.id)),
                         'effective_live': c.active and control.allowed(str(c.id), 'live'),
                         'effective_recording': c.active and control.allowed(str(c.id), 'recording'),
                         'effective_retention_days': control.policy(str(c.id)).get('retention_days') or settings.default_retention_days,
                         'streams': [{'id': s.stream_id, 'profile': s.profile_type.value, 'resolution': s.resolution,
                                      'fps': s.fps, 'bitrate': s.bitrate, 'always_on': s.always_on, 'transcode': s.transcode,
                                      'codec': s.codec, 'status': s.status.value, **recordings.get(s.stream_id, {'segments': 0})} for s in c.streams]}
                        for c in cameras]}


@router.put('/server')
async def update_server(payload: ServerPolicy, session=Depends(get_session)):
    async with control.lock:
        from .operations import check_revision, reconcile
        check_revision(payload.revision)
        await inventory(session)
        value = copy.deepcopy(control.state)
        value['server'] = payload.model_dump(exclude={'revision'})
        value['runtime'] = {'status': 'pending', 'time': time.time()}
        control.commit(value, 'server.policy', 'server', {'live': payload.live, 'recording': payload.recording, 'source_changed': settings.upstream_camera_api_url != payload.upstream_url})
        settings.upstream_camera_api_url = payload.upstream_url
        await reconcile(session)
    return await read_controls(session)


@router.put('/cameras/{camera_id}')
async def update_camera_policy(camera_id: str, payload: CameraPolicy, session=Depends(get_session)):
    async with control.lock:
        from .operations import check_revision, reconcile
        check_revision(payload.revision)
        cameras = await inventory(session)
        if camera_id not in {str(c.id) for c in cameras}:
            raise HTTPException(404, 'Camera not found')
        previous = control.policy(camera_id)
        value = copy.deepcopy(control.state)
        value.setdefault('cameras', {}).setdefault(camera_id, {}).update(payload.model_dump(exclude={'revision'}))
        requires_apply = any(previous[key] != getattr(payload, key) for key in ['ignored', 'live', 'recording'])
        if requires_apply:
            value['runtime'] = {'status': 'pending', 'time': time.time()}
        control.commit(value, 'camera.policy', camera_id, payload.model_dump(exclude={'revision'}))
        if requires_apply:
            await reconcile(session)
    return await read_controls(session)


class DeleteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    camera_id: str
    before: float = Field(gt=0)
    confirm: bool = False


async def deletion_scope(payload, session):
    cameras = await inventory(session)
    selected = cameras if payload.camera_id == 'all' else [c for c in cameras if str(c.id) == payload.camera_id]
    if not selected:
        raise HTTPException(404, 'Camera not found')
    ids = [s.stream_id for c in selected for s in c.streams]
    cutoff = min(payload.before, time.time() - max(120, settings.segment_time_seconds * 2))
    result = await session.execute(select(RecordingSegment).where(RecordingSegment.stream_id.in_(ids), RecordingSegment.end_ts < cutoff))
    return selected, cutoff, list(result.scalars().all())


@router.post('/recordings/preview')
async def preview_delete(payload: DeleteRequest, session=Depends(get_session)):
    cameras, cutoff, segments = await deletion_scope(payload, session)
    return {'cameras': len(cameras), 'segments': len(segments), 'before': cutoff,
            'message': 'Only completed recordings older than two segment durations are eligible. This cannot be undone.'}


@router.post('/recordings/delete')
async def delete_recordings(payload: DeleteRequest, session=Depends(get_session)):
    if not payload.confirm:
        raise HTTPException(400, 'Preview and explicitly confirm deletion first')
    async with control.lock:
        cameras, cutoff, segments = await deletion_scope(payload, session)
        if any(control.allowed(str(c.id), 'recording') for c in cameras):
            raise HTTPException(409, 'Stop recording for the selected cameras before deleting footage')
        value = copy.deepcopy(control.state)
        for camera in cameras:
            await control.cancel_recovery(str(camera.id))
            entry = value.setdefault('cameras', {}).setdefault(str(camera.id), {})
            entry['deleted_before'] = max(entry.get('deleted_before', 0), cutoff)
        control.commit(value, 'recordings.delete_requested', payload.camera_id, {'before': cutoff, 'segments': len(segments)})
        removed = count = failed = 0
        root = Path(settings.recording_dir).resolve()
        from .timeline_service import PlaybackTimelineService
        for segment in segments:
            try:
                removed += await asyncio.to_thread(delete_recording, root, segment.file_path)
            except (OSError, ValueError):
                failed += 1
                continue
            stream_id, start = segment.stream_id, segment.start_ts
            await session.delete(segment)
            await session.commit()  # Never hold SQLite's writer lock during filesystem/cache I/O.
            await PlaybackTimelineService.invalidate_cache_for_timestamp(stream_id, start)
            count += 1
        control.commit(control.state, 'recordings.delete_completed', payload.camera_id, {'deleted': count, 'bytes_freed': removed, 'failed': failed})
        return {'deleted': count, 'bytes_freed': removed, 'failed': failed}
