import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Camera, CameraStream, StreamState, ProfileType
from .stream_manager import stream_manager
from .recording_provider import recording_provider, MediaMTXRecordingProvider

@pytest.mark.asyncio
async def test_stream_state_transitions():
    """Test transitions of the stream state machine."""
    # Mock database session
    session = AsyncMock(spec=AsyncSession)
    
    # Mock camera stream
    stream = CameraStream(
        id=uuid.uuid4(),
        camera_id=uuid.uuid4(),
        stream_id="test_stream_main",
        profile_type=ProfileType.MAIN,
        resolution="1920x1080",
        fps=15,
        codec="H264",
        stream_url="rtsp://localhost:8554/test_stream",
        status=StreamState.REGISTERED
    )
    
    # Transition to CONNECTING
    with patch("app.redis_client.RedisManager.set_stream_state", new_callable=AsyncMock) as mock_redis:
        await stream_manager.set_stream_state(session, stream, StreamState.CONNECTING)
        assert stream.status == StreamState.CONNECTING
        mock_redis.assert_called_once_with("test_stream_main", "CONNECTING", None)
        session.commit.assert_called_once()
        
    # Transition to ONLINE
    session.commit.reset_mock()
    with patch("app.redis_client.RedisManager.set_stream_state", new_callable=AsyncMock) as mock_redis:
        await stream_manager.set_stream_state(session, stream, StreamState.ONLINE)
        assert stream.status == StreamState.ONLINE
        mock_redis.assert_called_once_with("test_stream_main", "ONLINE", None)
        session.commit.assert_called_once()

@pytest.mark.asyncio
async def test_add_stream_mediamtx_rtsp():
    """Test dynamic path creation on MediaMTX for an RTSP source."""
    session = AsyncMock(spec=AsyncSession)
    
    stream = CameraStream(
        id=uuid.uuid4(),
        camera_id=uuid.uuid4(),
        stream_id="test_stream_main",
        profile_type=ProfileType.MAIN,
        resolution="1920x1080",
        fps=15,
        codec="H264",
        stream_url="rtsp://camera_ip:554/h264",
        status=StreamState.REGISTERED,
        always_on=True
    )
    
    # Mock HTTP response
    mock_response = MagicMock()
    mock_response.status_code = 201
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post, \
         patch.object(stream_manager, "set_stream_state", new_callable=AsyncMock) as mock_state:
        
        await stream_manager.add_stream(session, stream)
        
        # Verify MediaMTX config add API URL and body
        mock_post.assert_called_once_with(
            "http://localhost:9997/v3/config/paths/add/test_stream_main",
            json={
                "source": "rtsp://camera_ip:554/h264",
                "sourceOnDemand": False,
                "record": True
            }
        )
        # Verify state transitioned to CONNECTING
        mock_state.assert_called_once_with(session, stream, StreamState.CONNECTING)

@pytest.mark.asyncio
async def test_add_stream_mediamtx_push():
    """Test dynamic path creation on MediaMTX for an Edge Push source."""
    session = AsyncMock(spec=AsyncSession)
    
    stream = CameraStream(
        id=uuid.uuid4(),
        camera_id=uuid.uuid4(),
        stream_id="edge_camera_main",
        profile_type=ProfileType.MAIN,
        resolution="1920x1080",
        fps=15,
        codec="H264",
        stream_url="publisher", # Edge Push publisher
        status=StreamState.REGISTERED,
        always_on=True
    )
    
    mock_response = MagicMock()
    mock_response.status_code = 201
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post, \
         patch.object(stream_manager, "set_stream_state", new_callable=AsyncMock) as mock_state:
        
        await stream_manager.add_stream(session, stream)
        
        mock_post.assert_called_once_with(
            "http://localhost:9997/v3/config/paths/add/edge_camera_main",
            json={
                "source": "publisher",
                "sourceOnDemand": False,
                "record": True,
                "runOnDemand": "ffmpeg -re -f lavfi -i testsrc=size=640x480:rate=15 -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p -f rtsp -rtsp_transport tcp rtsp://localhost:8554/edge_camera_main"
            }
        )
        mock_state.assert_called_once_with(session, stream, StreamState.CONNECTING)

@pytest.mark.asyncio
async def test_recording_provider_toggles():
    """Test standard interfaces in the RecordingProvider Abstraction Layer."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"record": True}
    
    with patch("httpx.AsyncClient.patch", new_callable=AsyncMock, return_value=mock_response) as mock_patch, \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response) as mock_get:
        
        # 1. Start recording
        await recording_provider.start_recording("test_stream_main")
        mock_patch.assert_called_with(
            "http://localhost:9997/v3/config/paths/patch/test_stream_main",
            json={"record": True}
        )
        
        # 2. Stop recording
        await recording_provider.stop_recording("test_stream_main")
        mock_patch.assert_called_with(
            "http://localhost:9997/v3/config/paths/patch/test_stream_main",
            json={"record": False}
        )
        
        # 3. Check recording status
        status = await recording_provider.get_recording_status("test_stream_main")
        assert status is True
        mock_get.assert_called_with(
            "http://localhost:9997/v3/config/paths/get/test_stream_main"
        )
