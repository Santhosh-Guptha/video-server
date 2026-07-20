"""
camera_watchdog.py — Dual Camera Health & Edge Push Watchdog

Two background loops:

1. camera_health_watchdog_loop() — runs every CAMERA_PING_INTERVAL_SECONDS (default: 120s)
   Priority chain per stream:
     P1: Recent Edge Push → skip all checks, ensure path=publisher
     P2: MediaMTX ready=true → ONLINE (RTSP_PULL), no ffprobe
     P3: MediaMTX ready=false → ffprobe RTSP → CONNECTING or OFFLINE

2. edge_push_watchdog_loop() — runs every EDGE_PUSH_CHECK_INTERVAL_SECONDS (default: 30s)
   Detects stale push heartbeats and reverts EDGE_PUSH → RTSP_PULL automatically.

All MediaMTX updates use PATCH only — never DELETE+ADD.
"""

import asyncio
import time
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import (
    CAMERA_PING_INTERVAL_SECONDS,
    CAMERA_PING_MAX_CONCURRENT,
    CAMERA_PING_TIMEOUT_SECONDS,
    EDGE_PUSH_CHECK_INTERVAL_SECONDS,
    EDGE_PUSH_HEARTBEAT_TIMEOUT_SECONDS,
    settings,
)
from .db import get_session
from .models import Camera, CameraStream, ProfileType, StreamState
from .redis_client import RedisManager
from .stream_manager import stream_manager, double_escape_rtsp_url


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _ffprobe_rtsp(rtsp_url: str, timeout_seconds: int) -> bool:
    """
    Checks if the RTSP port is open on the host.
    Replaces heavy ffprobe process with a lightweight TCP socket probe
    to avoid overloading physical cameras and exhausting RTSP connection limits.
    """
    import urllib.parse
    import socket
    
    host = ""
    port = 554
    
    # Parse RTSP URL
    if "://" in rtsp_url:
        try:
            # Handle user:pass@host:port/path
            parsed = urllib.parse.urlparse(rtsp_url)
            host = parsed.hostname or ""
            if parsed.port:
                port = parsed.port
        except Exception:
            pass
            
    if not host:
        # Fallback manual parse
        try:
            clean = rtsp_url.split("://", 1)[-1]
            clean = clean.split("@")[-1]  # remove credentials
            clean = clean.split("/")[0]   # remove path
            if ":" in clean:
                parts = clean.split(":", 1)
                host = parts[0]
                port = int(parts[1])
            else:
                host = clean
        except Exception:
            return False
            
    if not host:
        return False

    # Perform lightweight TCP socket check
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=float(timeout_seconds)
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


async def _patch_mediamtx(path_name: str, payload: dict) -> bool:
    """
    PATCH a MediaMTX path config. Returns True on success.
    If the path doesn't exist, attempts to ADD it.
    """
    from .stream_manager import _mtx_request
    try:
        resp = await _mtx_request("PATCH", f"{settings.mediamtx_api_url}/v3/config/paths/patch/{path_name}", json=payload, timeout=5.0)
        if resp.status_code in (200, 201):
            return True
        # Path may not exist yet — try adding
        if resp.status_code in (400, 404):
            add_resp = await _mtx_request("POST", f"{settings.mediamtx_api_url}/v3/config/paths/add/{path_name}", json=payload, timeout=5.0)
            return add_resp.status_code in (200, 201)
    except Exception as e:
        print(f"[watchdog] MediaMTX PATCH failed for {path_name}: {e}")
    return False


def _has_recent_push(last_push_ts: float | None) -> bool:
    """Returns True if a push heartbeat was seen within the EDGE_PUSH_HEARTBEAT_TIMEOUT window."""
    if last_push_ts is None:
        return False
    return (time.time() - last_push_ts) < EDGE_PUSH_HEARTBEAT_TIMEOUT_SECONDS


def _is_valid_rtsp(url: str) -> bool:
    """Returns True if the URL looks like a real RTSP source (not publisher/empty)."""
    if not url:
        return False
    url = url.strip().lower()
    return (
        url.startswith(("rtsp://", "rtsps://", "rtmp://"))
        and "publisher" not in url
        and url not in ("rtsp://", "rtsps://", "rtmp://")
    )


