"""Validation for bounded, on-demand camera archive requests."""
import math
import re
import time
import logging
from collections import OrderedDict
from urllib.parse import urlsplit, urlunsplit, urlencode
from datetime import datetime, timezone
from fastapi import HTTPException
from .providers import get_playback_recovery_provider, UNVProvider, HikvisionProvider
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

_failures = OrderedDict()


def playback_failure_message(stderr):
    if '401 Unauthorized' in stderr or '403 Forbidden' in stderr:
        return 'Camera rejected archive access. Verify remote playback permission for the configured camera account and the device playback API.'
    if '404 Not Found' in stderr or '454 Session Not Found' in stderr:
        return 'Camera archive endpoint or requested recording was not found. Verify the adapter and recording interval.'
    return 'Camera returned no playable recording. Verify archive availability, account permissions and device playback support.'


def record_failure(camera_id, start, end, detail):
    key = str(camera_id)
    _failures.pop(key, None)
    _failures[key] = {'time': time.time(), 'start_ts': start, 'end_ts': end, 'detail': detail}
    logging.getLogger('camera_video_platform').warning('Camera archive failed camera=%s start=%s end=%s: %s', key, start, end, detail)
    while len(_failures) > 500:
        _failures.popitem(last=False)


def last_failure(camera_id):
    value = _failures.get(str(camera_id))
    return value if value and time.time() - value['time'] < 900 else None


class ArchiveSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = True
    adapter: Literal['configured', 'unv', 'hikvision'] = 'configured'
    stream_id: str = Field(default='', max_length=255)
    max_minutes: int = Field(default=15, ge=1, le=15, strict=True)
    first_data_timeout: int = Field(default=20, ge=5, le=60, strict=True)
    idle_timeout: int = Field(default=30, ge=5, le=60, strict=True)


def archive_settings(camera_id):
    from .control_policy import policy
    return ArchiveSettings.model_validate(policy(str(camera_id)).get('archive', {}))


def validate_interval(start, end):
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        raise HTTPException(422, 'Choose a valid start and end time.')
    if end - start > 900:
        raise HTTPException(422, 'Camera playback supports up to 15 minutes per request.')


def camera_provider(make):
    provider = get_playback_recovery_provider(make)
    if not isinstance(provider, (UNVProvider, HikvisionProvider)):
        raise HTTPException(422, 'Camera archive playback is not implemented for this manufacturer. Generic live RTSP does not prove archive support.')
    return provider


def camera_url(make, stream, start, end):
    provider = camera_provider(make)
    parsed = urlsplit(stream.stream_url or '')
    if parsed.scheme not in ('rtsp', 'rtsps') or not parsed.hostname:
        raise HTTPException(422, 'A valid camera RTSP source is required.')
    if isinstance(provider, HikvisionProvider):
        match = re.fullmatch(r'/(?:ISAPI/)?Streaming/(?:Channels|tracks)/(\d+)/?', parsed.path, re.IGNORECASE)
        if not match:
            raise HTTPException(422, 'Hikvision archive requires a Streaming/Channels or Streaming/tracks source with a track ID.')
        # Playback uses tracks, not the live Channels endpoint. Z timestamps
        # must be UTC regardless of the server or browser's local timezone.
        query = urlencode({key: datetime.fromtimestamp(value, timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                           for key, value in [('starttime', start), ('endtime', end)]})
        return urlunsplit((parsed.scheme, parsed.netloc, f'/Streaming/tracks/{match.group(1)}', query, ''))
    if not re.search(r'/[cC]\d+\b|(?:^|[?&])channel(?:_id)?=\d+\b', parsed.path + '?' + parsed.query):
        raise HTTPException(422, 'UNV adapter does not match the camera URL. Select the correct archive adapter in camera configuration; no channel was guessed.')
    return provider.build_playback_url(stream, start, end)
