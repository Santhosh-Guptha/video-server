"""Validation for bounded, on-demand camera archive requests."""
import math
import re
from urllib.parse import urlsplit
from fastapi import HTTPException
from .providers import get_playback_recovery_provider, UNVProvider
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ArchiveSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = True
    adapter: Literal['configured', 'unv'] = 'configured'
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
    if not isinstance(provider, UNVProvider):
        raise HTTPException(422, 'Camera archive playback is not implemented for this manufacturer. Generic live RTSP does not prove archive support.')
    return provider


def camera_url(make, stream, start, end):
    provider = camera_provider(make)
    parsed = urlsplit(stream.stream_url or '')
    if parsed.scheme not in ('rtsp', 'rtsps') or not parsed.hostname:
        raise HTTPException(422, 'A valid camera RTSP source is required.')
    if not re.search(r'/[cC]\d+\b|(?:^|[?&])channel(?:_id)?=\d+\b', parsed.path + '?' + parsed.query):
        raise HTTPException(422, 'Camera channel could not be identified. Refusing to guess channel 1.')
    return provider.build_playback_url(stream, start, end)
