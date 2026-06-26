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
from .stream_manager import stream_manager


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _ffprobe_rtsp(rtsp_url: str, timeout_seconds: int) -> bool:
    """
    Runs ffprobe against the given RTSP URL with a hard timeout.
    Returns True if the stream is reachable, False otherwise.
    Designed to be minimal: exits as soon as the stream metadata is read.
    """
    cmd = [
        settings.ffmpeg_path.replace("ffmpeg", "ffprobe") if "ffmpeg" in settings.ffmpeg_path else "ffprobe",
        "-v", "quiet",
        "-rtsp_transport", "tcp",
        "-i", rtsp_url,
        "-show_entries", "stream=codec_type",
        "-of", "default=noprint_wrappers=1",
        "-timeout", str(timeout_seconds * 1_000_000),  # microseconds
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds + 2)
            return proc.returncode == 0
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return False
    except Exception as e:
        print(f"[watchdog] ffprobe error for {rtsp_url}: {e}")
        return False


async def _patch_mediamtx(client: httpx.AsyncClient, path_name: str, payload: dict) -> bool:
    """
    PATCH a MediaMTX path config. Returns True on success.
    If the path doesn't exist, attempts to ADD it.
    """
    try:
        url = f"{settings.mediamtx_api_url}/v3/config/paths/patch/{path_name}"
        resp = await client.patch(url, json=payload, timeout=5.0)
        if resp.status_code in (200, 201):
            return True
        # Path may not exist yet — try adding
        if resp.status_code in (400, 404):
            add_url = f"{settings.mediamtx_api_url}/v3/config/paths/add/{path_name}"
            add_resp = await client.post(add_url, json=payload, timeout=5.0)
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

    Priority chain per stream:
      1. Active Edge Push  → keep as EDGE_PUSH, skip RTSP checks
      2. MediaMTX ready    → ONLINE (RTSP_PULL)
      3. ffprobe RTSP      → CONNECTING if reachable, OFFLINE if not
    """
    print(f"[watchdog] Camera health watchdog starting (interval={CAMERA_PING_INTERVAL_SECONDS}s)...")

    # Initial delay so system boots fully before first check
    await asyncio.sleep(15.0)

    semaphore = asyncio.Semaphore(CAMERA_PING_MAX_CONCURRENT)

    while True:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # ── 1. Fetch active streams from DB ──────────────────────────
                active_streams: list[CameraStream] = []
                async for session in get_session():
                    res = await session.execute(
                        select(CameraStream)
                        .join(Camera)
                        .where(Camera.active == True)
                    )
                    active_streams = list(res.scalars().all())

                if not active_streams:
                    await asyncio.sleep(CAMERA_PING_INTERVAL_SECONDS)
                    continue

                print(f"[watchdog] Health check cycle: {len(active_streams)} active streams")

                # ── 2. Fetch MediaMTX runtime path status ────────────────────
                mediamtx_ready: dict[str, bool] = {}
                try:
                    resp = await client.get(
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

                # ── 3. Process each stream ────────────────────────────────────
                async def check_stream(stream: CameraStream):
                    stream_id = stream.stream_id
                    rtsp_url = stream.stream_url.strip() if stream.stream_url else ""

                    async with semaphore:
                        # ── P1: Check for active Edge Push ──────────────────
                        last_push_ts = await RedisManager.get_last_push_seen(stream_id)
                        if last_push_ts is None and stream.last_push_seen:
                            last_push_ts = stream.last_push_seen.timestamp()

                        if _has_recent_push(last_push_ts):
                            # Camera is actively being pushed from an edge device
                            # Ensure MediaMTX path is set to publisher (idempotent PATCH)
                            if stream.stream_source != "EDGE_PUSH":
                                print(f"[watchdog] {stream_id}: Active edge push detected → switching to EDGE_PUSH")
                                ok = await _patch_mediamtx(client, stream_id, {
                                    "source": "publisher",
                                    "sourceOnDemand": False,
                                })
                                if ok:
                                    async for session in get_session():
                                        stream_db = await session.get(CameraStream, stream.id)
                                        if stream_db:
                                            stream_db.stream_source = "EDGE_PUSH"
                                            await session.commit()
                                            await stream_manager.set_stream_state(
                                                session, stream_db, StreamState.ONLINE
                                            )
                            return  # Skip all RTSP checks

                        # ── P2: MediaMTX reports stream as ready ─────────────
                        if mediamtx_ready.get(stream_id, False):
                            # Stream is actively delivering packets — all good
                            if stream.status != StreamState.ONLINE:
                                async for session in get_session():
                                    stream_db = await session.get(CameraStream, stream.id)
                                    if stream_db:
                                        url_strip = (stream_db.stream_url or "").strip()
                                        has_valid_pull = url_strip.startswith(("rtsp://", "rtsps://", "rtmp://"))
                                        stream_db.stream_source = "RTSP_PULL" if has_valid_pull else "EDGE_PUSH"
                                        await session.commit()
                                        await stream_manager.set_stream_state(
                                            session, stream_db, StreamState.ONLINE
                                        )
                            return  # Healthy — nothing to do

                        # ── P3: MediaMTX reports not ready — run ffprobe ─────
                        if not _is_valid_rtsp(rtsp_url):
                            # No valid RTSP source and not ready → OFFLINE
                            if stream.status not in (StreamState.OFFLINE, StreamState.DISABLED):
                                async for session in get_session():
                                    stream_db = await session.get(CameraStream, stream.id)
                                    if stream_db:
                                        await stream_manager.set_stream_state(
                                            session, stream_db, StreamState.OFFLINE,
                                            "No valid RTSP source and not active"
                                        )
                            return

                        print(f"[watchdog] {stream_id}: not ready in MediaMTX — running ffprobe...")
                        reachable = await _ffprobe_rtsp(rtsp_url, CAMERA_PING_TIMEOUT_SECONDS)

                        if reachable:
                            print(f"[watchdog] {stream_id}: RTSP reachable → CONNECTING")
                            async for session in get_session():
                                stream_db = await session.get(CameraStream, stream.id)
                                if stream_db:
                                    stream_db.stream_source = "RTSP_PULL"
                                    await session.commit()
                                    if stream_db.status not in (StreamState.CONNECTING, StreamState.ONLINE):
                                        await stream_manager.set_stream_state(
                                            session, stream_db, StreamState.CONNECTING
                                        )
                        else:
                            print(f"[watchdog] {stream_id}: RTSP unreachable → OFFLINE")
                            async for session in get_session():
                                stream_db = await session.get(CameraStream, stream.id)
                                if stream_db and stream_db.status != StreamState.OFFLINE:
                                    await stream_manager.set_stream_state(
                                        session, stream_db, StreamState.OFFLINE,
                                        "RTSP unreachable (ffprobe timeout)"
                                    )

                # Run checks concurrently (bounded by semaphore)
                await asyncio.gather(*[check_stream(s) for s in active_streams])

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
    print(f"[watchdog] Edge push watchdog starting (interval={EDGE_PUSH_CHECK_INTERVAL_SECONDS}s)...")

    # Small delay so health watchdog starts first
    await asyncio.sleep(5.0)

    while True:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                async for session in get_session():
                    # Find all streams currently marked as EDGE_PUSH
                    res = await session.execute(
                        select(CameraStream)
                        .join(Camera)
                        .where(Camera.active == True)
                        .where(CameraStream.stream_source == "EDGE_PUSH")
                    )
                    push_streams = list(res.scalars().all())

                    for stream in push_streams:
                        stream_id = stream.stream_id

                        # Check last push heartbeat
                        last_push_ts = await RedisManager.get_last_push_seen(stream_id)
                        if last_push_ts is None and stream.last_push_seen:
                            last_push_ts = stream.last_push_seen.timestamp()

                        if _has_recent_push(last_push_ts):
                            # Still active — nothing to do
                            continue

                        # Heartbeat timed out → revert to RTSP_PULL
                        rtsp_url = stream.stream_url.strip() if stream.stream_url else ""
                        print(
                            f"[watchdog] {stream_id}: Edge push heartbeat expired "
                            f"({EDGE_PUSH_HEARTBEAT_TIMEOUT_SECONDS}s) → reverting to RTSP_PULL"
                        )

                        if _is_valid_rtsp(rtsp_url):
                            # Patch MediaMTX source back to RTSP URL
                            patched = await _patch_mediamtx(client, stream_id, {
                                "source": rtsp_url,
                                "sourceProtocol": "tcp",
                                "sourceOnDemand": not stream.always_on,
                            })
                            if patched:
                                print(f"[watchdog] {stream_id}: Patched MediaMTX source → {rtsp_url}")
                            else:
                                print(f"[watchdog] {stream_id}: Failed to patch MediaMTX source to RTSP URL")
                        else:
                            print(f"[watchdog] {stream_id}: No valid RTSP URL for revert — marking OFFLINE")

                        # Update stream state
                        stream_db = await session.get(CameraStream, stream.id)
                        if stream_db:
                            url_strip = (stream_db.stream_url or "").strip()
                            has_valid_pull = url_strip.startswith(("rtsp://", "rtsps://", "rtmp://"))
                            stream_db.stream_source = "RTSP_PULL" if has_valid_pull else "EDGE_PUSH"
                            await session.commit()
                            await stream_manager.set_stream_state(
                                session, stream_db,
                                StreamState.CONNECTING if has_valid_pull else StreamState.OFFLINE,
                                None if has_valid_pull else "Edge push disconnected, no RTSP fallback"
                            )

                        # Clear the stale push heartbeat from Redis
                        await RedisManager.clear_last_push_seen(stream_id)

        except Exception as e:
            print(f"[watchdog] Error in edge push watchdog: {e}")

        await asyncio.sleep(EDGE_PUSH_CHECK_INTERVAL_SECONDS)
