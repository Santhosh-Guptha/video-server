"""Validated, non-secret playback policy overrides, persisted atomically."""
import json
import os
from pathlib import Path
from typing import Literal
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

CONFIG_FILE = Path(__file__).parent / 'configs' / 'streaming_overrides.json'

class StreamingSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    grid_view_profile: Literal['HD', 'NORMAL', 'MOBILE'] = 'HD'
    focus_view_profile: Literal['HD', 'NORMAL', 'MOBILE'] = 'HD'
    playback_profile: Literal['HD', 'NORMAL', 'MOBILE'] = 'HD'
    webrtc_stall_timeout_seconds: int = Field(default=8, ge=4, le=60, strict=True)
    webrtc_connection_timeout_seconds: int = Field(default=20, ge=10, le=60, strict=True)
    max_active_transcoders: int = Field(default=10, ge=1, le=10, strict=True)

def load_overrides():
    if not CONFIG_FILE.exists():
        return {}
    return StreamingSettings.model_validate_json(CONFIG_FILE.read_text()).model_dump()

router = APIRouter(prefix='/api/settings/streaming', tags=['streaming settings'])

@router.get('')
async def read_streaming_settings():
    from .config import settings
    values = StreamingSettings(**{key: getattr(settings, key) for key in StreamingSettings.model_fields})
    return {'settings': values.model_dump(), 'upstream_url': settings.upstream_camera_api_url,
            'recording': {'hd_only': settings.record_hd_only, 'retention_days': settings.default_retention_days,
                          'segment_seconds': settings.segment_time_seconds},
            'turn_configured': bool(settings.turn_server_url)}

@router.put('')
async def write_streaming_settings(payload: StreamingSettings):
    from . import config
    # No credentials, network destinations or camera URLs are writable here.
    # A single process writes the small file before publishing runtime changes.
    temporary = CONFIG_FILE.with_suffix('.tmp')
    try:
        with temporary.open('w') as output:
            json.dump(payload.model_dump(), output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(CONFIG_FILE)
    finally:
        temporary.unlink(missing_ok=True)
    for key, value in payload.model_dump().items():
        setattr(config.settings, key, value)
    for key in ['grid_view_profile', 'focus_view_profile', 'playback_profile',
                'webrtc_connection_timeout_seconds', 'max_active_transcoders']:
        setattr(config, key.upper(), getattr(payload, key))
    return await read_streaming_settings()
