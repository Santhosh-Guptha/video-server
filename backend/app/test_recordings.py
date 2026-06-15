import pytest
import uuid
import os
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from .main import app, SegmentCompletePayload
from .models import RecordingSegment, CameraStream, StreamState, ProfileType
from .indexer import index_recordings

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
async def test_webhook_successful_registration(override_db):
    """Test successful segment complete webhook registration."""
    stream_id = "test_stream_rec"
    file_path = "/app/data/recordings/test_stream_rec/2026-06-13/20260613_005534_recovered.mp4"
    
    # 1. Mock DB call: Stream must exist
    mock_stream = CameraStream(
        stream_id=stream_id,
        camera_id=uuid.uuid4(),
        profile_type=ProfileType.MAIN,
        resolution="1920x1080",
        fps=15,
        stream_url="rtsp://dummy",
        status=StreamState.ONLINE
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_stream
    override_db.execute.return_value = mock_res
    
    # 2. Mock Path existence and size/mtime
    with patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.stat") as mock_stat, \
         patch("app.main.get_file_duration", return_value=12.0):
             
        # Mock file size = 1000 bytes, mtime (end_ts) = 1781280363.0
        mock_stat_val = MagicMock()
        mock_stat_val.st_size = 1000
        mock_stat_val.st_mtime = 1781280363.0
        mock_stat.return_value = mock_stat_val
        
        payload = {
            "stream_id": stream_id,
            "file_path": file_path
        }
        
        resp = client.post("/api/recordings/segment-complete", json=payload)
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        
        # Verify RecordingSegment insertion
        override_db.add.assert_called_once()
        added_segment = override_db.add.call_args[0][0]
        assert isinstance(added_segment, RecordingSegment)
        assert added_segment.stream_id == stream_id
        assert added_segment.file_path == file_path
        assert added_segment.end_ts == 1781280363.0
        assert added_segment.start_ts == 1781280363.0 - 12.0 # Derived start time
        override_db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_webhook_duplicate_registration(override_db):
    """Test duplicate webhook registration is handled gracefully (returns 200)."""
    stream_id = "test_stream_rec"
    file_path = "/app/data/recordings/test_stream_rec/2026-06-13/duplicate.mp4"
    
    mock_stream = CameraStream(
        stream_id=stream_id,
        camera_id=uuid.uuid4(),
        profile_type=ProfileType.MAIN,
        resolution="1920x1080",
        fps=15,
        stream_url="rtsp://dummy",
        status=StreamState.ONLINE
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_stream
    override_db.execute.return_value = mock_res
    
    # Force commit to raise IntegrityError for duplicate record conflict
    from sqlalchemy.exc import IntegrityError
    override_db.commit.side_effect = IntegrityError("Unique constraint", {}, None)
    
    with patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.stat") as mock_stat, \
         patch("app.main.get_file_duration", return_value=10.0):
             
        mock_stat_val = MagicMock()
        mock_stat_val.st_size = 1000
        mock_stat_val.st_mtime = 1781280363.0
        mock_stat.return_value = mock_stat_val
        
        payload = {
            "stream_id": stream_id,
            "file_path": file_path
        }
        
        resp = client.post("/api/recordings/segment-complete", json=payload)
        # Duplicate should be ignored and still return 200 ok
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        override_db.rollback.assert_called_once()

@pytest.mark.asyncio
async def test_webhook_missing_file(override_db):
    """Test webhook fails with 400 when file does not exist."""
    stream_id = "test_stream_rec"
    
    # Mock stream exists
    mock_stream = CameraStream(stream_id=stream_id, camera_id=uuid.uuid4(), profile_type=ProfileType.MAIN, resolution="1920x1080", fps=15, stream_url="rtsp://dummy", status=StreamState.ONLINE)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_stream
    override_db.execute.return_value = mock_res

    with patch("pathlib.Path.exists", return_value=False):
        payload = {
            "stream_id": stream_id,
            "file_path": "/missing/file.mp4"
        }
        resp = client.post("/api/recordings/segment-complete", json=payload)
        assert resp.status_code == 400
        assert "File does not exist" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_webhook_zero_byte_file(override_db):
    """Test webhook fails with 400 when file size is zero."""
    stream_id = "test_stream_rec"
    mock_stream = CameraStream(stream_id=stream_id, camera_id=uuid.uuid4(), profile_type=ProfileType.MAIN, resolution="1920x1080", fps=15, stream_url="rtsp://dummy", status=StreamState.ONLINE)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_stream
    override_db.execute.return_value = mock_res

    with patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.stat") as mock_stat:
             
        mock_stat_val = MagicMock()
        mock_stat_val.st_size = 0 # 0 bytes!
        mock_stat.return_value = mock_stat_val
        
        payload = {
            "stream_id": stream_id,
            "file_path": "/app/zero.mp4"
        }
        resp = client.post("/api/recordings/segment-complete", json=payload)
        assert resp.status_code == 400
        assert "File size is zero" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_ffprobe_duration_extraction():
    """Test that ffprobe duration extraction handles subprocess calls successfully."""
    mock_subprocess_res = MagicMock()
    mock_subprocess_res.returncode = 0
    mock_subprocess_res.stdout = '{"format": {"duration": "15.45"}}'
    
    with patch("subprocess.run", return_value=mock_subprocess_res) as mock_run:
        from .main import get_file_duration
        duration = get_file_duration("/dummy/file.mp4")
        assert duration == 15.45
        mock_run.assert_called_once()

@pytest.mark.asyncio
async def test_recovery_scanner_indexes_missing(mock_db_session):
    """Test that recovery scanner detects and indexes files not present in the database."""
    # 1. Scanned filesystem reports 1 file
    scanned_data = [{
        "stream_id": "cam_1",
        "file_path": "/data/recordings/cam_1/2026-06-13/file1.mp4",
        "mtime": 1000.0,
        "name": "file1.mp4"
    }]
    
    # 2. Database contains no indexed paths (returns empty)
    res_empty_db = MagicMock()
    res_empty_db.scalars.return_value.all.return_value = []
    
    # 3. Stream cam_1 is registered
    res_registered = MagicMock()
    res_registered.scalars.return_value.all.return_value = ["cam_1"]
    
    mock_db_session.execute.side_effect = [res_empty_db, res_registered]
    
    with patch("app.indexer.scan_files_sync", return_value=scanned_data):
        await index_recordings(mock_db_session, "/dummy/recording_dir")
        
        # Verify a new RecordingSegment was added to database
        mock_db_session.add.assert_called_once()
        added = mock_db_session.add.call_args[0][0]
        assert isinstance(added, RecordingSegment)
        assert added.stream_id == "cam_1"
        assert added.file_path == "/data/recordings/cam_1/2026-06-13/file1.mp4"
        mock_db_session.commit.assert_called_once()

@pytest.mark.asyncio
async def test_recovery_scanner_ignores_already_indexed(mock_db_session):
    """Test that recovery scanner ignores files already indexed in database."""
    file_path = "/data/recordings/cam_1/2026-06-13/indexed.mp4"
    scanned_data = [{
        "stream_id": "cam_1",
        "file_path": file_path,
        "mtime": 1000.0,
        "name": "indexed.mp4"
    }]
    
    # Database already contains this file path
    res_indexed_db = MagicMock()
    res_indexed_db.scalars.return_value.all.return_value = [file_path]
    
    # Stream cam_1 is registered
    res_registered = MagicMock()
    res_registered.scalars.return_value.all.return_value = ["cam_1"]
    
    mock_db_session.execute.side_effect = [res_indexed_db, res_registered]
    
    with patch("app.indexer.scan_files_sync", return_value=scanned_data):
        await index_recordings(mock_db_session, "/dummy/recording_dir")
        
        # Verify no additions or commits happened
        mock_db_session.add.assert_not_called()