# ─────────────────────────────────────────────────────────────────────────────
# Watchdog 1 — Camera Health (every 120 seconds)
# ─────────────────────────────────────────────────────────────────────────────

async def camera_health_watchdog_loop():
    """
    Background loop that checks camera health every CAMERA_PING_INTERVAL_SECONDS.
    Runs camera health check by grouping streams per active Camera and validating
    reachability of preferred or fallback RTSP profiles.
    """
    from sqlalchemy.orm import selectinload
    from .webrtc import resolve_stream_by_identifier
    print(f"[watchdog] Camera health watchdog starting (interval={CAMERA_PING_INTERVAL_SECONDS}s)...")

    # Initial delay so system boots fully before first check
    await asyncio.sleep(15.0)

    semaphore = asyncio.Semaphore(CAMERA_PING_MAX_CONCURRENT)

    while True:
        try:
            from .stream_manager import _mtx_request
            # ── 1. Fetch active cameras from DB ──────────────────────────
            active_cameras: list[Camera] = []
            async for session in get_session():
                res = await session.execute(
                    select(Camera)
                    .options(selectinload(Camera.streams))
                    .where(Camera.active == True)
                )
                active_cameras = list(res.scalars().all())

            if not active_cameras:
                await asyncio.sleep(CAMERA_PING_INTERVAL_SECONDS)
                continue

            print(f"[watchdog] Health check cycle: {len(active_cameras)} active cameras")

            # ── 2. Fetch MediaMTX runtime path status ────────────────────
            mediamtx_ready: dict[str, bool] = {}
            try:
                resp = await _mtx_request(
                    "GET",
                    f"{settings.mediamtx_api_url}/v3/paths/list?page=0&itemsPerPage=10000"
                )
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict) and "name" in item:
                                mediamtx_ready[item["name"]] = item.get("ready", False) is True
                    elif isinstance(items, dict):
                        for name, item in items.items():
                            mediamtx_ready[name] = item.get("ready", False) is True
            except Exception as e:
                print(f"[watchdog] Failed to query MediaMTX path status: {e}")

            # ── 3. Process each camera ────────────────────────────────────
            async def check_camera_health(camera: Camera):
                if not camera.streams:
                    return

                path_name = camera.server_camera_id or camera.name or camera.streams[0].stream_id
                
                async with semaphore:
                    # ── P1: Check for active Edge Push ──────────────────
                    last_push_ts = await RedisManager.get_last_push_seen(path_name)
                    
                    recent_db_ts = None
                    for s in camera.streams:
                        if s.last_push_seen:
                            ts_val = s.last_push_seen.timestamp()
                            if recent_db_ts is None or ts_val > recent_db_ts:
                                recent_db_ts = ts_val
                                
                    if last_push_ts is None and recent_db_ts is not None:
                        last_push_ts = recent_db_ts

                    if _has_recent_push(last_push_ts):
                        async for session in get_session():
                            best_stream = await resolve_stream_by_identifier(path_name, session)
                            if not best_stream:
                                best_stream = camera.streams[0]
                                
                            if best_stream.stream_source != "EDGE_PUSH":
                                print(f"[watchdog] {path_name}: Active edge push detected → switching to EDGE_PUSH")
                                from .stream_manager import should_record_stream
                                rec_val = await should_record_stream(session, best_stream)
                                ok = await _patch_mediamtx(path_name, {
                                    "source": "publisher",
                                    "sourceOnDemand": False,
                                    "record": rec_val,
                                })
                                if ok:
                                    stream_db = await session.get(CameraStream, best_stream.id)
                                    if stream_db:
                                        stream_db.stream_source = "EDGE_PUSH"
                                        await session.commit()
                                        await stream_manager.set_stream_state(
                                            session, stream_db, StreamState.ONLINE
                                        )
                        return

                    # ── P2: MediaMTX reports path is ready ──────────────
                    if mediamtx_ready.get(path_name, False):
                        async for session in get_session():
                            best_stream = await resolve_stream_by_identifier(path_name, session)
                            if not best_stream:
                                best_stream = camera.streams[0]
                            if best_stream.status != StreamState.ONLINE:
                                stream_db = await session.get(CameraStream, best_stream.id)
                                if stream_db:
                                    stream_db.stream_source = "RTSP_PULL"
                                    await session.commit()
                                    await stream_manager.set_stream_state(
                                        session, stream_db, StreamState.ONLINE
                                    )
                        return

                    # ── P3: MediaMTX path not ready — ping primary RTSP url, fallback to secondary
                    async for session in get_session():
                        best_stream = await resolve_stream_by_identifier(path_name, session)
                        if not best_stream:
                            best_stream = camera.streams[0]
                            
                        rtsp_url = best_stream.stream_url.strip() if best_stream.stream_url else ""
                        
                        reachable = False
                        if _is_valid_rtsp(rtsp_url):
                            print(f"[watchdog] {path_name}: checking primary stream...")
                            reachable = await _ffprobe_rtsp(rtsp_url, CAMERA_PING_TIMEOUT_SECONDS)
                            
                        if reachable:
                            print(f"[watchdog] {path_name}: primary RTSP reachable → CONNECTING")
                            from .stream_manager import should_record_stream
                            rec_val = await should_record_stream(session, best_stream)
                            await _patch_mediamtx(path_name, {
                                "source": double_escape_rtsp_url(rtsp_url),
                                "sourceProtocol": "tcp",
                                "sourceOnDemand": True,
                                "record": rec_val,
                            })
                            stream_db = await session.get(CameraStream, best_stream.id)
                            if stream_db:
                                stream_db.stream_source = "RTSP_PULL"
                                await session.commit()
                                if stream_db.status not in (StreamState.CONNECTING, StreamState.ONLINE):
                                    await stream_manager.set_stream_state(
                                        session, stream_db, StreamState.CONNECTING
                                    )
                            return

                        # Primary not reachable. Try fallback (the other profile)
                        fallback_stream = next((s for s in camera.streams if s.id != best_stream.id), None)
                        fallback_reachable = False
                        fallback_rtsp = fallback_stream.stream_url.strip() if (fallback_stream and fallback_stream.stream_url) else ""
                        
                        if fallback_stream and _is_valid_rtsp(fallback_rtsp):
                            print(f"[watchdog] {path_name}: primary unreachable, trying fallback profile...")
                            fallback_reachable = await _ffprobe_rtsp(fallback_rtsp, CAMERA_PING_TIMEOUT_SECONDS)
                            
                        if fallback_reachable:
                            print(f"[watchdog] {path_name}: fallback RTSP reachable → CONNECTING fallback")
                            from .stream_manager import should_record_stream
                            rec_val = await should_record_stream(session, fallback_stream)
                            await _patch_mediamtx(path_name, {
                                "source": double_escape_rtsp_url(fallback_rtsp),
                                "sourceProtocol": "tcp",
                                "sourceOnDemand": True,
                                "record": rec_val,
                            })
                            
                            fallback_db = await session.get(CameraStream, fallback_stream.id)
                            if fallback_db:
                                fallback_db.stream_source = "RTSP_PULL"
                                await session.commit()
                                await stream_manager.set_stream_state(
                                    session, fallback_db, StreamState.CONNECTING
                                )
                                
                            pref_db = await session.get(CameraStream, best_stream.id)
                            if pref_db:
                                await stream_manager.set_stream_state(
                                    session, pref_db, StreamState.OFFLINE, "Primary offline, fallback active"
                                )
                            return

                        # Both unreachable → OFFLINE
                        print(f"[watchdog] {path_name}: both primary and fallback unreachable")
                        for s in camera.streams:
                            s_db = await session.get(CameraStream, s.id)
                            if s_db and s_db.status != StreamState.OFFLINE:
                                await stream_manager.set_stream_state(
                                    session, s_db, StreamState.OFFLINE,
                                    "Primary and fallback RTSP unreachable"
                                )

            await asyncio.gather(*[check_camera_health(c) for c in active_cameras])

        except Exception as e:
            print(f"[watchdog] Error in camera health watchdog: {e}")

        print(f"[watchdog] Health check cycle complete. Next in {CAMERA_PING_INTERVAL_SECONDS}s.")
        await asyncio.sleep(CAMERA_PING_INTERVAL_SECONDS)


