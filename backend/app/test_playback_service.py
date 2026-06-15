import pytest
import uuid
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from .main import app
from .models import RecordingSegment, CameraStream, StreamState, ProfileType
from .timeline_service import PlaybackTimelineService, local_memory_cache

client = TestClient(app)

@pytest.fixture
def mock_db_session():
    return AsyncMock(spec=AsyncSession)

@pytest.fixture
def override_db(mock_db_session):
    from .db import get_session
    async def override():
        yield mock_db_session
    app.dependency_overrides[get_session] = override
    yield mock_db_session
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_playback_timeline_service_calculation(mock_db_session):
    """Test PlaybackTimelineService calculations: contiguous merging, gaps, and coverage."""
    stream_id = "test_stream_play"
    date_str = "2026-06-13"
    
    # Define start of day (local epoch timestamp equivalent)
    from datetime import datetime
    dt_start = datetime.strptime(date_str, "%Y-%m-%d")
    day_start_ts = dt_start.timestamp()
    
    # 1. Create mock segments:
    # Seg A: 10:00:00 to 10:01:00 (60s)
    # Seg B: 10:01:03 to 10:02:00 (57s) -> Gap is 3s (should merge since <= 5s)
    # Seg C: 11:00:00 to 11:10:00 (600s) -> Gap is 3480s (should NOT merge)
    seg_a = RecordingSegment(
        stream_id=stream_id,
        file_path="/data/a.mp4",
        start_ts=day_start_ts + 36000.0, # 10:00:00
        end_ts=day_start_ts + 36060.0    # 10:01:00
    )
    seg_b = RecordingSegment(
        stream_id=stream_id,
        file_path="/data/b.mp4",
        start_ts=day_start_ts + 36063.0, # 10:01:03
        end_ts=day_start_ts + 36120.0    # 10:02:00
    )
    seg_c = RecordingSegment(
        stream_id=stream_id,
        file_path="/data/c.mp4",
        start_ts=day_start_ts + 39600.0, # 11:00:00
        end_ts=day_start_ts + 40200.0    # 11:10:00
    )
    
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [seg_a, seg_b, seg_c]
    mock_db_session.execute.return_value = mock_res
    
    # Clear local cache to force DB query
    cache_key = f"vms:timeline:{stream_id}:{date_str}"
    local_memory_cache._cache.pop(cache_key, None)
    
    # Mock redis_client = None to test local cache
    with patch("app.timeline_service.redis_client", None):
        timeline = await PlaybackTimelineService.get_daily_timeline(mock_db_session, stream_id, date_str)
        
        # Verify merged segments
        # Seg A & B should merge: start_ts = 10:00:00, end_ts = 10:02:00 (duration = 120s)
        assert len(timeline["segments"]) == 2
        assert timeline["segments"][0]["start_ts"] == day_start_ts + 36000.0
        assert timeline["segments"][0]["end_ts"] == day_start_ts + 36120.0
        assert timeline["segments"][0]["duration"] == 120.0
        
        # Seg C should remain unmerged: start_ts = 11:00:00, end_ts = 11:10:00 (duration = 600s)
        assert timeline["segments"][1]["start_ts"] == day_start_ts + 39600.0
        assert timeline["segments"][1]["end_ts"] == day_start_ts + 40200.0
        
        # Verify first and last recording ts
        assert timeline["first_recording_ts"] == day_start_ts + 36000.0
        assert timeline["last_recording_ts"] == day_start_ts + 40200.0
        
        # Verify metrics
        assert timeline["segment_count"] == 3
        
        # Total recorded duration is sum of merged segments = 120.0 + 600.0 = 720.0s
        assert timeline["recorded_duration"] == 720.0
        assert timeline["gap_duration"] == 86400.0 - 720.0
        assert timeline["coverage_percent"] == round((720.0 / 86400.0) * 100.0, 2)

@pytest.mark.asyncio
async def test_playback_timeline_service_caching(mock_db_session):
    """Test PlaybackTimelineService caching in memory."""
    stream_id = "test_stream_play_cache"
    date_str = "2026-06-13"
    
    # Initial db call returns 0 segments
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = mock_res
    
    cache_key = f"vms:timeline:{stream_id}:{date_str}"
    local_memory_cache._cache.pop(cache_key, None)
    
    with patch("app.timeline_service.redis_client", None):
        # 1st call: DB query executed
        res1 = await PlaybackTimelineService.get_daily_timeline(mock_db_session, stream_id, date_str)
        assert res1["segment_count"] == 0
        assert mock_db_session.execute.call_count == 1
        
        # 2nd call: Cached response read (DB not hit again)
        res2 = await PlaybackTimelineService.get_daily_timeline(mock_db_session, stream_id, date_str)
        assert res2["segment_count"] == 0
        assert mock_db_session.execute.call_count == 1  # Still 1 call!

@pytest.mark.asyncio
async def test_playback_api_endpoints(override_db):
    """Test HTTP API endpoints: /timeline, /gaps, and /summary."""
    stream_id = "test_stream_endpoints"
    date_str = "2026-06-13"
    
    # Seed timeline service cache manually to prevent DB dependencies
    cache_key = f"vms:timeline:{stream_id}:{date_str}"
    mock_timeline = {
        "segments": [{"start_ts": 100.0, "end_ts": 200.0, "duration": 100.0}],
        "gaps": [{"start_ts": 200.0, "end_ts": 300.0, "duration": 100.0}],
        "coverage_percent": 98.3,
        "recorded_duration": 84960.0,
        "gap_duration": 1440.0,
        "segment_count": 5,
        "first_recording_ts": 100.0,
        "last_recording_ts": 200.0
    }
    local_memory_cache.set(cache_key, mock_timeline, 60)
    
    # 1. Test /timeline
    resp = client.get(f"/api/playback/{stream_id}/timeline?date={date_str}")
    assert resp.status_code == 200
    assert resp.json()["coverage_percent"] == 98.3
    assert resp.json()["segment_count"] == 5
    
    # 2. Test /gaps
    resp = client.get(f"/api/playback/{stream_id}/gaps?date={date_str}")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["duration"] == 100.0
    
    # 3. Test /summary
    resp = client.get(f"/api/playback/{stream_id}/summary?date={date_str}")
    assert resp.status_code == 200
    assert resp.json()["gaps"] == 1
    assert resp.json()["coverage_percent"] == 98.3
