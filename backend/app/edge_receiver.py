import asyncio
import struct
import json
import base64
import time
import uuid
from datetime import datetime
from sqlalchemy import select
from .config import settings
from .db import get_session
from .models import CameraStream, StreamState, EdgeConnection
from .stream_manager import stream_manager

# ================= PROTOCOL CONSTANTS =================
PROXY_METADATA_COMMAND = 0x01
PROXY_METADATA_IMAGE = 0x02
PROXY_COMMAND_TYPE_CAMERA_CONFIG = 0x05

MAX_PACKET_SIZE = 10 * 1024 * 1024  # 10 MB
EDGE_SOCKET_TIMEOUT = 30.0  # 30 seconds

# ================= GLOBAL STATE & METRICS =============
metrics = {
    "active_edge_connections": 0,
    "active_ffmpeg_relays": 0,
    "total_bytes_received": 0,
    "packet_parse_errors": 0,
    "watchdog_timeouts": 0,
    "ffmpeg_failures": 0,
}

# Real-time memory registry for active connections: camera_id -> connection dict
active_connections = {}


async def cleanup_ffmpeg(proc):
    """Guarantees terminating and waiting on the FFmpeg process, force killing if necessary."""
    if proc is None:
        return
    print(f"[edge_receiver] Cleaning up FFmpeg process (PID={proc.pid})")
    try:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            print(f"[edge_receiver] FFmpeg process {proc.pid} did not exit on terminate. Force killing...")
            proc.kill()
            await proc.wait()
    except Exception as e:
        print(f"[edge_receiver] Error cleaning up FFmpeg process: {e}")


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peername = writer.get_extra_info('peername')
    client_ip = peername[0] if peername else "unknown"
    print(f"[edge_receiver] New connection from {client_ip}")

    # Track metrics
    metrics["active_edge_connections"] += 1

    session_id = uuid.uuid4()
    connection_db_id = None
    camera_id = None
    ffmpeg_proc = None
    watchdog_task = None
    last_frame_received_ts = time.time()
    bytes_received_session = 0

    # Watchdog task for frame inactivity
    async def watchdog_loop():
        nonlocal last_frame_received_ts
        try:
            while True:
                await asyncio.sleep(5)
                if time.time() - last_frame_received_ts > EDGE_SOCKET_TIMEOUT:
                    print(f"[edge_receiver] Frame watchdog timeout: no video frames for {EDGE_SOCKET_TIMEOUT}s for camera {camera_id}. Disconnecting.")
                    metrics["watchdog_timeouts"] += 1
                    writer.close()
                    break
        except asyncio.CancelledError:
            pass
        except Exception as ex:
            print(f"[edge_receiver] Watchdog loop exception: {ex}")

    try:
        while True:
            # 1. Read packet length (4-byte big-endian uint32)
            try:
                len_bytes = await asyncio.wait_for(reader.readexactly(4), timeout=EDGE_SOCKET_TIMEOUT)
            except asyncio.TimeoutError:
                print(f"[edge_receiver] Socket timeout reading packet header from {client_ip} (idle for {EDGE_SOCKET_TIMEOUT}s). Disconnecting.")
                metrics["watchdog_timeouts"] += 1
                break
            except (asyncio.IncompleteReadError, ConnectionResetError):
                break

            bytes_received_session += 4
            metrics["total_bytes_received"] += 4
            if camera_id and camera_id in active_connections:
                active_connections[camera_id]["bytes_received"] += 4

            pkt_len = struct.unpack(">I", len_bytes)[0]
            if pkt_len > MAX_PACKET_SIZE:
                print(f"[edge_receiver] Warning: Packet size limit exceeded ({pkt_len} bytes) from {client_ip}. Disconnecting client.")
                metrics["packet_parse_errors"] += 1
                break

            # 2. Read packet body
            try:
                body = await asyncio.wait_for(reader.readexactly(pkt_len), timeout=EDGE_SOCKET_TIMEOUT)
            except asyncio.TimeoutError:
                print(f"[edge_receiver] Socket timeout reading packet body from {client_ip}. Disconnecting.")
                metrics["watchdog_timeouts"] += 1
                break
            except (asyncio.IncompleteReadError, ConnectionResetError):
                break

            bytes_received_session += pkt_len
            metrics["total_bytes_received"] += pkt_len
            if camera_id and camera_id in active_connections:
                active_connections[camera_id]["bytes_received"] += pkt_len

            if not body:
                break

            magic_type = body[0]

            if magic_type == PROXY_METADATA_COMMAND:
                command_type = body[1]
                if command_type == PROXY_COMMAND_TYPE_CAMERA_CONFIG:
                    # body[2:6] are unused padding, body[6:] is JSON camera config
                    try:
                        config_json = json.loads(body[6:].decode('utf-8'))
                    except Exception as e:
                        print(f"[edge_receiver] JSON config parsing error: {e}")
                        metrics["packet_parse_errors"] += 1
                        break

                    camera_id = config_json.get("cameraId")
                    encoder_type = config_json.get("encoderType")  # 3 = H264, 10 = H265
                    config_param = config_json.get("configParam")

                    if not camera_id:
                        print("[edge_receiver] Config packet has missing cameraId.")
                        metrics["packet_parse_errors"] += 1
                        break

                    print(f"[edge_receiver] CAMERA_CONFIG received for {camera_id}: encoder_type={encoder_type}")

                    # Validate camera ID in database
                    async for db_session in get_session():
                        stmt = select(CameraStream).where(CameraStream.stream_id == camera_id)
                        res = await db_session.execute(stmt)
                        stream = res.scalar_one_or_none()

                        if not stream:
                            print(f"[edge_receiver] Unauthorized camera ID registration attempt: {camera_id}")
                            metrics["packet_parse_errors"] += 1
                            writer.close()
                            return

                        # Terminate existing connections for this camera
                        if camera_id in active_connections:
                            print(f"[edge_receiver] Duplicate connection for camera {camera_id}. Terminating older session.")
                            old_conn = active_connections[camera_id]
                            try:
                                old_conn["writer"].close()
                            except Exception:
                                pass

                        # Initialize and spawn FFmpeg relayer
                        codec_fmt = "hevc" if encoder_type == 10 else "h264"
                        rtsp_target = f"rtsp://localhost:8554/{camera_id}"
                        cmd = [
                            settings.ffmpeg_path,
                            "-f", codec_fmt,
                            "-i", "pipe:0",
                            "-c:v", "copy",
                            "-f", "rtsp",
                            "-rtsp_transport", "tcp",
                            rtsp_target
                        ]
                        print(f"[edge_receiver] Starting FFmpeg copy relayer: {' '.join(cmd)}")
                        try:
                            ffmpeg_proc = await asyncio.create_subprocess_exec(
                                *cmd,
                                stdin=asyncio.subprocess.PIPE,
                                stdout=asyncio.subprocess.DEVNULL,
                                stderr=asyncio.subprocess.DEVNULL
                            )
                            metrics["active_ffmpeg_relays"] += 1
                        except Exception as fe:
                            print(f"[edge_receiver] Failed to start FFmpeg for camera {camera_id}: {fe}")
                            metrics["ffmpeg_failures"] += 1
                            await stream_manager.set_stream_state(db_session, stream, StreamState.FAILED, f"FFmpeg relay startup failed: {fe}")
                            writer.close()
                            return

                        # Register new connection record in database
                        connection_db_id = uuid.uuid4()
                        db_conn = EdgeConnection(
                            id=connection_db_id,
                            camera_id=camera_id,
                            connected_at=datetime.utcnow(),
                            status="CONNECTED",
                            client_ip=client_ip
                        )
                        db_session.add(db_conn)
                        await db_session.commit()

                        # Update Stream state to ONLINE
                        await stream_manager.set_stream_state(db_session, stream, StreamState.ONLINE)
                        break

                    # Register in memory registry
                    active_connections[camera_id] = {
                        "session_id": session_id,
                        "writer": writer,
                        "ffmpeg_proc": ffmpeg_proc,
                        "connected_at": datetime.utcnow(),
                        "last_frame_ts": datetime.utcnow(),
                        "bytes_received": bytes_received_session,
                        "client_ip": client_ip,
                        "connection_db_id": connection_db_id
                    }

                    # Write configParam base64 SPS/PPS/VPS parameters to FFmpeg stdin
                    if config_param:
                        try:
                            parts = config_param.split(",")
                            for part in parts:
                                part = part.strip()
                                if part:
                                    nal_bytes = base64.b64decode(part)
                                    if not (nal_bytes.startswith(b"\x00\x00\x00\x01") or nal_bytes.startswith(b"\x00\x00\x01")):
                                        nal_bytes = b"\x00\x00\x00\x01" + nal_bytes
                                    ffmpeg_proc.stdin.write(nal_bytes)
                            await ffmpeg_proc.stdin.drain()
                        except Exception as ex:
                            print(f"[edge_receiver] Error writing initial codec params to FFmpeg for {camera_id}: {ex}")

                    # Start watchdog loop task
                    watchdog_task = asyncio.create_task(watchdog_loop())

            elif magic_type == PROXY_METADATA_IMAGE:
                if not camera_id:
                    print("[edge_receiver] Received image frame before CONFIG packet. Disconnecting.")
                    metrics["packet_parse_errors"] += 1
                    break

                # Parse lengths and frame payload
                # Byte 1: encoder type
                # Bytes 2-5: json header length
                hdr_len = struct.unpack(">I", body[2:6])[0]
                nal_len_offset = 6 + hdr_len
                nal_len = struct.unpack(">I", body[nal_len_offset : nal_len_offset + 4])[0]
                nal = body[nal_len_offset + 4 : nal_len_offset + 4 + nal_len]

                # Update frame flow tracking
                last_frame_received_ts = time.time()
                if camera_id in active_connections:
                    active_connections[camera_id]["last_frame_ts"] = datetime.utcnow()

                # Feed FFmpeg pipe
                if ffmpeg_proc and ffmpeg_proc.returncode is None:
                    try:
                        ffmpeg_proc.stdin.write(nal)
                        await ffmpeg_proc.stdin.drain()
                    except (OSError, BrokenPipeError, ConnectionResetError) as ex:
                        print(f"[edge_receiver] FFmpeg pipe broken for camera {camera_id}: {ex}")
                        break
                else:
                    print(f"[edge_receiver] FFmpeg relayer process has stopped unexpectedly for {camera_id}.")
                    break

            else:
                print(f"[edge_receiver] Unknown magic type: {magic_type} from {client_ip}.")
                metrics["packet_parse_errors"] += 1
                break

    except Exception as e:
        print(f"[edge_receiver] Error handling client connection: {e}")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        print(f"[edge_receiver] Connection closed for {client_ip} / {camera_id}")

        # Metrics updates
        metrics["active_edge_connections"] -= 1

        # Cancel watchdog task
        if watchdog_task:
            watchdog_task.cancel()
            try:
                await watchdog_task
            except asyncio.CancelledError:
                pass

        # Cleanup FFmpeg process
        if ffmpeg_proc:
            metrics["active_ffmpeg_relays"] -= 1
            await cleanup_ffmpeg(ffmpeg_proc)

        # Cleanup memory registry and update Database stream status / connection history
        if camera_id:
            # Check if this connection was indeed the active one registered
            if active_connections.get(camera_id, {}).get("session_id") == session_id:
                active_connections.pop(camera_id, None)

                async for db_session in get_session():
                    stmt = select(CameraStream).where(CameraStream.stream_id == camera_id)
                    res = await db_session.execute(stmt)
                    stream = res.scalar_one_or_none()
                    if stream:
                        # Revert status to OFFLINE
                        await stream_manager.set_stream_state(db_session, stream, StreamState.OFFLINE, "Edge push client disconnected")
                    break

            # Update database connection history log
            if connection_db_id:
                async for db_session in get_session():
                    stmt = select(EdgeConnection).where(EdgeConnection.id == connection_db_id)
                    res = await db_session.execute(stmt)
                    db_conn = res.scalar_one_or_none()
                    if db_conn:
                        db_conn.disconnected_at = datetime.utcnow()
                        db_conn.last_frame_ts = datetime.fromtimestamp(last_frame_received_ts)
                        db_conn.bytes_received = bytes_received_session
                        # Differentiate between timeout vs graceful exit
                        if time.time() - last_frame_received_ts > EDGE_SOCKET_TIMEOUT:
                            db_conn.status = "TIMEOUT"
                        else:
                            db_conn.status = "DISCONNECTED"
                        await db_session.commit()
                    break


async def start_edge_receiver():
    """Starts the asyncio TCP server for custom edge device push connections."""
    print(f"[edge_receiver] Starting Custom TCP Edge Push Receiver on {settings.edge_receiver_host}:{settings.edge_receiver_port}...")
    try:
        server = await asyncio.start_server(
            handle_client,
            settings.edge_receiver_host,
            settings.edge_receiver_port
        )
        async with server:
            await server.serve_forever()
    except Exception as e:
        print(f"[edge_receiver] Failed to run TCP Edge Push Server: {e}")
