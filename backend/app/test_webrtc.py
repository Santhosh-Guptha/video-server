import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from .main import app
from .config import settings
from .models import WebRTCSession, CameraStream, StreamState, ProfileType
from .webrtc import StatsPayload

client = TestClient(app)

@pytest.mark.asyncio
async def test_ice_servers_endpoint():
    """Test retrieving STUN/TURN configurations."""
    with patch("app.config.settings.enable_webrtc", True), \
         patch("app.config.settings.turn_server_url", "turn:localhost:3478"), \
         patch("app.config.settings.turn_server_username", "vms_user"), \
         patch("app.config.settings.turn_server_credential", "vms_turn_password"):
        
        resp = client.get("/api/webrtc/ice-servers")
        assert resp.status_code == 200
        data = resp.json()
        assert "iceServers" in data
        assert len(data["iceServers"]) >= 1
        
        turn_servers = [s for s in data["iceServers"] if "urls" in s and any("turn:" in u for u in s["urls"])]
        assert len(turn_servers) == 1
        assert turn_servers[0]["username"] == "vms_user"
        assert turn_servers[0]["credential"] == "vms_turn_password"

@pytest.mark.asyncio
async def test_ice_servers_disabled():
    """Test retrieving STUN/TURN configurations when WebRTC is disabled."""
    with patch("app.config.settings.enable_webrtc", False):
        resp = client.get("/api/webrtc/ice-servers")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "WebRTC is disabled"

@pytest.mark.asyncio
async def test_report_and_get_stats():
    """Test reporting stream statistics and retrieving aggregated stats."""
    stream_id = "test_stream_stats"
    session_id = "test_sess_123"
    
    payload = {
        "session_id": session_id,
        "fps": 30.0,
        "resolution": "1920x1080",
        "bitrate": 1500.0,
        "rtt": 25.0,
        "packet_loss": 0.01,
        "jitter": 2.0,
        "frames_dropped": 0,
        "decoder_latency": 12.0
    }
    
    mock_db_session = AsyncMock(spec=AsyncSession)
    
    from .db import get_session
    async def override_get_session():
        yield mock_db_session
        
    app.dependency_overrides[get_session] = override_get_session
    
    try:
        # Report stats via API
        resp = client.post(f"/api/webrtc/streams/{stream_id}/stats", json=payload)
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()
        
        # Get stream stats
        mock_active_session = WebRTCSession(
            session_id=session_id,
            stream_id=stream_id,
            status="ACTIVE",
            protocol="WHEP",
            client_ip="127.0.0.1"
        )
        
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [mock_active_session]
        mock_db_session.execute.return_value = mock_res
        
        resp = client.get(f"/api/webrtc/streams/{stream_id}/stats")
        assert resp.status_code == 200
        stats_data = resp.json()
        assert stats_data["active_viewers"] == 1
        assert stats_data["avg_fps"] == 30.0
        assert stats_data["avg_bitrate_kbps"] == 1500.0
        
    finally:
        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_whep_signaling_proxy():
    """Test WHEP signaling POST endpoint proxying SDP to MediaMTX."""
    stream_id = "test_whep_stream"
    sdp_offer = "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\nc=IN IP4 127.0.0.1"
    sdp_answer = "v=0\r\no=- 1 0 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\nc=IN IP4 127.0.0.1"
    
    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = mock_execute_result
    
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.headers = {
        "Location": f"http://mediamtx/v3/webrtcsessions/{stream_id}/whep/session_xyz",
        "Content-Type": "application/sdp"
    }
    mock_response.content = sdp_answer.encode()
    
    from .db import get_session
    async def override_get_session():
        yield mock_db_session
        
    app.dependency_overrides[get_session] = override_get_session
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post, \
         patch("app.webrtc.create_db_session", new_callable=AsyncMock) as mock_create_db, \
         patch("app.redis_viewer_tracker.RedisViewerTracker.get_viewer_count", new_callable=AsyncMock, return_value=0), \
         patch("app.redis_viewer_tracker.RedisViewerTracker.add_viewer_session", new_callable=AsyncMock) as mock_add_viewer:
             
        try:
            resp = client.post(
                f"/api/streams/{stream_id}/live/whep",
                content=sdp_offer,
                headers={"Content-Type": "application/sdp"}
            )
            
            assert resp.status_code == 201
            assert resp.headers["Location"] == f"/api/streams/{stream_id}/live/whep/session_xyz"
            assert resp.text == sdp_answer
            
            mock_post.assert_called_once()
            mock_create_db.assert_called_once()
            mock_add_viewer.assert_called_once()
            
        finally:
            app.dependency_overrides.clear()