# ─────────────────────────────────────────────────────────────────────────────
# Watchdog 2 — Edge Push Heartbeat (every 30 seconds)
# ─────────────────────────────────────────────────────────────────────────────

async def edge_push_watchdog_loop():
    """
    Background loop that detects stale edge push heartbeats and reverts
    EDGE_PUSH streams back to RTSP_PULL when the push device disconnects.

    Runs every EDGE_PUSH_CHECK_INTERVAL_SECONDS (default: 30s).
    """
    from sqlalchemy.orm import selectinload
    from .webrtc import resolve_stream_by_identifier
    print(f"[watchdog] Edge push watchdog starting (interval={EDGE_PUSH_CHECK_INTERVAL_SECONDS}s)...")

    # Small delay so health watchdog starts first
    await asyncio.sleep(5.0)

    while True:
        try:
            async for session in get_session():
                # Find all active cameras
                res = await session.execute(
                    select(Camera)
                    .options(selectinload(Camera.streams))
                    .where(Camera.active == True)
                )
                active_cameras = list(res.scalars().all())

                for camera in active_cameras:
                    if not camera.streams:
                        continue
                    path_name = camera.server_camera_id or camera.name or camera.streams[0].stream_id
                    
                    # Check if any stream of this camera is currently marked as EDGE_PUSH
                    push_stream = next((s for s in camera.streams if s.stream_source == "EDGE_PUSH"), None)
                    if not push_stream:
                        continue
                        
                    # Check last push heartbeat
                    last_push_ts = await RedisManager.get_last_push_seen(path_name)
                    if last_push_ts is None and push_stream.last_push_seen:
                        last_push_ts = push_stream.last_push_seen.timestamp()

                    if _has_recent_push(last_push_ts):
                        continue

                    # Heartbeat timed out → revert to RTSP_PULL
                    best_stream = await resolve_stream_by_identifier(path_name, session)
                    if not best_stream:
                        best_stream = push_stream
                        
                    rtsp_url = best_stream.stream_url.strip() if best_stream.stream_url else ""
                    print(
                        f"[watchdog] {path_name}: Edge push heartbeat expired "
                        f"({EDGE_PUSH_HEARTBEAT_TIMEOUT_SECONDS}s) → reverting to RTSP_PULL"
                    )

                    if _is_valid_rtsp(rtsp_url):
                        patched = await _patch_mediamtx(path_name, {
                            "source": double_escape_rtsp_url(rtsp_url),
                            "sourceProtocol": "tcp",
                            "sourceOnDemand": not best_stream.always_on,
                        })
                        if patched:
                            print(f"[watchdog] {path_name}: Patched MediaMTX source → {rtsp_url}")
                        else:
                            print(f"[watchdog] {path_name}: Failed to patch MediaMTX source to RTSP URL")
                    else:
                        print(f"[watchdog] {path_name}: No valid RTSP URL for revert — marking OFFLINE")

                    stream_db = await session.get(CameraStream, best_stream.id)
                    if stream_db:
                        stream_db.stream_source = "RTSP_PULL"
                        await session.commit()
                        await stream_manager.set_stream_state(
                            session, stream_db,
                            StreamState.CONNECTING if _is_valid_rtsp(rtsp_url) else StreamState.OFFLINE,
                            None if _is_valid_rtsp(rtsp_url) else "Edge push disconnected, no RTSP fallback"
                        )

                    await RedisManager.clear_last_push_seen(path_name)

        except Exception as e:
            print(f"[watchdog] Error in edge push watchdog: {e}")

        await asyncio.sleep(EDGE_PUSH_CHECK_INTERVAL_SECONDS)
