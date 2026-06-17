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
    from .config import settings
    old_val = settings.strict_camera_validation
    settings.strict_camera_validation = False
    async def override():
        yield mock_db_session
    app.dependency_overrides[get_session] = override
    yield mock_db_session
    app.dependency_overrides.clear()
    settings.strict_camera_validation = old_val

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


@pytest.mark.asyncio
async def test_playback_recovery_providers():
    from .providers import get_playback_recovery_provider, UNVProvider, GenericProvider, HikvisionProvider
    
    # Test factory mapping
    assert isinstance(get_playback_recovery_provider("UNV"), UNVProvider)
    assert isinstance(get_playback_recovery_provider("Uniview"), UNVProvider)
    assert isinstance(get_playback_recovery_provider("Hikvision"), HikvisionProvider)
    assert isinstance(get_playback_recovery_provider(None), GenericProvider)
    assert isinstance(get_playback_recovery_provider("UnknownBrand"), GenericProvider)

    # Mock stream objects
    class MockCamera:
        def __init__(self, name, make):
            self.name = name
            self.make = make

    class MockStream:
        def __init__(self, url, make=None):
            self.stream_url = url
            self.camera = MockCamera("test_cam", make)

    # Test UNV Playback URL builder
    unv_stream = MockStream("rtsp://admin:pass@192.168.1.100:554/unicast/c2/s1/live", "UNV")
    unv_provider = get_playback_recovery_provider("UNV")
    unv_url = unv_provider.build_playback_url(unv_stream, 1781280300.0, 1781280360.0)
    assert unv_url == "rtsp://admin:pass@192.168.1.100:554/c2/b1781280300/e1781280360/replay/"

    # Test Generic Playback URL builder
    gen_stream = MockStream("rtsp://192.168.1.150/live", None)
    gen_provider = get_playback_recovery_provider(None)
    gen_url = gen_provider.build_playback_url(gen_stream, 1781280300.0, 1781280360.0)
    assert "starttime=" in gen_url
    assert "endtime=" in gen_url


@pytest.mark.asyncio
async def test_edge_upload_endpoint_unauthorized_policy(override_db):
    """Test that unauthorized upload is rejected with 403 when allow_unknown_edge_devices is False."""
    from .config import settings
    # Setup policy to FALSE (default)
    settings.allow_unknown_edge_devices = False

    # Mock DB returns None for stream_id
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    override_db.execute.return_value = mock_res

    # Send file
    file_payload = {"file": ("20260613_005534_recovered.mp4", b"dummy mp4 data", "video/mp4")}
    form_payload = {"stream_id": "unknown_edge_stream"}

    resp = client.post("/api/edge/upload", data=form_payload, files=file_payload)
    assert resp.status_code == 403
    assert "Forbidden" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_edge_upload_endpoint_success(override_db):
    """Test successful edge backlog file upload with validation, saving, and DB recording."""
    from .config import settings
    settings.allow_unknown_edge_devices = False
    
    # Mock valid Camera and Stream
    from .models import Camera
    mock_camera = Camera(
        source_camera_id=1234,
        name="test_cam",
        active=True,
        make="UNV",
        synced_from_api=True
    )
    mock_stream = CameraStream(
        stream_id="valid_stream",
        camera_id=uuid.uuid4(),
        profile_type=ProfileType.MAIN,
        resolution="1920x1080",
        fps=15,
        stream_url="rtsp://dummy",
        status=StreamState.ONLINE
    )
    mock_stream.camera = mock_camera

    # DB executes: 1. query stream/camera, 2. query duplicate check
    mock_res_stream = MagicMock()
    mock_res_stream.scalar_one_or_none.return_value = mock_stream
    
    mock_res_dup = MagicMock()
    mock_res_dup.scalar_one_or_none.return_value = None # No duplicates
    
    override_db.execute.side_effect = [mock_res_stream, mock_res_dup]

    with patch("pathlib.Path.mkdir"), \
         patch("app.main.open", create=True) as mock_open, \
         patch("app.main.get_file_duration", return_value=60.0):

        file_payload = {"file": ("20260613_005530.mp4", b"data", "video/mp4")}
        form_payload = {"stream_id": "valid_stream"}

        resp = client.post("/api/edge/upload", data=form_payload, files=file_payload)
        assert resp.status_code == 200
        
        res_json = resp.json()
        assert res_json["status"] == "success"
        # 20260613_005530 -> timestamp is 1781312130 (depending on timezone, let's verify it gets parsed)
        assert res_json["start_ts"] is not None
        assert res_json["end_ts"] == res_json["start_ts"] + 60.0
        
        # Verify db insert
        override_db.add.assert_called_once()
        added_segment = override_db.add.call_args[0][0]
        assert isinstance(added_segment, RecordingSegment)
        assert added_segment.stream_id == "valid_stream"
        override_db.commit.assert_called_once()
