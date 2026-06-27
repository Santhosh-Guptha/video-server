import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from .policy_loader import PolicyLoader
from .transcoding_decision_engine import TranscodingDecisionEngine
from .session_registry import SessionRegistry, SessionState
from .event_bus import EventBus
from .stream_router import StreamRouter
from .transcoding_client import TranscodingClient
from .models import CameraStream

@pytest.mark.asyncio
async def test_policy_loader():
    """Verify that PolicyLoader loads values from yaml config files dynamically."""
    # Fetch default settings from stream_policy.yaml
    val = PolicyLoader.get("stream_policy.yaml", "enable_adaptive_profile", False)
    assert isinstance(val, bool)
    
    # Check that a default is returned if file/key is missing
    missing_val = PolicyLoader.get("nonexistent.yaml", "any_key", "default_val")
    assert missing_val == "default_val"

@pytest.mark.asyncio
async def test_decision_engine():
    """Verify routing decisions based on codec, capabilities, and overrides."""
    # Case 1: H.264 -> Always Direct
    route = await TranscodingDecisionEngine.determine_route(
        codec="H264",
        client_profile={"supports_h265": False}
    )
    assert route == "direct"

    # Case 2: H.265 + Browser Native H265 Support -> Direct
    route = await TranscodingDecisionEngine.determine_route(
        codec="H265",
        client_profile={"supports_h265": True}
    )
    assert route == "direct"

    # Case 3: H.265 + No Native Browser Support + Cloud Healthy -> Cloud
    await TranscodingDecisionEngine.set_cloud_health(True)
    route = await TranscodingDecisionEngine.determine_route(
        codec="H265",
        client_profile={"supports_h265": False}
    )
    assert route == "cloud"

    # Case 4: H.265 + No Native Browser Support + Cloud Unhealthy -> Local Fallback
    await TranscodingDecisionEngine.set_cloud_health(False)
    route = await TranscodingDecisionEngine.determine_route(
        codec="H265",
        client_profile={"supports_h265": False}
    )
    assert route == "local"

@pytest.mark.asyncio
async def test_session_registry():
    """Verify registering, retrieving, renaming, and unregistering sessions in SessionRegistry."""
    session = SessionState(
        session_id="test_sess_1",
        stream_id="cam_stream_123",
        session_type="live",
        source_type="cloud",
        codec="H265"
    )
    
    # Register
    await SessionRegistry.register_session(session)
    fetched = await SessionRegistry.get_session("test_sess_1")
    assert fetched is not None
    assert fetched.stream_id == "cam_stream_123"
    assert fetched.source_type == "cloud"

    # Rename
    success = await SessionRegistry.rename_session("test_sess_1", "test_sess_renamed")
    assert success is True
    
    old_fetched = await SessionRegistry.get_session("test_sess_1")
    assert old_fetched is None
    
    new_fetched = await SessionRegistry.get_session("test_sess_renamed")
    assert new_fetched is not None
    assert new_fetched.stream_id == "cam_stream_123"

    # Fetch for stream
    sessions = await SessionRegistry.get_sessions_for_stream("cam_stream_123")
    assert len(sessions) == 1
    assert sessions[0].session_id == "test_sess_renamed"

    # Unregister
    removed = await SessionRegistry.unregister_session("test_sess_renamed")
    assert removed is not None
    
    final_fetch = await SessionRegistry.get_session("test_sess_renamed")
    assert final_fetch is None

@pytest.mark.asyncio
async def test_event_bus():
    """Verify pub-sub pattern in EventBus is non-blocking and triggers subscribers."""
    triggered = False
    received_data = None
    
    async def sample_callback(data):
        nonlocal triggered, received_data
        triggered = True
        received_data = data

    await EventBus.subscribe("test_event", sample_callback)
    await EventBus.publish("test_event", {"val": 42})
    
    # Yield to let the async task execute
    await asyncio.sleep(0.1)
    
    assert triggered is True
    assert received_data == {"val": 42}
    
    # Unsubscribe
    await EventBus.unsubscribe("test_event", sample_callback)

@pytest.mark.asyncio
async def test_stream_router_playback():
    """Verify playback routing specs for H.264 vs H.265 based on client profiles."""
    stream_h264 = CameraStream(stream_id="cam_h264", codec="H264")
    stream_h265 = CameraStream(stream_id="cam_h265", codec="H265")

    # Playback H.264 -> Never transcode
    specs = await StreamRouter.route_playback(stream_h264, 0.0, 10.0, {"supports_h265": False})
    assert specs["transcode"] is False
    assert specs["vcodec"] == "copy"

    # Playback H.265 with H.265 supported browser -> copy (direct)
    specs = await StreamRouter.route_playback(stream_h265, 0.0, 10.0, {"supports_h265": True})
    assert specs["transcode"] is False
    assert specs["vcodec"] == "copy"

    # Playback H.265 with H.264 only browser -> transcode
    specs = await StreamRouter.route_playback(stream_h265, 0.0, 10.0, {"supports_h265": False})
    assert specs["transcode"] is True
    assert specs["vcodec"] == "libx264"
