import asyncio
import os
import httpx
import struct
import json
import base64
import time
import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .config import settings
from .db import get_session
from .models import CameraStream, StreamState, EdgeConnection, Camera, ProfileType
from .stream_manager import stream_manager
from .redis_client import RedisManager

# ================= PROTOCOL CONSTANTS =================
PROXY_METADATA_COMMAND = 0x01
PROXY_METADATA_IMAGE = 0x02
PROXY_COMMAND_TYPE_CAMERA_CONFIG = 0x05

MAX_PACKET_SIZE = 10 * 1024 * 1024  # 10 MB
EDGE_SOCKET_TIMEOUT = 45.0  # 45 seconds
MAX_FFMPEG_RESTARTS = 3  # Max FFmpeg restart attempts per connection

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
unregistered_attempts = {}


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
                        stmt = (
                            select(CameraStream)
                            .options(selectinload(CameraStream.camera))
                            .where(CameraStream.stream_id == camera_id)
                        )
                        res = await db_session.execute(stmt)
                        stream = res.scalar_one_or_none()

                        # Check if camera ID is in local edge push whitelist
                        whitelisted_cams = set()
                        possible_paths = [
                            "edge_push_config.json",
                            "../edge-push/edge-push/edge_push_config.json",
                            "edge-push/edge-push/edge_push_config.json",
                        ]
                        for p in possible_paths:
                            if os.path.exists(p):
                                try:
                                    with open(p, "r") as f:
                                        data = json.load(f)
                                    whitelisted_cams = {item.get("cameraId") for item in data if item.get("cameraId")}
                                    break
                                except Exception as e:
                                    print(f"[edge_receiver] Error loading whitelist from {p}: {e}")
                        
                        is_whitelisted = camera_id in whitelisted_cams

                        is_valid = False
                        if settings.strict_camera_validation and not is_whitelisted:
                            if stream:
                                camera = stream.camera
                                if camera and camera.active:
                                    is_valid = True
                            if not is_valid:
                                print(f"[edge_receiver] Rejected camera: camera_id={camera_id} reason=inactive")
                                await RedisManager.increment_counter("rejected_edge_connections")
                        else:
                            # Open Mode OR Whitelisted camera (auto-register if missing)
                            if stream:
                                is_valid = True
                            else:
                                # Auto-register camera and stream
                                try:
                                    from sqlalchemy import func
                                    max_id_stmt = select(func.max(Camera.source_camera_id))
                                    max_id_res = await db_session.execute(max_id_stmt)
                                    max_id = max_id_res.scalar() or 0
                                    new_source_id = max(max_id + 1, 900000)

                                    camera = Camera(
                                        source_camera_id=new_source_id,
                                        name=camera_id,
                                        active=True,
                                        make="Generic",
                                        synced_from_api=False
                                    )
                                    db_session.add(camera)
                                    await db_session.flush()

                                    stream = CameraStream(
                                        camera_id=camera.id,
                                        stream_id=camera_id,
                                        profile_type=ProfileType.MAIN,
                                        resolution="1920x1080",
                                        fps=15,
                                        codec="H265" if encoder_type == 10 else "H264",
                                        stream_url="",
                                        status=StreamState.REGISTERED,
                                        always_on=True,
                                    )
                                    db_session.add(stream)
                                    await db_session.flush()
                                    await stream_manager.add_stream(db_session, stream)
                                    await db_session.commit()
                                    is_valid = True
                                    print(f"[edge_receiver] Auto-registered whitelisted/open-mode camera: {camera_id} (codec={stream.codec})")
                                except Exception as auto_reg_err:
                                    await db_session.rollback()
                                    print(f"[edge_receiver] Auto-registration failed for {camera_id}: {auto_reg_err}")

                        # Mode verification
                        if is_valid and stream:
                            if stream.stream_mode == "PULL":
                                print(f"[edge_receiver] Rejecting edge push for camera {camera_id}: Camera configured as PULL only")
                                await RedisManager.increment_counter("rejected_edge_connections")
                                is_valid = False

                        if not is_valid:
                            print(f"[edge_receiver] Rejecting unauthorized camera connection: {camera_id}")
                            metrics["packet_parse_errors"] += 1
                            
                            # Track this unregistered push attempt in memory
                            now_time = datetime.utcnow()
                            if camera_id in unregistered_attempts:
                                unregistered_attempts[camera_id]["last_seen"] = now_time
                                unregistered_attempts[camera_id]["bytes_received"] += bytes_received_session
                                unregistered_attempts[camera_id]["client_ip"] = client_ip
                            else:
                                unregistered_attempts[camera_id] = {
                                    "camera_id": camera_id,
                                    "client_ip": client_ip,
                                    "first_seen": now_time,
                                    "last_seen": now_time,
                                    "bytes_received": bytes_received_session,
                                    "status": "UNAUTHORIZED"
                                }
                            
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

                        # Dynamically patch MediaMTX path config to publisher to accept edge push relayer
                        # Use should_record() to respect HD-only recording policy:
                        # MAIN/HD streams → record=True, NORMAL/SUB streams → record=False
                        from .stream_manager import should_record
                        record_for_push = should_record(stream) if stream else True

                        async with httpx.AsyncClient() as client:
                            url = f"{settings.mediamtx_api_url}/v3/config/paths/patch/{camera_id}"
                            payload = {
                                "source": "publisher",
                                "sourceOnDemand": False,
                                "record": record_for_push,
                                "runOnDemand": "",
                                "runOnUnDemand": ""
                            }
                            try:
                                resp = await client.patch(url, json=payload, timeout=5.0)
                                if resp.status_code in (200, 201):
                                    print(f"[edge_receiver] Patched MediaMTX path {camera_id} config to source=publisher (record={record_for_push}).")
                                else:
                                    # Try adding path if not exists (although it should exist)
                                    add_url = f"{settings.mediamtx_api_url}/v3/config/paths/add/{camera_id}"
                                    await client.post(add_url, json=payload, timeout=5.0)
                                    print(f"[edge_receiver] Added MediaMTX path {camera_id} with source=publisher (record={record_for_push}).")
                            except Exception as e:
                                print(f"[edge_receiver] Error patching MediaMTX path config for {camera_id}: {e}")

                        # Initialize and spawn FFmpeg relayer
                        codec_fmt = "hevc" if encoder_type == 10 else "h264"
                        rtsp_target = f"rtsp://127.0.0.1:8554/{camera_id}"
                        cmd = [
                            settings.ffmpeg_path,
                            "-use_wallclock_as_timestamps", "1",
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
                                stderr=asyncio.subprocess.PIPE
                            )
                            metrics["active_ffmpeg_relays"] += 1
                            # Background task to log FFmpeg stderr
                            async def _log_ffmpeg_stderr(proc, cam_id):
                                try:
                                    while True:
                                        line = await proc.stderr.readline()
                                        if not line:
                                            break
                                        print(f"[edge_receiver] FFmpeg stderr [{cam_id}]: {line.decode('utf-8', errors='replace').strip()}")
                                except Exception:
                                    pass
                            asyncio.create_task(_log_ffmpeg_stderr(ffmpeg_proc, camera_id))
                        except Exception as fe:
                            print(f"[edge_receiver] Failed to start FFmpeg for camera {camera_id}: {fe}")
                            metrics["ffmpeg_failures"] += 1
                            await stream_manager.set_stream_state(db_session, stream, StreamState.FAILED, f"FFmpeg relay startup failed: {fe}")
                            writer.close()
                            return

                        # Update Stream source and heartbeat before setting ONLINE state
                        stream.stream_source = "EDGE_PUSH"
                        stream.last_push_seen = datetime.utcnow()
                        stream.pull_failed_since = None

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

                # Update frame flow tracking and heartbeat
                now_dt = datetime.utcnow()
                last_frame_received_ts = time.time()
                if camera_id in active_connections:
                    active_connections[camera_id]["last_frame_ts"] = now_dt

                # Update Redis heartbeat cache
                await RedisManager.set_last_push_seen(camera_id, last_frame_received_ts)

                # Throttle database write to once per 10 seconds
                last_db_write = active_connections.get(camera_id, {}).get("last_db_heartbeat_ts", 0.0)
                if last_frame_received_ts - last_db_write > 10.0:
                    if camera_id in active_connections:
                        active_connections[camera_id]["last_db_heartbeat_ts"] = last_frame_received_ts
                    async def _update_db_heartbeat(cam_id, timestamp_dt):
                        try:
                            async for db_session in get_session():
                                stmt = select(CameraStream).where(CameraStream.stream_id == cam_id)
                                res = await db_session.execute(stmt)
                                db_stream = res.scalar_one_or_none()
                                if db_stream:
                                    db_stream.last_push_seen = timestamp_dt
                                    db_stream.pull_failed_since = None
                                    await db_session.commit()
                                break
                        except Exception as ex:
                            print(f"[edge_receiver] Heartbeat DB update failed: {ex}")
                    asyncio.create_task(_update_db_heartbeat(camera_id, now_dt))

                # Feed FFmpeg pipe
                if ffmpeg_proc and ffmpeg_proc.returncode is None:
                    try:
                        ffmpeg_proc.stdin.write(nal)
                        await ffmpeg_proc.stdin.drain()
                    except (OSError, BrokenPipeError, ConnectionResetError) as ex:
                        print(f"[edge_receiver] FFmpeg pipe broken for camera {camera_id}: {ex}. Attempting restart...")
                        # Try to restart FFmpeg relay
                        ffmpeg_restart_count = getattr(ffmpeg_proc, '_restart_count', 0)
                        if ffmpeg_restart_count < MAX_FFMPEG_RESTARTS:
                            await cleanup_ffmpeg(ffmpeg_proc)
                            metrics["active_ffmpeg_relays"] -= 1
                            try:
                                ffmpeg_proc = await asyncio.create_subprocess_exec(
                                    *cmd,
                                    stdin=asyncio.subprocess.PIPE,
                                    stdout=asyncio.subprocess.DEVNULL,
                                    stderr=asyncio.subprocess.PIPE
                                )
                                ffmpeg_proc._restart_count = ffmpeg_restart_count + 1
                                metrics["active_ffmpeg_relays"] += 1
                                asyncio.create_task(_log_ffmpeg_stderr(ffmpeg_proc, camera_id))
                                # Re-send the current NAL unit
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
                                    except Exception:
                                        pass
                                # Update active_connections
                                if camera_id in active_connections:
                                    active_connections[camera_id]["ffmpeg_proc"] = ffmpeg_proc
                                print(f"[edge_receiver] FFmpeg relay restarted for {camera_id} (attempt {ffmpeg_proc._restart_count}/{MAX_FFMPEG_RESTARTS})")
                                continue
                            except Exception as restart_err:
                                print(f"[edge_receiver] FFmpeg restart failed for {camera_id}: {restart_err}")
                                metrics["ffmpeg_failures"] += 1
                                break
                        else:
                            print(f"[edge_receiver] Max FFmpeg restarts reached for {camera_id}. Disconnecting.")
                            break
                else:
                    # FFmpeg process has exited
                    ffmpeg_restart_count = getattr(ffmpeg_proc, '_restart_count', 0) if ffmpeg_proc else MAX_FFMPEG_RESTARTS
                    if ffmpeg_restart_count < MAX_FFMPEG_RESTARTS:
                        print(f"[edge_receiver] FFmpeg relayer process stopped for {camera_id}. Attempting restart...")
                        if ffmpeg_proc:
                            await cleanup_ffmpeg(ffmpeg_proc)
                            metrics["active_ffmpeg_relays"] -= 1
                        try:
                            ffmpeg_proc = await asyncio.create_subprocess_exec(
                                *cmd,
                                stdin=asyncio.subprocess.PIPE,
                                stdout=asyncio.subprocess.DEVNULL,
                                stderr=asyncio.subprocess.PIPE
                            )
                            ffmpeg_proc._restart_count = ffmpeg_restart_count + 1
                            metrics["active_ffmpeg_relays"] += 1
                            asyncio.create_task(_log_ffmpeg_stderr(ffmpeg_proc, camera_id))
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
                                except Exception:
                                    pass
                            if camera_id in active_connections:
                                active_connections[camera_id]["ffmpeg_proc"] = ffmpeg_proc
                            print(f"[edge_receiver] FFmpeg relay restarted for {camera_id} (attempt {ffmpeg_proc._restart_count}/{MAX_FFMPEG_RESTARTS})")
                            continue
                        except Exception as restart_err:
                            print(f"[edge_receiver] FFmpeg restart failed for {camera_id}: {restart_err}")
                            metrics["ffmpeg_failures"] += 1
                            break
                    else:
                        print(f"[edge_receiver] Max FFmpeg restarts reached for {camera_id}. Disconnecting.")
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
