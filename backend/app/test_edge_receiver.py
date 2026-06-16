import pytest
import asyncio
import struct
import json
import base64
import time
from unittest.mock import AsyncMock, patch, MagicMock

from app.models import CameraStream, StreamState, EdgeConnection
from app.edge_receiver import (
    handle_client,
    metrics,
    PROXY_METADATA_COMMAND,
    PROXY_METADATA_IMAGE,
    PROXY_COMMAND_TYPE_CAMERA_CONFIG,
    MAX_PACKET_SIZE
)


@pytest.mark.asyncio
async def test_edge_receiver_config_and_disconnect():
    # Setup mocks
    mock_reader = AsyncMock()
    mock_writer = MagicMock()
    mock_writer.get_extra_info.return_value = ("127.0.0.1", 9999)

    # Reset metrics
    metrics["active_edge_connections"] = 0
    metrics["active_ffmpeg_relays"] = 0
    metrics["packet_parse_errors"] = 0
    metrics["watchdog_timeouts"] = 0

    # Mock CONFIG packet payload
    camera_id = "EDGE_CAM_TEST"
    req_payload = {
        "cameraId": camera_id,
        "width": 640,
        "height": 360,
        "configParam": "c3BzX2J5dGVzLHBwc19ieXRlcw==",  # base64 representation
        "encoderType": 3  # H264
    }
    config_bytes = json.dumps(req_payload).encode()

    # Packet body: magic_type (1) + cmd_type (5) + padding (4 bytes) + config_bytes
    body = (
        struct.pack(">B", PROXY_METADATA_COMMAND) +
        struct.pack(">B", PROXY_COMMAND_TYPE_CAMERA_CONFIG) +
        struct.pack(">I", 0) +
        config_bytes
    )

    # Mock readexactly to return packet, then raise IncompleteReadError to stop loop
    mock_reader.readexactly.side_effect = [
        struct.pack(">I", len(body)),
        body,
        asyncio.IncompleteReadError(b"", 4)
    ]

    # Mock DB session and camera lookup
    from app.models import Camera
    mock_camera = Camera(
        source_camera_id=123,
        name="test_cam",
        active=True,
        synced_from_api=True
    )
    mock_stream = CameraStream(
        stream_id=camera_id,
        status=StreamState.REGISTERED,
        stream_url="publisher"
    )
    mock_stream.camera = mock_camera

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.add = MagicMock()

    # Make mock_session.execute return mock_stream
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_stream
    mock_session.execute.return_value = mock_result

    # Async generator mock for get_session
    async def mock_get_session():
        yield mock_session

    # Mock subprocess
    mock_subprocess = AsyncMock()
    mock_subprocess.stdin = AsyncMock()
    mock_subprocess.stdin.write = MagicMock()
    mock_subprocess.returncode = None

    # Patch database session generator, stream manager, and process executions
    with patch("app.edge_receiver.get_session", side_effect=mock_get_session), \
         patch("app.edge_receiver.stream_manager.set_stream_state", new_callable=AsyncMock) as mock_set_state, \
         patch("asyncio.create_subprocess_exec", return_value=mock_subprocess) as mock_exec, \
         patch("app.edge_receiver.cleanup_ffmpeg", new_callable=AsyncMock) as mock_cleanup:

        await handle_client(mock_reader, mock_writer)

        # Verify validations
        assert mock_exec.called
        assert mock_set_state.called
        # Verify db insert log
        assert mock_session.add.called
        added_obj = mock_session.add.call_args[0][0]
        assert isinstance(added_obj, EdgeConnection)
        assert added_obj.camera_id == camera_id

        # Verify cleanup on disconnect
        assert mock_cleanup.called


@pytest.mark.asyncio
async def test_edge_receiver_max_packet_protection():
    mock_reader = AsyncMock()
    mock_writer = MagicMock()
    mock_writer.get_extra_info.return_value = ("127.0.0.1", 9999)

    # Set packet size header > 10MB
    oversized_len = MAX_PACKET_SIZE + 1024
    mock_reader.readexactly.side_effect = [
        struct.pack(">I", oversized_len)
    ]

    metrics["packet_parse_errors"] = 0

    await handle_client(mock_reader, mock_writer)

    # Verify parsing error metric and connection closed
    assert metrics["packet_parse_errors"] == 1
    assert mock_writer.close.called
