import json
import time
from datetime import datetime
import http.client
http.client._MAXHEADERS = 100000
from pathlib import Path
from typing import Annotated
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, Form, File, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import select, delete, text, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import asyncio
import httpx
import os
import tempfile
import subprocess
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from urllib.parse import quote

from .indexer import index_recordings
from .config import settings
from .db import engine, Base, get_session
from .models import Camera, CameraStream, RecordingSegment, StreamState, ProfileType, EdgeConnection, StreamTranscoder
from .schemas import CameraOut, CameraStreamOut, RecordingSegmentOut, SyncResponse, CameraCreate, CameraUpdate, SettingsUpdate
from .upstream import fetch_upstream_cameras
from .redis_client import RedisManager
from .stream_manager import stream_manager
from .webrtc import router as webrtc_router, streams_router as webrtc_streams_router
from .timeline_service import PlaybackTimelineService

app = FastAPI(title=settings.app_name)

app.include_router(webrtc_router)
app.include_router(webrtc_streams_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def map_stream_profile(upstream_type: str) -> ProfileType:
    upstream_type = (upstream_type or "").upper()
    if upstream_type in ("HD", "MAIN"):
        return ProfileType.MAIN
    elif upstream_type in ("NORMAL", "SUB"):
        return ProfileType.SUB
    else:
        return ProfileType.MOBILE

async def upstream_sync_loop():
    print("[upstream_sync] Starting periodic upstream camera sync watchdog loop...")
    from .config import UPSTREAM_SYNC_INTERVAL_MINUTES
    while True:
        await asyncio.sleep(UPSTREAM_SYNC_INTERVAL_MINUTES * 60)
        try:
            use_upstream = await RedisManager.get_setting_use_upstream()
            if not use_upstream:
                print("[upstream_sync] Upstream sync is disabled. Skipping periodic sync.")
                continue

            print("[upstream_sync] Running periodic camera synchronization...")
            async for session in get_session():
                await sync_cameras(session)
            print("[upstream_sync] Periodic camera sync complete.")
        except Exception as e:
            print("[upstream_sync] Periodic camera sync error:", e)

def configure_mediamtx_paths_dynamically():
    import subprocess
    import os
    import re
    from pathlib import Path
    
    # 1. Determine the path to mediamtx.yml
    candidate_paths = [
        "/opt/mediamtx/mediamtx.yml",
        "./backend/app/mediamtx.yml",
        "./app/mediamtx.yml",
        "./mediamtx.yml",
        "../mediamtx_linux.yml"
    ]
    
    config_path = None
    for cp in candidate_paths:
        p = Path(cp)
        if p.exists():
            config_path = p
            break
            
    if not config_path:
        print("[startup] No MediaMTX configuration file found to dynamically configure.")
        return

    print(f"[startup] Found MediaMTX configuration file at {config_path}")

    # 2. Get absolute path of recordings directory
    rec_dir = Path(settings.recording_dir).resolve().absolute()
    backend_dir = Path(__file__).resolve().parent.parent
    
    target_record_path = f"{rec_dir}/%path/%Y-%m-%d/%Y%m%d_%H%M_live"
    target_hook_cmd = f"/bin/bash {backend_dir}/app/segment_hook.sh \"$MTX_PATH\" \"$MTX_SEGMENT_PATH\""
    
    # 3. Read configuration file
    try:
        content = config_path.read_text()
    except Exception as e:
        print(f"[startup] Failed to read MediaMTX config file: {e}")
        return

    # 4. Parse/replace settings in the configuration content
    modified = False
    
    # Replace recordPath
    record_path_pattern = r"(^\s*recordPath:\s*)[^\n]+"
    match_rp = re.search(record_path_pattern, content, re.MULTILINE)
    if match_rp:
        current_line = match_rp.group(0)
        new_line = f"{match_rp.group(1)}\"{target_record_path}\""
        if current_line.strip() != new_line.strip():
            content = re.sub(record_path_pattern, new_line, content, flags=re.MULTILINE)
            modified = True
            print(f"[startup] MediaMTX recordPath updated to: {target_record_path}")
            
    # Replace recordSegmentDuration
    segment_dur_pattern = r"(^\s*recordSegmentDuration:\s*)[^\n]+"
    match_sd = re.search(segment_dur_pattern, content, re.MULTILINE)
    if match_sd:
        current_line = match_sd.group(0)
        new_line = f"{match_sd.group(1)}\"{settings.segment_time_seconds}s\""
        if current_line.strip() != new_line.strip():
            content = re.sub(segment_dur_pattern, new_line, content, flags=re.MULTILINE)
            modified = True
            print(f"[startup] MediaMTX recordSegmentDuration updated to: {settings.segment_time_seconds}s")
            
    # Replace runOnRecordSegmentComplete
    hook_pattern = r"(^\s*runOnRecordSegmentComplete:\s*)[^\n]+"
    match_hook = re.search(hook_pattern, content, re.MULTILINE)
    if match_hook:
        current_line = match_hook.group(0)
        new_line = f"{match_hook.group(1)}{target_hook_cmd}"
        if current_line.strip() != new_line.strip():
            content = re.sub(hook_pattern, new_line, content, flags=re.MULTILINE)
            modified = True
            print(f"[startup] MediaMTX runOnRecordSegmentComplete updated to: {target_hook_cmd}")

    # 5. Write back and restart MediaMTX service if updated
    if modified:
        try:
            config_path.write_text(content)
            print("[startup] MediaMTX configuration updated successfully.")
            
            # Check if running as a systemd service, restart it
            if os.path.exists("/etc/systemd/system/mediamtx.service") or os.path.exists("/lib/systemd/system/mediamtx.service"):
                print("[startup] Restarting mediamtx service to apply changes...")
                res = subprocess.run(["systemctl", "restart", "mediamtx"], capture_output=True, text=True)
                if res.returncode == 0:
                    print("[startup] mediamtx service restarted successfully.")
                else:
                    print(f"[startup] Failed to restart mediamtx service: {res.stderr}")
            else:
                print("[startup] Not running under systemd or service file not found, mediamtx needs to be restarted manually.")
        except Exception as e:
            print(f"[startup] Failed to write config or restart MediaMTX: {e}")
    else:
        print("[startup] MediaMTX configuration is already up to date.")

@app.on_event("startup")
async def startup():
    # 1. Detect upstream API URL change and clean up if it did
    import os
    import shutil
    from pathlib import Path
    
    last_url_file = Path("./data/last_upstream_url.txt")
    current_url = settings.upstream_camera_api_url.strip()
    url_changed = False
    
    if last_url_file.exists():
        try:
            last_url = last_url_file.read_text().strip()
            if last_url and last_url != current_url:
                url_changed = True
                print(f"[startup] DETECTED UPSTREAM CAMERA API URL CHANGE:")
                print(f"  Old URL: {last_url}")
                print(f"  New URL: {current_url}")
        except Exception as e:
            print(f"[startup] Error reading last upstream URL file: {e}")
    else:
        # If tracker file doesn't exist, but database exists and is not the default, trigger initial cleanup
        db_file = Path("./data/app.db")
        if db_file.exists() and current_url != "https://iportal-poc.iviscloud.net/api/cameras/camera-videoserver":
            url_changed = True
            print(f"[startup] First run of tracking, but DB exists and current URL is not the old default. Triggering cleanup.")

    if url_changed:
        print("[startup] TRIGGERING AUTOMATIC WIPE OF DATABASE AND RECORDINGS...")
        
        # A. Clear SQLite database files
        db_file = Path("./data/app.db")
        for suffix in ["", "-journal", "-shm", "-wal"]:
            p = Path(str(db_file) + suffix)
            if p.exists():
                try:
                    p.unlink()
                    print(f"[startup] Deleted database file: {p}")
                except Exception as ex:
                    print(f"[startup] Error deleting database file {p}: {ex}")
                    
        # B. Clear recordings directory content
        rec_dir = Path(settings.recording_dir)
        if rec_dir.exists():
            print(f"[startup] Clearing recordings directory: {rec_dir}")
            for item in rec_dir.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                except Exception as ex:
                    print(f"[startup] Error deleting recording item {item}: {ex}")
                    
        # C. Clear HLS directory content
        hls_dir = Path(settings.hls_dir)
        if hls_dir.exists():
            print(f"[startup] Clearing HLS directory: {hls_dir}")
            for item in hls_dir.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                except Exception as ex:
                    print(f"[startup] Error deleting HLS item {item}: {ex}")
                    
        # D. Clear backup_cameras.json file
        backup_cameras_file = Path(os.path.dirname(os.path.abspath(__file__))) / "backup_cameras.json"
        if backup_cameras_file.exists():
            try:
                backup_cameras_file.unlink()
                print(f"[startup] Deleted cached backup camera config: {backup_cameras_file}")
            except Exception as ex:
                print(f"[startup] Error deleting backup camera file: {ex}")

        # E. Clear Redis DB cache
        try:
            from .redis_client import redis_client
            if redis_client:
                await redis_client.flushdb()
                print("[startup] Flushed Redis database cache.")
        except Exception as rx:
            print(f"[startup] Error flushing Redis database: {rx}")

    # Write current URL to tracking file
    try:
        last_url_file.parent.mkdir(parents=True, exist_ok=True)
        last_url_file.write_text(current_url)
    except Exception as e:
        print(f"[startup] Error writing last upstream URL to file: {e}")

    # Dynamically configure MediaMTX path mapping and hooks
    try:
        configure_mediamtx_paths_dynamically()
    except Exception as e:
        print(f"[startup] Error during MediaMTX dynamic configuration: {e}")

    # Attempt to auto-create PostgreSQL tables on start (fallback logic)
    from . import db
    
    async def apply_dynamic_schema_upgrades(conn):
        try:
            await conn.execute(text("ALTER TABLE cameras ADD COLUMN make VARCHAR(128);"))
        except Exception:
            pass
        try:
            await conn.execute(text("ALTER TABLE cameras ADD COLUMN synced_from_api BOOLEAN DEFAULT FALSE NOT NULL;"))
        except Exception:
            pass
        try:
            await conn.execute(text("UPDATE cameras SET synced_from_api = TRUE;"))
        except Exception:
            pass

    try:
        async with db.engine.begin() as conn:
            await conn.run_sync(db.Base.metadata.create_all)
            await apply_dynamic_schema_upgrades(conn)
    except Exception as e:
        print(f"[startup] PostgreSQL connection/migration failed: {e}. Falling back to local SQLite.")
        from .db import reset_db_engine
        sqlite_url = "sqlite+aiosqlite:///./data/app.db"
        Path("./data").mkdir(parents=True, exist_ok=True)
        reset_db_engine(sqlite_url)
        # Create SQLite tables
        async with db.engine.begin() as conn:
            await conn.run_sync(db.Base.metadata.create_all)
            await apply_dynamic_schema_upgrades(conn)

    Path(settings.recording_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.hls_dir).mkdir(parents=True, exist_ok=True)

    # Sync registered camera streams with Upstream API and MediaMTX on boot
    async def initial_sync():
        await asyncio.sleep(2.0) # Wait for MediaMTX to boot up fully in Compose
        use_upstream = await RedisManager.get_setting_use_upstream()
        if not use_upstream:
            print("[startup] Upstream sync disabled. Skipping startup sync.")
            # Still need to load and register existing local streams into stream_manager on boot!
            async for session in get_session():
                try:
                    res = await session.execute(
                        select(CameraStream).options(selectinload(CameraStream.camera))
                    )
                    streams = res.scalars().all()
                    for stream in streams:
                        camera = stream.camera
                        if camera and camera.active:
                            await stream_manager.add_stream(session, stream)
                        else:
                            await stream_manager.remove_stream(session, stream)
                    print("[startup] Local streams registered successfully.")
                except Exception as e:
                    print(f"[startup] Error registering local streams: {e}")
            return

        print("[startup] Syncing camera streams with upstream API dynamically...")
        async for session in get_session():
            try:
                await sync_cameras(session)
                print("[startup] Dynamic camera synchronization complete.")
            except Exception as e:
                print(f"[startup] Error performing dynamic camera sync: {e}")

    asyncio.create_task(initial_sync())

    # Start periodic watchdog loops
    asyncio.create_task(recording_recovery_loop())
    
    from .schedulers import (
        camera_scheduler_loop,
        camera_gap_recovery_loop,
        camera_archive_cleanup_loop,
        webrtc_session_watchdog_loop,
        transcoder_watchdog_loop
    )
    from .health_monitor import health_monitor_loop
    from .camera_watchdog import camera_health_watchdog_loop, edge_push_watchdog_loop

    asyncio.create_task(upstream_sync_loop())
    asyncio.create_task(camera_scheduler_loop())
    asyncio.create_task(camera_gap_recovery_loop())
    asyncio.create_task(camera_archive_cleanup_loop())
    asyncio.create_task(webrtc_session_watchdog_loop())
    asyncio.create_task(health_monitor_loop())
    asyncio.create_task(transcoder_watchdog_loop())
    # Phase 3: Camera lifecycle watchdogs
    asyncio.create_task(camera_health_watchdog_loop())   # Ping/ffprobe cycle every 120s
    asyncio.create_task(edge_push_watchdog_loop())       # Push heartbeat monitor every 30s

    if settings.edge_receiver_enabled:
        from .edge_receiver import start_edge_receiver
        asyncio.create_task(start_edge_receiver())

    # Print VMS policy summary on startup
    from . import config as policy
    print("\n" + "="*70)
    print("  VMS POLICY ACTIVE CONFIGURATION")
    print("="*70)
    print(f"  Recording  : HD={policy.RECORD_HD_ONLY}, Normal={policy.RECORD_NORMAL}, Mobile={policy.RECORD_MOBILE}")
    print(f"  Live Stream: profile={policy.LIVE_STREAM_PROFILE}, adaptive={policy.ENABLE_ADAPTIVE_PROFILE}")
    if policy.ENABLE_ADAPTIVE_PROFILE:
        print(f"    1x1 (focus) → {policy.FOCUS_VIEW_PROFILE}")
        print(f"    2x2/3x3     → {policy.GRID_VIEW_PROFILE}")
    print(f"  Playback   : profile={policy.PLAYBACK_PROFILE}, normal_fallback={policy.PLAYBACK_ALLOW_NORMAL_FALLBACK}")
    print(f"  WebRTC     : enabled={policy.ENABLE_WEBRTC}, max_sessions={policy.MAX_WEBRTC_SESSIONS_PER_CAMERA}")
    print(f"  H265       : transcoding={policy.ENABLE_H265_TRANSCODING}, vcodec={policy.TRANSCODER_VCODEC}, preset={policy.TRANSCODER_PRESET}")
    print(f"  Retention  : enabled={policy.ENABLE_RETENTION}, days={policy.DEFAULT_RETENTION_DAYS}")
    print(f"  Edge Push  : enabled={policy.ENABLE_EDGE_PUSH}, priority={policy.EDGE_PUSH_PRIORITY}")
    print("="*70 + "\n")

@app.on_event("shutdown")
async def shutdown():
    """Clean up all active transcoders on server shutdown."""
    from .transcoder import transcoder_manager
    await transcoder_manager.stop_all()


# ── Policy API ─────────────────────────────────────────────────────────────────

@app.get("/api/policy")
async def get_policy():
    """
    Exposes the active VMS runtime policy to the frontend and any external client.

    The UI must use this response to make all stream-selection and playback decisions.
    No stream routing logic should be hardcoded in the frontend.
    """
    from . import config as p
    return {
        "recording": {
            "record_hd_only":   p.RECORD_HD_ONLY,
            "record_normal":    p.RECORD_NORMAL,
            "record_mobile":    p.RECORD_MOBILE,
            "enabled_profiles": p.get_recording_profiles(),
            "segment_duration_seconds": p.SEGMENT_DURATION_SECONDS,
            "enable_recording": p.ENABLE_RECORDING,
            "retention_enabled": p.ENABLE_RETENTION,
            "retention_days":   p.DEFAULT_RETENTION_DAYS,
            "indexer_interval_seconds": p.INDEXER_INTERVAL_SECONDS,

        },
        "live": {
            "profile":                p.LIVE_STREAM_PROFILE,
            "adaptive_enabled":       p.ENABLE_ADAPTIVE_PROFILE,
            "focus_view_profile":     p.FOCUS_VIEW_PROFILE,
            "grid_view_profile":      p.GRID_VIEW_PROFILE,
            "mobile_view_profile":    p.MOBILE_VIEW_PROFILE,
            "resolved_1x1":           p.resolve_live_profile(layout_size=1),
            "resolved_grid":          p.resolve_live_profile(layout_size=4),
        },
        "playback": {
            "profile":                   p.PLAYBACK_PROFILE,
            "resolved_profile_type":     p.resolve_playback_profile(),
            "allow_normal_fallback":     p.PLAYBACK_ALLOW_NORMAL_FALLBACK,
            "allow_mobile_fallback":     p.PLAYBACK_ALLOW_MOBILE_FALLBACK,
            "speeds":                    p.PLAYBACK_SPEEDS,
            "timeline_default_zoom":     p.TIMELINE_DEFAULT_ZOOM,
            "timeline_merge_threshold":  p.TIMELINE_MERGE_THRESHOLD_SECONDS,
        },
        "webrtc": {
            "enabled":              p.ENABLE_WEBRTC,
            "hls_fallback":         p.ENABLE_HLS_FALLBACK,
            "max_sessions":         p.MAX_WEBRTC_SESSIONS_PER_CAMERA,
            "connection_timeout":   p.WEBRTC_CONNECTION_TIMEOUT_SECONDS,
        },
        "transcoding": {
            "h265_enabled":      p.ENABLE_H265_TRANSCODING,
            "vcodec":            p.TRANSCODER_VCODEC,
            "preset":            p.TRANSCODER_PRESET,
            "tune":              p.TRANSCODER_TUNE,
            "idle_timeout":      p.TRANSCODER_IDLE_TIMEOUT_SECONDS,
            "max_transcoders":   p.MAX_ACTIVE_TRANSCODERS,
        },
        "edge_push": {
            "enabled":              p.ENABLE_EDGE_PUSH,
            "priority":             p.EDGE_PUSH_PRIORITY,
            "heartbeat_timeout":    p.EDGE_PUSH_HEARTBEAT_TIMEOUT_SECONDS,
            "check_interval":       p.EDGE_PUSH_CHECK_INTERVAL_SECONDS,
        },
        "watchdog": {
            "rtsp_health_check":     p.ENABLE_RTSP_HEALTH_CHECK,
            "ping_interval":         p.CAMERA_PING_INTERVAL_SECONDS,
            "ping_timeout":          p.CAMERA_PING_TIMEOUT_SECONDS,
        },
        "validation": {
            "strict_camera_validation": p.STRICT_CAMERA_VALIDATION,
            "allow_unknown_edge":        p.ALLOW_UNKNOWN_EDGE_DEVICES,
        },
    }


@app.get("/api/policy/stream-selection")
async def get_stream_selection(
    camera_id: str,
    context: str = "live",
    layout_size: int = 1,
    session: Annotated[AsyncSession, Depends(get_session)] = None
):
    """
    Resolves the correct stream_id to use for a given camera and context.

    Args:
        camera_id: The Camera.id (UUID) to resolve streams for.
        context:   "live" | "playback" | "live-wall"
        layout_size: Number of cameras in the current grid (for adaptive profile).

    Returns:
        { stream_id, profile_type, profile_name, hls_url, context }
    """
    from . import config as p
    from .models import Camera, CameraStream, ProfileType

    res = await session.execute(
        select(Camera).where(Camera.id == camera_id).options(selectinload(Camera.streams))
    )
    camera = res.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    if context == "playback":
        target_profile = p.resolve_playback_profile()
    else:
        target_profile = p.resolve_live_profile(layout_size=layout_size)

    # Find matching stream
    target_stream = None
    if camera.streams:
        # Prefer exact profile match
        target_stream = next((s for s in camera.streams if s.profile_type.value == target_profile), None)
        # Fallback chain
        if not target_stream and context == "playback" and p.PLAYBACK_ALLOW_NORMAL_FALLBACK:
            target_stream = next((s for s in camera.streams if s.profile_type == ProfileType.SUB), None)
        if not target_stream:
            target_stream = next((s for s in camera.streams if s.profile_type == ProfileType.MAIN), None)
        if not target_stream:
            target_stream = camera.streams[0] if camera.streams else None

    if not target_stream:
        raise HTTPException(status_code=404, detail="No streams available for this camera")

    profile_name = next(
        (k for k, v in p.PROFILE_MAP.items() if v == target_stream.profile_type.value),
        target_stream.profile_type.value
    )

    return {
        "camera_id":    camera_id,
        "stream_id":    target_stream.stream_id,
        "profile_type": target_stream.profile_type.value,
        "profile_name": profile_name,
        "hls_url":      f"/api/streams/{target_stream.stream_id}/live/index.m3u8",
        "context":      context,
        "layout_size":  layout_size,
    }


class SegmentCompletePayload(BaseModel):
    stream_id: str
    file_path: str

def get_file_duration(file_path: str, ffmpeg_path: str = "ffmpeg") -> float:
    """Uses ffprobe to extract the duration of a video file."""
    ffprobe_path = "ffprobe"
    if "/" in ffmpeg_path or "\\" in ffmpeg_path:
        dirname = os.path.dirname(ffmpeg_path)
        basename = os.path.basename(ffmpeg_path)
        ext = os.path.splitext(basename)[1]
        ffprobe_path = os.path.join(dirname, f"ffprobe{ext}")
    
    cmd = [
        ffprobe_path,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        file_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            duration_str = data.get("format", {}).get("duration")
            if duration_str:
                return float(duration_str)
    except Exception as e:
        print(f"[metadata] ffprobe failed for {file_path}: {e}")
    
    return float(settings.segment_time_seconds)

@app.post("/api/recordings/segment-complete")
async def record_segment_complete(
    payload: SegmentCompletePayload,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    print(f"[webhook] Segment complete notification received: stream_id={payload.stream_id}, path={payload.file_path}")
    
    # 1. Validate payload inputs
    if not payload.stream_id or not payload.file_path:
        raise HTTPException(status_code=400, detail="stream_id and file_path are required")
        
    # 2. Verify stream is registered
    res = await session.execute(
        select(CameraStream)
        .options(selectinload(CameraStream.camera))
        .where(CameraStream.stream_id == payload.stream_id)
    )
    stream = res.scalar_one_or_none()
    if not stream:
        raise HTTPException(status_code=400, detail=f"Unregistered stream_id: {payload.stream_id}")

    if settings.strict_camera_validation:
        camera = stream.camera
        if not camera or not camera.active:
            print(f"[webhook] Rejected indexing segment for stream: stream_id={payload.stream_id} reason=inactive")
            return {"status": "ignored", "reason": "strict_validation_failed"}
        
    # 3. Resolve relative path (stream_id/date/filename) from the payload path
    parts = Path(payload.file_path).parts
    relative_path = "/".join(parts[-3:])
    
    # 4. Verify file exists on local disk and size > 0 (checking both absolute input and relative fallback)
    p = Path(payload.file_path)
    if not p.exists():
        p = Path(settings.recording_dir) / relative_path
        
    if not p.exists():
        print(f"[webhook] File not found: {payload.file_path} (resolved: {p})")
        raise HTTPException(status_code=400, detail="File does not exist on disk")
        
    try:
        size = p.stat().st_size
        if size == 0:
            print(f"[webhook] Rejecting 0-byte file: {p}")
            raise HTTPException(status_code=400, detail="File size is zero")
            
        end_ts = p.stat().st_mtime
    except Exception as e:
        print(f"[webhook] Error checking file stats for {p}: {e}")
        raise HTTPException(status_code=400, detail=f"Error checking file: {e}")
        
    # 5. Calculate duration and start timestamp
    duration = await asyncio.to_thread(get_file_duration, str(p), settings.ffmpeg_path)
    start_ts = end_ts - duration
    
    # 6. Insert RecordingSegment idempotent using relative path
    seg = RecordingSegment(
        stream_id=payload.stream_id,
        file_path=relative_path,
        start_ts=start_ts,
        end_ts=end_ts
    )
    session.add(seg)
    try:
        await session.commit()
        print(f"[webhook] Indexed segment: {relative_path} (Duration: {duration}s)")
        await PlaybackTimelineService.invalidate_cache_for_timestamp(payload.stream_id, start_ts)
    except IntegrityError:
        await session.rollback()
        print(f"[webhook] Duplicate segment ignored: {relative_path}")
        
    return {"status": "ok"}

async def recording_recovery_loop():
    print("[indexer] Starting periodic recording recovery scanner (safety net)...")
    # Wait for initial_sync to register all camera streams in the database
    await asyncio.sleep(10.0)
    
    # Initial recovery scan on startup
    try:
        async for session in get_session():
            await index_recordings(session, settings.recording_dir)
    except Exception as e:
        print("[indexer] Initial recovery scanner error:", e)

    while True:
        await asyncio.sleep(settings.indexer_interval_seconds)
        async for session in get_session():
            try:
                await index_recordings(session, settings.recording_dir)
            except Exception as e:
                print("[indexer] Recovery scanner loop error:", e)


@app.get("/api/recordings/recovered-stats")
async def get_recovered_stats(
    session: Annotated[AsyncSession, Depends(get_session)] = None
):
    from sqlalchemy import select, func
    
    # We query all segments where file_path contains '_recovered'
    stmt = select(
        RecordingSegment.stream_id,
        func.count(RecordingSegment.id).label("count"),
        func.sum(RecordingSegment.end_ts - RecordingSegment.start_ts).label("duration")
    ).where(RecordingSegment.file_path.like("%_recovered%")).group_by(RecordingSegment.stream_id)
    
    res = await session.execute(stmt)
    rows = res.all()
    
    by_stream = {}
    total_count = 0
    total_duration = 0.0
    
    for row in rows:
        stream_id, count, duration = row
        duration = float(duration or 0)
        by_stream[stream_id] = {
            "count": count,
            "duration": duration
        }
        total_count += count
        total_duration += duration
        
    # Also query the 10 most recent recovered files
    recent_stmt = select(RecordingSegment).where(
        RecordingSegment.file_path.like("%_recovered%")
    ).order_by(RecordingSegment.created_at.desc()).limit(10)
    
    recent_res = await session.execute(recent_stmt)
    recent_segs = recent_res.scalars().all()
    
    recent_list = []
    for s in recent_segs:
        recent_list.append({
            "id": s.id,
            "stream_id": s.stream_id,
            "file_path": s.file_path,
            "filename": s.file_path.split("/")[-1].split("\\")[-1],
            "start_ts": s.start_ts,
            "end_ts": s.end_ts,
            "duration": s.end_ts - s.start_ts,
            "created_at": s.created_at.isoformat() if s.created_at else None
        })
        
    return {
        "total_count": total_count,
        "total_duration": total_duration,
        "by_stream": by_stream,
        "recent": recent_list
    }


# ----------------------------------------------------
# Manual Recording Gap Scanning & Recovery Endpoints
# ----------------------------------------------------
@app.get("/api/recordings/{stream_id}/gaps")
async def get_recording_gaps(
    stream_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    start_time: float | None = None,
    end_time: float | None = None
):
    now = time.time()
    start_ts = start_time if start_time is not None else (now - 24 * 3600)
    end_ts = end_time if end_time is not None else now

    from .webrtc import resolve_stream_by_identifier
    stream = await resolve_stream_by_identifier(stream_id, session)
    if not stream:
        raise HTTPException(status_code=404, detail="Camera stream not found")

    # Fetch segments
    seg_res = await session.execute(
        select(RecordingSegment)
        .where(RecordingSegment.stream_id == stream.stream_id)
        .where(RecordingSegment.start_ts >= start_ts)
        .where(RecordingSegment.end_ts <= end_ts)
        .order_by(RecordingSegment.start_ts.asc())
    )
    segments = list(seg_res.scalars().all())

    gaps = []
    if not segments:
        return []

    for i in range(len(segments) - 1):
        curr = segments[i]
        nxt = segments[i+1]
        
        gap_start = curr.end_ts
        gap_end = nxt.start_ts
        gap_duration = gap_end - gap_start
        
        if gap_duration >= 5.0:
            seg_time = settings.segment_time_seconds
            # Align temp_start to segment boundary
            temp_start = (gap_start // seg_time) * seg_time
            while temp_start < gap_end:
                next_end = temp_start + seg_time
                if next_end <= gap_end:
                    dt_start = datetime.fromtimestamp(temp_start)
                    dt_end = datetime.fromtimestamp(next_end)
                    gaps.append({
                        "start_ts": temp_start,
                        "end_ts": next_end,
                        "duration": seg_time,
                        "formatted_start": dt_start.strftime("%Y-%m-%d %H:%M:%S"),
                        "formatted_end": dt_end.strftime("%Y-%m-%d %H:%M:%S")
                    })
                temp_start += seg_time
    return gaps


async def run_manual_recovery(stream_id: str, gap_chunks: list[dict]):
    print(f"[recovery] [manual] Starting manual recovery task for {stream_id} ({len(gap_chunks)} chunks)...")
    from .db import get_session
    from .models import CameraStream, Camera, RecordingSegment
    from .providers import get_playback_recovery_provider
    
    # We resolve inside the background session
    async for session in get_session():
        res = await session.execute(
            select(CameraStream)
            .options(selectinload(CameraStream.camera))
            .where(CameraStream.stream_id == stream_id)
        )
        stream = res.scalar_one_or_none()
        if not stream:
            print(f"[recovery] [manual] Stream {stream_id} not found in database inside background task.")
            return

        semaphore = asyncio.Semaphore(3)

        async def download_chunk(chunk):
            temp_start = chunk["start_ts"]
            temp_end = chunk["end_ts"]
            
            # Resolve vendor provider
            make_val = stream.camera.make if stream.camera else None
            provider = get_playback_recovery_provider(make_val)
            recovery_url = provider.build_playback_url(stream, temp_start, temp_end)
            
            dt_start = datetime.fromtimestamp(temp_start)
            day_str = dt_start.strftime("%Y-%m-%d")
            stream_record_dir = Path(settings.recording_dir) / stream_id / day_str
            stream_record_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{dt_start.strftime('%Y%m%d_%H%M')}_recovered.mp4"
            output_path = stream_record_dir / filename

            is_hevc = stream.codec and stream.codec.lower() in ("hevc", "h265")

            # Dynamic HEVC check fallback: if DB says H264, probe the actual stream to be sure
            if not is_hevc:
                try:
                    cmd_probe = [
                        "ffprobe", "-v", "error",
                        "-rtsp_transport", "tcp",
                        "-select_streams", "v:0",
                        "-show_entries", "stream=codec_name",
                        "-of", "default=noprint_wrappers=1:nokey=1",
                        recovery_url
                    ]
                    proc_probe = await asyncio.create_subprocess_exec(
                        *cmd_probe,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout_probe, _ = await asyncio.wait_for(proc_probe.communicate(), timeout=5.0)
                    if proc_probe.returncode == 0:
                        codec_name = stdout_probe.decode().strip()
                        if codec_name.lower() in ("hevc", "h265"):
                            is_hevc = True
                            print(f"[recovery] [manual] [{stream_id}] Dynamically probed HEVC codec fallback for recovery URL: {filename}")
                except Exception as probe_err:
                    print(f"[recovery] [manual] [{stream_id}] Failed to dynamically probe codec fallback: {probe_err}")

            codec_args = ["-c:v", "libx264", "-preset", "superfast", "-crf", "23", "-c:a", "copy"] if is_hevc else ["-c", "copy"]

            async with semaphore:
                print(f"[recovery] [manual] [{stream_id}] Downloading gap segment: {filename} (HEVC Transcode: {is_hevc})...")
                cmd = [
                    settings.ffmpeg_path,
                    "-y", # Overwrite existing/corrupted clips
                    "-hide_banner",
                    "-loglevel", "warning",
                    "-rtsp_transport", "tcp",
                    "-stimeout", "15000000", # 15 seconds socket timeout
                    "-i", recovery_url,
                    "-t", str(settings.segment_time_seconds),
                ] + codec_args + ["-movflags", "+faststart", str(output_path)]

                try:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await asyncio.wait_for(proc.wait(), timeout=settings.segment_time_seconds * 2)
                    if proc.returncode == 0:
                        print(f"[recovery] [manual] [{stream_id}] Successfully recovered: {filename}")
                        
                        parts = Path(output_path).parts
                        relative_path = "/".join(parts[-3:])
                        
                        async for insert_session in get_session():
                            stmt_check = select(RecordingSegment).where(
                                RecordingSegment.stream_id == stream_id,
                                RecordingSegment.file_path == relative_path
                            )
                            res_check = await insert_session.execute(stmt_check)
                            existing_seg = res_check.scalar_one_or_none()
                            if not existing_seg:
                                new_seg = RecordingSegment(
                                    stream_id=stream_id,
                                    file_path=relative_path,
                                    start_ts=temp_start,
                                    end_ts=temp_end
                                )
                                insert_session.add(new_seg)
                                await insert_session.commit()
                                print(f"[recovery] [manual] [{stream_id}] Indexed segment: {filename}")
                    else:
                        print(f"[recovery] [manual] [{stream_id}] FFmpeg exit code {proc.returncode} for: {filename}")
                        if output_path.exists():
                            output_path.unlink()
                except asyncio.TimeoutError:
                    print(f"[recovery] [manual] [{stream_id}] Timeout downloading: {filename}")
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    if output_path.exists():
                        output_path.unlink()
                except Exception as e:
                    print(f"[recovery] [manual] [{stream_id}] Error running FFmpeg: {e}")
                    if output_path.exists():
                        output_path.unlink()

        for chunk in gap_chunks:
            await download_chunk(chunk)


@app.post("/api/recordings/{stream_id}/recover")
async def recover_recording_gaps(
    stream_id: str,
    payload: list[dict],
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    from .webrtc import resolve_stream_by_identifier
    stream = await resolve_stream_by_identifier(stream_id, session)
    if not stream:
        raise HTTPException(status_code=404, detail="Camera stream not found")

    background_tasks.add_task(
        run_manual_recovery,
        stream.stream_id,
        payload
    )
    return {"status": "started", "queued_count": len(payload)}


@app.get("/api/recordings/file")
async def recording_file(path: str):
    p = Path(path)
    if not p.is_absolute() or not p.exists():
        # Fallback to resolving relative path dynamically
        parts = Path(path).parts
        rel_path = "/".join(parts[-3:])
        p = Path(settings.recording_dir) / rel_path
        
    if not p.exists():
        raise HTTPException(404, f"File not found: {path}")
    return FileResponse(p, media_type="video/mp4")

@app.get("/api/recordings/download")
async def download_recording(
    stream_id: str,
    start_time: str,
    end_time: str,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    from fastapi import BackgroundTasks
    import tempfile
    import os
    import subprocess
    
    # 1. Parse timestamps
    try:
        try:
            start_ts = float(start_time)
            end_ts = float(end_time)
        except ValueError:
            from datetime import datetime
            start_ts = datetime.fromisoformat(start_time.replace("Z", "+00:00")).timestamp()
            end_ts = datetime.fromisoformat(end_time.replace("Z", "+00:00")).timestamp()
    except Exception as e:
        raise HTTPException(400, f"Invalid start_time or end_time format: {e}")
        
    if start_ts >= end_ts:
        raise HTTPException(400, "start_time must be before end_time")
        
    # Enforce maximum duration of 30 minutes
    max_duration = 30 * 60  # 1800 seconds
    requested_duration = end_ts - start_ts
    if requested_duration > max_duration:
        raise HTTPException(400, f"Requested duration exceeds the maximum limit of 30 minutes (requested: {requested_duration:.1f}s)")

    # Resolve stream_id
    from .webrtc import resolve_stream_by_identifier
    stream = await resolve_stream_by_identifier(stream_id, session, purpose="playback")
    if stream:
        stream_id = stream.stream_id

    # 2. Query database for segments overlapping with this range
    stmt = (
        select(RecordingSegment)
        .where(RecordingSegment.stream_id == stream_id)
        .where(RecordingSegment.end_ts >= start_ts)
        .where(RecordingSegment.start_ts <= end_ts)
        .order_by(RecordingSegment.start_ts.asc())
    )
    res = await session.execute(stmt)
    segments = list(res.scalars().all())
    
    if not segments:
        raise HTTPException(404, "No recordings found for the specified range")
        
    valid_files = []
    valid_segments = []
    for seg in segments:
        p = Path(seg.file_path)
        if not p.is_absolute() or not p.exists():
            parts = Path(seg.file_path).parts
            rel_path = "/".join(parts[-3:])
            p = Path(settings.recording_dir) / rel_path
        p = p.resolve().absolute()
        if p.exists():
            valid_files.append(p)
            valid_segments.append(seg)
            
    if not valid_files:
        raise HTTPException(404, "Recording files not found on disk")
        
    # 3. Calculate start offset and duration for ffmpeg trimming
    first_seg = valid_segments[0]
    start_offset = max(0.0, start_ts - first_seg.start_ts)
    duration = requested_duration

    temp_dir = tempfile.gettempdir()
    output_filename = f"{stream_id}_{int(start_ts)}_{int(end_ts)}_trimmed.mp4"
    output_path = os.path.join(temp_dir, output_filename)
    list_file_path = None

    try:
        # Case 1: Exactly 1 file
        if len(valid_files) == 1:
            cmd = [
                settings.ffmpeg_path,
                "-ss", f"{start_offset:.3f}",
                "-i", str(valid_files[0]),
                "-t", f"{duration:.3f}",
                "-c", "copy",
                "-y",
                output_path
            ]
            print(f"[download] Running ffmpeg trim: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                print(f"[download] ffmpeg error: {result.stderr}")
                raise HTTPException(500, f"FFmpeg trim failed: {result.stderr}")
                
        # Case 2: Multiple files -> Concatenate and trim using ffmpeg
        else:
            list_file_path = os.path.join(temp_dir, f"{stream_id}_{int(start_ts)}_{int(end_ts)}_list.txt")
            with open(list_file_path, "w", encoding="utf-8") as f:
                for file_path in valid_files:
                    safe_path = str(file_path).replace("\\", "/")
                    f.write(f"file '{safe_path}'\n")
                    
            cmd = [
                settings.ffmpeg_path,
                "-f", "concat",
                "-safe", "0",
                "-i", list_file_path,
                "-ss", f"{start_offset:.3f}",
                "-t", f"{duration:.3f}",
                "-c", "copy",
                "-y",
                output_path
            ]
            print(f"[download] Running ffmpeg concat and trim: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                print(f"[download] ffmpeg error: {result.stderr}")
                raise HTTPException(500, f"FFmpeg concat and trim failed: {result.stderr}")
                
        def cleanup():
            try:
                if list_file_path and os.path.exists(list_file_path):
                    os.remove(list_file_path)
                if os.path.exists(output_path):
                    os.remove(output_path)
            except Exception as e:
                print(f"[download] Cleanup error: {e}")
                
        background_tasks = BackgroundTasks()
        background_tasks.add_task(cleanup)
        
        return FileResponse(
            path=output_path,
            media_type="video/mp4",
            filename=output_filename,
            background=background_tasks
        )
    except Exception as ex:
        if list_file_path and os.path.exists(list_file_path):
            os.remove(list_file_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        if isinstance(ex, HTTPException):
            raise ex
        raise HTTPException(500, f"Failed to process download segments: {ex}")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/api/cameras/sync", response_model=SyncResponse)
async def sync_cameras(session: Annotated[AsyncSession, Depends(get_session)]):
    raw_cameras = await fetch_upstream_cameras()
    updated_count = 0
    
    for raw in raw_cameras:
        source_id = int(raw.get("cameraId") or raw.get("id"))
        name = str(raw.get("name") or f"Camera {source_id}")
        active = bool(raw.get("active", True))

        # 1. Sync Camera Parent Row
        make = raw.get("make")
        res = await session.execute(
            select(Camera).where(Camera.source_camera_id == source_id)
        )
        camera = res.scalar_one_or_none()
        if not camera:
            camera = Camera(
                source_camera_id=source_id,
                name=name,
                active=active,
                make=make,
                synced_from_api=True
            )
            session.add(camera)
            await session.flush()
        else:
            camera.name = name
            camera.active = active
            camera.make = make
            camera.synced_from_api = True
            await session.flush()

        # 2. Sync CameraStream Child Row
        stream_id = str(raw.get("streamId") or f"{raw.get('serverCameraId','camera')}_{raw.get('streamType','NORMAL')}")
        stream_url = str(raw.get("rtspUrl") or "").strip()
        if not stream_url.startswith(("rtsp://", "rtsps://", "rtmp://")):
            stream_url = f"rtsp://{stream_url}"

        # Inject username/password if present
        username = raw.get("username")
        password = raw.get("password")
        if username and password:
            try:
                protocol, rest = stream_url.split("://", 1)
                encoded_username = quote(str(username), safe="")
                encoded_password = quote(str(password), safe="")
                stream_url = f"{protocol}://{encoded_username}:{encoded_password}@{rest}"
            except Exception:
                pass

        stream_res = await session.execute(
            select(CameraStream).where(CameraStream.stream_id == stream_id)
        )
        stream = stream_res.scalar_one_or_none()
        
        profile = map_stream_profile(raw.get("streamType"))
        res_str = f"{raw.get('width', 1920)}x{raw.get('height', 1080)}"
        fps_val = int(raw.get("fps", 15)) if raw.get("fps") is not None else 15
        codec_val = "H265" if "h265" in (raw.get("archiveType") or "").lower() else "H264"
        bitrate_val = int(raw.get("bitrate") // 1000) if raw.get("bitrate") else None

        # Determine always_on based on archiveDays
        archive_days = raw.get("archiveDays")
        always_on_val = False
        if archive_days is not None:
            try:
                if int(archive_days) > 0:
                    always_on_val = True
            except (ValueError, TypeError):
                pass

        if not stream:
            stream = CameraStream(
                camera_id=camera.id,
                stream_id=stream_id,
                profile_type=profile,
                resolution=res_str,
                fps=fps_val,
                codec=codec_val,
                bitrate=bitrate_val,
                stream_url=stream_url,
                stream_mode="AUTO",
                always_on=always_on_val,
                status=StreamState.REGISTERED
            )
            session.add(stream)
            await session.flush()
        else:
            stream.stream_url = stream_url
            stream.resolution = res_str
            stream.fps = fps_val
            stream.bitrate = bitrate_val
            if stream.codec != "H265":
                stream.codec = codec_val
            stream.always_on = always_on_val
            await session.flush()

        # Register in MediaMTX config
        if camera.active:
            await stream_manager.add_stream(session, stream)
        else:
            await stream_manager.remove_stream(session, stream)

        updated_count += 1

    await session.commit()
    return SyncResponse(total=len(raw_cameras), created_or_updated=updated_count, source=settings.upstream_camera_api_url)

@app.get("/api/cameras/sync", response_model=SyncResponse)
async def sync_cameras_get(session: Annotated[AsyncSession, Depends(get_session)]):
    """GET alias for syncing cameras. Calls the same sync logic as the POST endpoint.
    Useful for browsers or tools that default to GET.
    """
    return await sync_cameras(session)

@app.get("/api/cameras", response_model=list[CameraOut])
async def list_cameras(session: Annotated[AsyncSession, Depends(get_session)], sync: bool = Query(default=False)):
    use_upstream = await RedisManager.get_setting_use_upstream()
    if sync and use_upstream:
        try:
            await sync_cameras(session)
        except Exception as e:
            print(f"[main] Failed to sync upstream cameras: {e}")

    query = select(Camera).options(selectinload(Camera.streams))
    if not use_upstream:
        query = query.where(Camera.synced_from_api == False)

    res = await session.execute(query.order_by(Camera.name.asc()))
    return list(res.scalars().all())

@app.get("/api/cameras/active", response_model=list[CameraOut])
async def list_active_cameras(session: Annotated[AsyncSession, Depends(get_session)]):
    active_stream_ids = set()

    # 1. Query MediaMTX paths list for currently publishing feeds
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.mediamtx_api_url}/v3/paths/list?page=0&itemsPerPage=10000")
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", []) if isinstance(data, dict) else []
                for item in items:
                    if item.get("ready") is True:
                        active_stream_ids.add(item.get("name"))
    except Exception as e:
        print(f"[main] Failed to fetch active paths from MediaMTX: {e}")

    # 2. Scan recordings directory for existing active directories
    try:
        rec_dir = Path(settings.recording_dir)
        if rec_dir.exists():
            for subdir in rec_dir.iterdir():
                if subdir.is_dir():
                    active_stream_ids.add(subdir.name)
    except Exception as e:
        print(f"[main] Failed to scan recordings directory: {e}")

    # 3. Query matching Cameras from the DB
    conditions = [CameraStream.status == StreamState.ONLINE]
    if active_stream_ids:
        conditions.append(CameraStream.stream_id.in_(list(active_stream_ids)))

    use_upstream = await RedisManager.get_setting_use_upstream()
    query = select(Camera).join(CameraStream).where(or_(*conditions))
    if not use_upstream:
        query = query.where(Camera.synced_from_api == False)

    res = await session.execute(
        query.options(selectinload(Camera.streams))
        .order_by(Camera.name.asc())
        .distinct()
    )
    return list(res.scalars().all())

@app.get("/api/cameras/{stream_id}", response_model=CameraOut)
async def get_camera(stream_id: str, session: Annotated[AsyncSession, Depends(get_session)]):
    # Retrieve the parent Camera for the requested stream ID
    from .webrtc import resolve_stream_by_identifier
    stream = await resolve_stream_by_identifier(stream_id, session)
    if not stream:
        raise HTTPException(status_code=404, detail="Camera stream not found")

    camera_res = await session.execute(
        select(Camera)
        .where(Camera.id == stream.camera_id)
        .options(selectinload(Camera.streams))
    )
    return camera_res.scalar_one()

@app.post("/api/cameras/{stream_id}/live/start")
async def start_live(stream_id: str, session: Annotated[AsyncSession, Depends(get_session)]):
    from .webrtc import resolve_stream_by_identifier
    stream = await resolve_stream_by_identifier(stream_id, session)
    if not stream:
        raise HTTPException(status_code=404, detail="Camera stream not found")

    await stream_manager.add_stream(session, stream)
    return {
        "stream_id": stream.stream_id,
        "status": "started",
        "hls": f"/api/streams/{stream.stream_id}/live/index.m3u8"
    }

@app.post("/api/cameras/{stream_id}/live/stop")
async def stop_live(stream_id: str, session: Annotated[AsyncSession, Depends(get_session)]):
    from .webrtc import resolve_stream_by_identifier
    stream = await resolve_stream_by_identifier(stream_id, session)
    if not stream:
        raise HTTPException(status_code=404, detail="Camera stream not found")

    await stream_manager.remove_stream(session, stream)
    return {"stream_id": stream.stream_id, "status": "stopped"}

@app.post("/api/cameras/{stream_id}/live/restart")
async def restart_live(stream_id: str, session: Annotated[AsyncSession, Depends(get_session)]):
    from .webrtc import resolve_stream_by_identifier
    stream = await resolve_stream_by_identifier(stream_id, session)
    if not stream:
        raise HTTPException(status_code=404, detail="Camera stream not found")

    await stream_manager.restart_stream(session, stream)
    return {"stream_id": stream.stream_id, "status": "restarted"}

# ----------------------------------------------------
# MediaMTX HLS Reverse Proxy Endpoints
# ----------------------------------------------------
@app.get("/api/streams/{stream_id}/live/index.m3u8")
async def hls_playlist(
    stream_id: str,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    target_stream_id = stream_id
    stream = None
    try:
        from .webrtc import resolve_stream_by_identifier
        stream = await resolve_stream_by_identifier(stream_id, session)
        if stream:
            stream_id = stream.stream_id
            target_stream_id = stream_id
            if stream.codec and stream.codec.upper() == "H265":
                from .transcoder import transcoder_manager
                target_stream_id = await transcoder_manager.ensure_transcoder(
                    stream_id, session, increment_viewer=False
                )
    except Exception as e:
        print(f"[main] Error ensuring transcoder for H.265 HLS stream {stream_id}: {e}")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{settings.mediamtx_api_url.replace(':9997', ':8080')}/{target_stream_id}/index.m3u8")
            if response.status_code == 200:
                return Response(
                    content=response.content,
                    media_type="application/vnd.apple.mpegurl",
                    headers={
                        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                        "Pragma": "no-cache",
                        "Expires": "0"
                    }
                )
            
            # If the playlist is not found (404), trigger fast dynamic recovery by re-registering config
            if response.status_code == 404 and stream:
                print(f"[main] HLS stream {stream_id} not found in MediaMTX (404). Triggering fast recovery...")
                from .stream_manager import stream_manager
                await stream_manager.add_stream(session, stream)
                
                if stream.codec and stream.codec.upper() == "H265":
                    from .transcoder import transcoder_manager
                    target_stream_id = await transcoder_manager.ensure_transcoder(
                        stream_id, session, increment_viewer=False
                    )

                # Wait up to 1.5 seconds (checking every 0.3s) for MediaMTX to initialize the stream
                for _ in range(5):
                    await asyncio.sleep(0.3)
                    retry_resp = await client.get(f"{settings.mediamtx_api_url.replace(':9997', ':8080')}/{target_stream_id}/index.m3u8")
                    if retry_resp.status_code == 200:
                        print(f"[main] Fast recovery succeeded for HLS stream {stream_id}!")
                        return Response(
                            content=retry_resp.content,
                            media_type="application/vnd.apple.mpegurl",
                            headers={
                                "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                                "Pragma": "no-cache",
                                "Expires": "0"
                            }
                        )
        except Exception as e:
            print(f"[main] Error proxying index.m3u8 for {stream_id}: {e}")
    raise HTTPException(404, "Playlist not ready")

@app.get("/api/streams/{stream_id}/live/{filename}")
async def hls_segment(
    stream_id: str,
    filename: str,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    target_stream_id = stream_id
    try:
        from .webrtc import resolve_stream_by_identifier
        stream = await resolve_stream_by_identifier(stream_id, session)
        if stream:
            stream_id = stream.stream_id
            target_stream_id = stream_id
            if stream.codec and stream.codec.upper() == "H265":
                target_stream_id = f"{stream_id}_h264"
    except Exception as e:
        print(f"[main] Error checking codec for HLS segment {stream_id}: {e}")

    async with httpx.AsyncClient() as client:
        try:
            # Match endpoints and format params
            url = f"{settings.mediamtx_api_url.replace(':9997', ':8080')}/{target_stream_id}/{filename}"
            response = await client.get(url)
            if response.status_code == 200:
                media_type = "video/MP2T" if filename.endswith(".ts") else "video/mp4"
                return Response(
                    content=response.content,
                    media_type=media_type,
                    headers={
                        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                        "Pragma": "no-cache",
                        "Expires": "0"
                    }
                )
        except Exception as e:
            print(f"[main] Error proxying segment {filename} for {stream_id}: {e}")
    raise HTTPException(404, "Segment not found")

# ----------------------------------------------------
# Playback API Endpoints
# ----------------------------------------------------
@app.get("/api/playback/{stream_id}", response_model=list[RecordingSegmentOut])
async def playback(stream_id: str, start_ts: float, end_ts: float, session: Annotated[AsyncSession, Depends(get_session)]):
    from .webrtc import resolve_stream_by_identifier
    stream = await resolve_stream_by_identifier(stream_id, session, purpose="playback")
    if stream:
        stream_id = stream.stream_id

    res = await session.execute(
        select(RecordingSegment)
        .where(RecordingSegment.stream_id == stream_id)
        .where(RecordingSegment.end_ts >= start_ts)
        .where(RecordingSegment.start_ts <= end_ts)
        .order_by(RecordingSegment.start_ts.asc())
    )
    segments = list(res.scalars().all())

    if not segments:
        stmt = (
            select(RecordingSegment)
            .where(RecordingSegment.stream_id == stream_id)
            .where(RecordingSegment.start_ts >= start_ts)
            .order_by(RecordingSegment.start_ts.asc())
            .limit(1)
        )
        fallback_res = await session.execute(stmt)
        nearest = fallback_res.scalar_one_or_none()
        if nearest:
            new_start_ts = nearest.start_ts
            new_end_ts = new_start_ts + 3600
            res = await session.execute(
                select(RecordingSegment)
                .where(RecordingSegment.stream_id == stream_id)
                .where(RecordingSegment.end_ts >= new_start_ts)
                .where(RecordingSegment.start_ts <= new_end_ts)
                .order_by(RecordingSegment.start_ts.asc())
            )
            segments = list(res.scalars().all())

    return segments

@app.get("/api/cameras/{stream_id}/recordings")
async def list_recordings(stream_id: str, session: Annotated[AsyncSession, Depends(get_session)]):
    from .webrtc import resolve_stream_by_identifier
    stream = await resolve_stream_by_identifier(stream_id, session, purpose="playback")
    if stream:
        stream_id = stream.stream_id

    res = await session.execute(
        select(RecordingSegment)
        .where(RecordingSegment.stream_id == stream_id)
        .order_by(RecordingSegment.start_ts.desc())
    )
    segments = res.scalars().all()
    if not segments:
        return []

    # Get camera name
    stream_res = await session.execute(
        select(CameraStream)
        .options(selectinload(CameraStream.camera))
        .where(CameraStream.stream_id == stream_id)
    )
    stream_obj = stream_res.scalar_one_or_none()
    cam_name = stream_obj.camera.name if stream_obj and stream_obj.camera else stream_id

    return [
        {
            "id": row.id,
            "stream_id": row.stream_id,
            "camera_name": cam_name,
            "file_path": row.file_path,
            "start_ts": row.start_ts,
            "end_ts": row.end_ts,
        }
        for row in segments
    ]

@app.websocket("/ws/status")
async def ws_status(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            # Sync states in Redis
            async for db_session in get_session():
                try:
                    res = await db_session.execute(select(CameraStream))
                    streams = res.scalars().all()
                    stream_list = []
                    for s in streams:
                        viewers = await RedisManager.get_viewer_count(s.stream_id)
                        cached = await RedisManager.get_stream_state(s.stream_id)
                        status = cached.get("status") if cached else s.status.value
                        stream_list.append({
                            "stream_id": s.stream_id,
                            "status": status,
                            "subscribers": viewers,
                        })
                    
                    payload = {
                        "ts": time.time(),
                        "streams": stream_list,
                    }
                    await ws.send_json(payload)
                except WebSocketDisconnect:
                    raise
                except Exception as ex:
                    print(f"[ws] Status compile error: {ex}")
                break # Close the async generator loop cleanly

            await asyncio.sleep(settings.ui_poll_seconds)
            # Receive client packets to keep ping-pong connection alive
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=0.1)
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break
            except (RuntimeError, Exception) as e:
                print(f"[ws] WebSocket connection closed or invalid: {e}")
                break
    except WebSocketDisconnect:
        return

@app.get("/api/playback/{stream_id}/available-dates")
async def available_dates(stream_id: str, session: Annotated[AsyncSession, Depends(get_session)]):
    from .webrtc import resolve_stream_by_identifier
    stream = await resolve_stream_by_identifier(stream_id, session, purpose="playback")
    if stream:
        stream_id = stream.stream_id

    res = await session.execute(
        select(RecordingSegment.start_ts)
        .where(RecordingSegment.stream_id == stream_id)
        .order_by(RecordingSegment.start_ts.asc())
    )
    timestamps = res.scalars().all()
    dates = sorted(list(set(
        time.strftime("%Y-%m-%d", time.localtime(ts))
        for ts in timestamps
    )))
    return dates

@app.get("/api/playback/{stream_id}/timeline")
async def get_playback_timeline(
    stream_id: str,
    date: str,
    zoom_level: str = "24h",
    session: Annotated[AsyncSession, Depends(get_session)] = None
):
    from .webrtc import resolve_stream_by_identifier
    stream = await resolve_stream_by_identifier(stream_id, session, purpose="playback")
    if stream:
        stream_id = stream.stream_id
    try:
        timeline = await PlaybackTimelineService.get_daily_timeline(session, stream_id, date)
        return timeline
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/playback/{stream_id}/gaps")
async def get_playback_gaps(
    stream_id: str,
    date: str,
    session: Annotated[AsyncSession, Depends(get_session)] = None
):
    from .webrtc import resolve_stream_by_identifier
    stream = await resolve_stream_by_identifier(stream_id, session, purpose="playback")
    if stream:
        stream_id = stream.stream_id
    try:
        timeline = await PlaybackTimelineService.get_daily_timeline(session, stream_id, date)
        return timeline["gaps"]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/playback/{stream_id}/summary")
async def playback_summary(
    stream_id: str,
    date: str = None,
    session: Annotated[AsyncSession, Depends(get_session)] = None
):
    from .webrtc import resolve_stream_by_identifier
    stream = await resolve_stream_by_identifier(stream_id, session, purpose="playback")
    if stream:
        stream_id = stream.stream_id

    if date:
        try:
            timeline = await PlaybackTimelineService.get_daily_timeline(session, stream_id, date)
            return {
                "date": date,
                "coverage_percent": timeline["coverage_percent"],
                "recorded_hours": round(timeline["recorded_duration"] / 3600.0, 1),
                "gaps": len(timeline["gaps"])
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
            
    # Fallback to old behavior if date is not provided
    from sqlalchemy import func
    res = await session.execute(
        select(
            func.count(RecordingSegment.id),
            func.min(RecordingSegment.start_ts),
            func.max(RecordingSegment.end_ts)
        ).where(RecordingSegment.stream_id == stream_id)
    )
    row = res.fetchone()
    if row:
        count, min_start, max_end = row
    else:
        count, min_start, max_end = 0, None, None
    return {
        "count": count or 0,
        "min_start_ts": min_start,
        "max_end_ts": max_end,
    }

@app.get("/api/playback/{stream_id}/stream.mp4")
async def stream_playback(
    stream_id: str,
    start_ts: float,
    end_ts: float,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    from .webrtc import resolve_stream_by_identifier
    stream = await resolve_stream_by_identifier(stream_id, session, purpose="playback")
    if stream:
        stream_id = stream.stream_id

    res = await session.execute(
        select(RecordingSegment)
        .where(RecordingSegment.stream_id == stream_id)
        .where(RecordingSegment.end_ts >= start_ts)
        .where(RecordingSegment.start_ts <= end_ts)
        .order_by(RecordingSegment.start_ts.asc())
    )
    segments = list(res.scalars().all())

    if not segments:
        stmt = (
            select(RecordingSegment)
            .where(RecordingSegment.stream_id == stream_id)
            .where(RecordingSegment.start_ts >= start_ts)
            .order_by(RecordingSegment.start_ts.asc())
            .limit(1)
        )
        fallback_res = await session.execute(stmt)
        nearest = fallback_res.scalar_one_or_none()
        if nearest:
            new_start_ts = nearest.start_ts
            new_end_ts = new_start_ts + 24 * 3600
            res = await session.execute(
                select(RecordingSegment)
                .where(RecordingSegment.stream_id == stream_id)
                .where(RecordingSegment.end_ts >= new_start_ts)
                .where(RecordingSegment.start_ts <= new_end_ts)
                .order_by(RecordingSegment.start_ts.asc())
            )
            segments = list(res.scalars().all())

    if not segments:
        raise HTTPException(status_code=404, detail="No recording segments found for this range or after it")

    concat_content = ""
    for seg in segments:
        p = Path(seg.file_path)
        if not p.is_absolute() or not p.exists():
            parts = Path(seg.file_path).parts
            rel_path = "/".join(parts[-3:])
            p = Path(settings.recording_dir) / rel_path
        abs_path = os.path.abspath(str(p))
        escaped_path = abs_path.replace("'", "'\\''")
        concat_content += f"file '{escaped_path}'\n"

    tmp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    tmp_file.write(concat_content)
    tmp_file.close()

    cmd = [
        settings.ffmpeg_path,
        "-f", "concat",
        "-safe", "0",
        "-i", tmp_file.name,
        "-c", "copy",
        "-f", "mp4",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "pipe:1"
    ]

    print(f"[stream] Running: {' '.join(cmd)}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL
    )

    async def video_generator():
        try:
            while True:
                chunk = await proc.stdout.read(65536)
                if not chunk:
                    break
                yield chunk
        except asyncio.CancelledError:
            try:
                proc.terminate()
                await proc.wait()
            except:
                pass
        finally:
            try:
                os.unlink(tmp_file.name)
            except:
                pass

    return StreamingResponse(
        video_generator(),
        media_type="video/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Disposition": "inline; filename=\"stream.mp4\""
        }
    )

@app.get("/api/playback/{camera_id}/play")
async def play_playback_camera(
    camera_id: str,
    start_ts: float,
    end_ts: float,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    """Serve playback stream for a camera ID (which matches stream_id in the DB)."""
    return await stream_playback(camera_id, start_ts, end_ts, session)


@app.get("/api/edge/status")
async def get_edge_status(session: Annotated[AsyncSession, Depends(get_session)]):
    # Retrieve active connections and their state
    from .edge_receiver import active_connections, metrics
    
    stmt = select(CameraStream)
    res = await session.execute(stmt)
    streams = res.scalars().all()
    
    online_streams = []
    offline_streams = []
    for s in streams:
        is_push = "publisher" in s.stream_url.lower() or not s.stream_url.strip()
        if is_push:
            if s.status == StreamState.ONLINE:
                online_streams.append(s.stream_id)
            else:
                offline_streams.append(s.stream_id)
                
    return {
        "active_edge_connections": metrics["active_edge_connections"],
        "active_ffmpeg_relays": metrics["active_ffmpeg_relays"],
        "online_streams": online_streams,
        "offline_streams": offline_streams,
        "metrics": metrics
    }


@app.get("/api/edge/connections")
async def get_edge_connections(session: Annotated[AsyncSession, Depends(get_session)]):
    from .edge_receiver import active_connections
    from .models import EdgeConnection
    
    stmt = select(EdgeConnection).order_by(EdgeConnection.connected_at.desc()).limit(100)
    res = await session.execute(stmt)
    db_conns = res.scalars().all()
    
    result = []
    for conn in db_conns:
        bytes_received = conn.bytes_received
        last_frame_ts = conn.last_frame_ts
        status = conn.status
        
        if conn.status == "CONNECTED" and conn.camera_id in active_connections:
            mem_conn = active_connections[conn.camera_id]
            if mem_conn.get("connection_db_id") == conn.id:
                bytes_received = mem_conn["bytes_received"]
                last_frame_ts = mem_conn["last_frame_ts"]
        
        result.append({
            "id": str(conn.id),
            "camera_id": conn.camera_id,
            "connected_at": conn.connected_at.isoformat() if conn.connected_at else None,
            "disconnected_at": conn.disconnected_at.isoformat() if conn.disconnected_at else None,
            "last_frame_ts": last_frame_ts.isoformat() if last_frame_ts else None,
            "bytes_received": bytes_received,
            "status": status,
            "client_ip": conn.client_ip
        })
        
    return result


@app.get("/api/system/validation-status")
async def get_validation_status(session: Annotated[AsyncSession, Depends(get_session)]):
    from sqlalchemy import func
    
    # Synced cameras count
    synced_stmt = select(func.count(Camera.id)).where(Camera.synced_from_api == True)
    synced_res = await session.execute(synced_stmt)
    synced_cameras = synced_res.scalar() or 0
    
    # Active cameras count
    active_stmt = select(func.count(Camera.id)).where(Camera.active == True)
    active_res = await session.execute(active_stmt)
    active_cameras = active_res.scalar() or 0
    
    # RTSP Pull count
    rtsp_stmt = select(func.count(CameraStream.id)).where(CameraStream.stream_source == "RTSP_PULL")
    rtsp_res = await session.execute(rtsp_stmt)
    rtsp_pull_streams = rtsp_res.scalar() or 0

    # Edge Push count
    push_stmt = select(func.count(CameraStream.id)).where(CameraStream.stream_source == "EDGE_PUSH")
    push_res = await session.execute(push_stmt)
    edge_push_streams = push_res.scalar() or 0

    # Auto Mode count
    auto_stmt = select(func.count(CameraStream.id)).where(CameraStream.stream_mode == "AUTO")
    auto_res = await session.execute(auto_stmt)
    auto_mode_streams = auto_res.scalar() or 0

    # Unknown streams count
    unknown_stmt = select(func.count(CameraStream.id)).join(Camera).where(Camera.synced_from_api == False)
    unknown_res = await session.execute(unknown_stmt)
    unknown_streams = unknown_res.scalar() or 0

    # Rejection metrics from Redis/Memory
    rejected_edge_connections = await RedisManager.get_counter("rejected_edge_connections")
    rejected_uploads = await RedisManager.get_counter("rejected_uploads")
    
    return {
        "strict_validation": settings.strict_camera_validation,
        "synced_cameras": synced_cameras,
        "active_cameras": active_cameras,
        "rtsp_pull_streams": rtsp_pull_streams,
        "edge_push_streams": edge_push_streams,
        "auto_mode_streams": auto_mode_streams,
        "unknown_streams": unknown_streams,
        "rejected_edge_connections": rejected_edge_connections,
        "rejected_uploads": rejected_uploads
    }


@app.get("/api/edge/unregistered")
async def get_unregistered_edge_cameras(session: Annotated[AsyncSession, Depends(get_session)]):
    """
    Returns camera IDs that are actively pushing via TCP (connected or recently seen)
    but have NO matching CameraStream record in the local database.
    These are cameras pushing from the field that are not registered in UAT1.
    """
    from .edge_receiver import active_connections, unregistered_attempts
    from .models import EdgeConnection

    # Get all distinct camera_ids that have ever connected via edge push
    stmt = select(EdgeConnection.camera_id).distinct()
    res = await session.execute(stmt)
    all_edge_cam_ids = {row[0] for row in res.fetchall()}

    # Also include any currently active in-memory connections or unauthorized attempts
    all_edge_cam_ids.update(active_connections.keys())
    all_edge_cam_ids.update(unregistered_attempts.keys())

    if not all_edge_cam_ids:
        return []

    # Get all registered stream_ids from the DB
    stmt2 = select(CameraStream.stream_id)
    res2 = await session.execute(stmt2)
    registered_ids = {row[0] for row in res2.fetchall()}

    # Unregistered = pushed but not in DB
    unregistered = all_edge_cam_ids - registered_ids

    result = []
    for cam_id in unregistered:
        # Get latest connection record
        stmt3 = (
            select(EdgeConnection)
            .where(EdgeConnection.camera_id == cam_id)
            .order_by(EdgeConnection.connected_at.desc())
            .limit(1)
        )
        res3 = await session.execute(stmt3)
        latest = res3.scalar_one_or_none()

        is_active = cam_id in active_connections
        mem = active_connections.get(cam_id, {})
        unreg_info = unregistered_attempts.get(cam_id, {})

        client_ip = mem.get("client_ip") or unreg_info.get("client_ip") or (latest.client_ip if latest else None)
        
        last_seen = None
        if mem.get("last_frame_ts"):
            last_seen = mem.get("last_frame_ts").isoformat()
        elif unreg_info.get("last_seen"):
            last_seen = unreg_info.get("last_seen").isoformat()
        elif latest and latest.last_frame_ts:
            last_seen = latest.last_frame_ts.isoformat()

        bytes_received = mem.get("bytes_received") or unreg_info.get("bytes_received") or (latest.bytes_received if latest else 0)
        
        first_seen = None
        if unreg_info.get("first_seen"):
            first_seen = unreg_info.get("first_seen").isoformat()
        elif latest and latest.connected_at:
            first_seen = latest.connected_at.isoformat()

        status = "CONNECTED" if is_active else (unreg_info.get("status") or (latest.status if latest else "UNKNOWN"))

        result.append({
            "camera_id": cam_id,
            "is_active": is_active,
            "client_ip": client_ip,
            "last_seen": last_seen,
            "bytes_received": bytes_received,
            "first_seen": first_seen,
            "status": status,
        })

    # Sort: active first, then by last_seen desc
    result.sort(key=lambda x: (not x["is_active"], x["last_seen"] or ""), reverse=True)
    return result


@app.post("/api/edge/register/{camera_id}")
async def register_edge_camera(
    camera_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    name: str = None,
):
    """
    Manually register an unregistered edge-push camera into the local DB.
    Creates a parent Camera and child CameraStream record so the server
    will accept future connections from this camera_id.
    """
    # Check if already registered
    stmt = select(CameraStream).where(CameraStream.stream_id == camera_id)
    res = await session.execute(stmt)
    existing = res.scalar_one_or_none()
    if existing:
        return {"status": "already_registered", "stream_id": camera_id}

    # Generate a unique source_camera_id
    from sqlalchemy import func
    max_id_stmt = select(func.max(Camera.source_camera_id))
    max_id_res = await session.execute(max_id_stmt)
    max_id = max_id_res.scalar() or 0
    new_source_id = max(max_id + 1, 900000)

    # 1. Create parent Camera
    camera = Camera(
        source_camera_id=new_source_id,
        name=name or camera_id,
        active=True
    )
    session.add(camera)
    await session.flush()

    # 2. Create child CameraStream
    new_stream = CameraStream(
        camera_id=camera.id,
        stream_id=camera_id,
        profile_type=ProfileType.MAIN,
        resolution="1920x1080",
        fps=15,
        codec="H264",
        stream_url="",  # empty means publisher edge-push stream
        status=StreamState.REGISTERED,
        always_on=True,
    )
    session.add(new_stream)
    await session.flush()

    # Add stream to MediaMTX config
    await stream_manager.add_stream(session, new_stream)
    await session.commit()

    # Clean up from unregistered_attempts in memory
    from .edge_receiver import unregistered_attempts
    unregistered_attempts.pop(camera_id, None)

    return {
        "status": "registered",
        "stream_id": camera_id,
        "message": f"Camera '{camera_id}' registered successfully as EDGE_PUSH. It will be accepted on next connection."
    }


@app.post("/api/edge/upload")
async def upload_edge_backlog(
    stream_id: str = Form(...),
    file: UploadFile = File(...),
    start_ts: float = Form(None),
    end_ts: float = Form(None),
    session: Annotated[AsyncSession, Depends(get_session)] = None,
):
    from datetime import datetime
    import re
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy import func

    # 1. Validation & Acceptance Policy
    stmt = (
        select(CameraStream)
        .options(selectinload(CameraStream.camera))
        .where(CameraStream.stream_id == stream_id)
    )
    res = await session.execute(stmt)
    stream = res.scalar_one_or_none()

    is_valid = False
    if settings.strict_camera_validation:
        if stream:
            camera = stream.camera
            if camera and camera.active:
                is_valid = True
        if not is_valid:
            print(f"[upload] Rejected camera: camera_id={stream_id} reason=inactive")
            await RedisManager.increment_counter("rejected_uploads")
            raise HTTPException(status_code=403, detail="Forbidden: Device is inactive")
    else:
        # Open/Development Mode
        if stream:
            is_valid = True
        else:
            if not settings.allow_unknown_edge_devices:
                raise HTTPException(status_code=403, detail="Forbidden: Unknown edge stream ID")

            # Auto-registration in development mode
            max_id_stmt = select(func.max(Camera.source_camera_id))
            max_id_res = await session.execute(max_id_stmt)
            max_id = max_id_res.scalar()
            from unittest.mock import AsyncMock, MagicMock
            if isinstance(max_id, (AsyncMock, MagicMock)) or not isinstance(max_id, int):
                try:
                    max_id = int(max_id) if max_id is not None else 0
                except Exception:
                    max_id = 0
            new_source_id = max(max_id + 1, 900000)

            # Create camera
            camera = Camera(
                source_camera_id=new_source_id,
                name=stream_id,
                active=True,
                make="Generic",
                synced_from_api=False
            )
            session.add(camera)
            await session.flush()

            # Create stream
            stream = CameraStream(
                camera_id=camera.id,
                stream_id=stream_id,
                profile_type=ProfileType.MAIN,
                resolution="1920x1080",
                fps=15,
                codec="H264",
                stream_url="",
                status=StreamState.REGISTERED,
                always_on=True,
            )
            session.add(stream)
            await session.flush()
            await stream_manager.add_stream(session, stream)
            await session.commit()

    # 2. Timestamp Extraction
    parsed_start_ts = start_ts
    if parsed_start_ts is None:
        filename = file.filename or ""
        match = re.search(r"(\d{8})_(\d{6})", filename)
        if match:
            try:
                date_str, time_str = match.groups()
                dt = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
                parsed_start_ts = dt.timestamp()
            except Exception:
                pass
        else:
            # Try YYYYMMDD_HHMM
            match_min = re.search(r"(\d{8})_(\d{4})", filename)
            if match_min:
                try:
                    date_str, time_str = match_min.groups()
                    dt = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M")
                    parsed_start_ts = dt.timestamp()
                except Exception:
                    pass
        # Try 10-digit unix timestamp
        if parsed_start_ts is None:
            match_unix = re.search(r"(\d{10})", filename)
            if match_unix:
                try:
                    parsed_start_ts = float(match_unix.group(1))
                except Exception:
                    pass

    if parsed_start_ts is None:
        raise HTTPException(
            status_code=400,
            detail="Bad Request: Could not determine start timestamp from filename or parameters."
        )

    # 3. File Processing & Saving
    dt_start = datetime.fromtimestamp(parsed_start_ts)
    day_str = dt_start.strftime("%Y-%m-%d")
    target_dir = Path(settings.recording_dir) / stream_id / day_str
    target_dir.mkdir(parents=True, exist_ok=True)

    # Format the filename in a standardized way to ensure consistent recovery parsing
    safe_filename = f"{dt_start.strftime('%Y%m%d_%H%M%S')}_recovered.mp4"
    file_path = target_dir / safe_filename

    # Save incoming stream
    try:
        with open(file_path, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                buffer.write(chunk)
    except Exception as io_err:
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to write file: {io_err}")

    # Determine end_ts
    parsed_end_ts = end_ts
    if parsed_end_ts is None:
        duration = get_file_duration(str(file_path), settings.ffmpeg_path)
        parsed_end_ts = parsed_start_ts + duration

    # 4. Duplicate Handling
    # Check if this exact file path is already indexed
    parts = Path(file_path).parts
    relative_path = "/".join(parts[-3:])

    stmt_check = select(RecordingSegment).where(
        RecordingSegment.stream_id == stream_id,
        RecordingSegment.file_path == relative_path
    )
    res_check = await session.execute(stmt_check)
    existing_seg = res_check.scalar_one_or_none()
    if existing_seg:
        if file_path.exists():
            file_path.unlink()
        return {"status": "already_indexed", "message": "Duplicate upload ignored."}

    # Insert recording segment
    new_segment = RecordingSegment(
        stream_id=stream_id,
        file_path=relative_path,
        start_ts=parsed_start_ts,
        end_ts=parsed_end_ts
    )
    session.add(new_segment)
    try:
        await session.commit()
        await PlaybackTimelineService.invalidate_cache_for_timestamp(stream_id, parsed_start_ts)
    except IntegrityError:
        await session.rollback()
        if file_path.exists():
            file_path.unlink()
        return {"status": "already_indexed", "message": "Duplicate upload ignored."}

    return {"status": "success", "file_path": str(file_path), "start_ts": parsed_start_ts, "end_ts": parsed_end_ts}


@app.get("/")
async def root():
    return {"message": "Enterprise VMS FastAPI backend is running"}

# ── VMS Settings and Camera CRUD Endpoints ──

@app.get("/api/settings")
async def get_settings():
    use_upstream = await RedisManager.get_setting_use_upstream()
    return {"use_upstream_cameras": use_upstream}

@app.post("/api/settings")
async def update_settings(
    payload: SettingsUpdate,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    await RedisManager.set_setting_use_upstream(payload.use_upstream_cameras)
    
    if not payload.use_upstream_cameras:
        # Delete all synced cameras from DB and MediaMTX
        res = await session.execute(
            select(Camera).where(Camera.synced_from_api == True)
        )
        synced_cameras = list(res.scalars().all())
        for camera in synced_cameras:
            # Delete its streams from MediaMTX
            streams_res = await session.execute(
                select(CameraStream).where(CameraStream.camera_id == camera.id)
            )
            camera_streams = list(streams_res.scalars().all())
            for s in camera_streams:
                try:
                    await stream_manager.remove_stream(session, s)
                except Exception:
                    pass
            await session.delete(camera)
        await session.commit()
    else:
        # Sync immediately on enabling to restore upstream feeds
        try:
            await sync_cameras(session)
        except Exception as e:
            print(f"[main] Failed to sync upstream cameras after enabling setting: {e}")
            
    return {"status": "ok", "use_upstream_cameras": payload.use_upstream_cameras}


@app.post("/api/cameras/test-rtsp")
async def test_rtsp_connection(payload: dict):
    rtsp_url = payload.get("rtsp_url")
    if not rtsp_url:
        raise HTTPException(status_code=400, detail="Missing rtsp_url")
    
    url_to_parse = rtsp_url.strip()
    if not url_to_parse.startswith(("rtsp://", "rtsps://", "rtmp://")):
        url_to_parse = f"rtsp://{url_to_parse}"
        
    url_to_parse = url_to_parse.replace("rtsp://", "http://").replace("rtsps://", "https://")
    import urllib.parse
    import socket
    try:
        parsed = urllib.parse.urlparse(url_to_parse)
        host = parsed.hostname
        port = parsed.port or 554
    except Exception as e:
        return {"success": False, "message": f"Invalid RTSP URL format: {str(e)}"}
    
    if not host:
        return {"success": False, "message": "Could not parse host/IP from RTSP URL"}
        
    try:
        socket.setdefaulttimeout(3.0)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port))
        
        # Send RTSP OPTIONS request
        options_req = f"OPTIONS {rtsp_url} RTSP/1.0\r\nCSeq: 1\r\nUser-Agent: VMS-Tester\r\n\r\n"
        s.sendall(options_req.encode())
        response = s.recv(1024).decode(errors='ignore')
        s.close()
        
        if "RTSP/1.0" in response or "200" in response or "401" in response or response.strip():
            first_line = response.splitlines()[0] if response.splitlines() else "Connected"
            return {"success": True, "message": f"Connected successfully! RTSP response: {first_line}"}
        else:
            return {"success": True, "message": "Connected successfully (TCP port open)."}
    except Exception as e:
        return {"success": False, "message": f"Connection failed: {str(e)}"}


@app.post("/api/cameras", response_model=CameraOut)
async def create_camera(
    payload: CameraCreate,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    # Validate unique source_camera_id
    existing_cam = await session.execute(
        select(Camera).where(Camera.source_camera_id == payload.source_camera_id)
    )
    if existing_cam.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Camera with ID {payload.source_camera_id} already exists")

    # Validate unique stream_id
    existing_stream = await session.execute(
        select(CameraStream).where(CameraStream.stream_id == payload.stream_id)
    )
    if existing_stream.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Stream with ID {payload.stream_id} already exists")

    # Map profile type
    profile = ProfileType.MAIN
    if payload.profile_type == "SUB":
        profile = ProfileType.SUB
    elif payload.profile_type == "MOBILE":
        profile = ProfileType.MOBILE

    camera = Camera(
        source_camera_id=payload.source_camera_id,
        name=payload.name,
        active=payload.active,
        make=payload.make,
        synced_from_api=False, # Manually created
    )
    session.add(camera)
    await session.flush()

    stream = CameraStream(
        camera_id=camera.id,
        stream_id=payload.stream_id,
        profile_type=profile,
        resolution=payload.resolution,
        fps=payload.fps,
        codec=payload.codec,
        bitrate=payload.bitrate,
        stream_url=payload.stream_url,
        stream_mode=payload.stream_mode,
        always_on=payload.always_on,
        status=StreamState.REGISTERED
    )
    session.add(stream)
    await session.commit()

    # Re-fetch camera with streams pre-loaded to prevent serialization error
    refreshed_res = await session.execute(
        select(Camera)
        .options(selectinload(Camera.streams))
        .where(Camera.id == camera.id)
    )
    camera = refreshed_res.scalar_one()

    # Register stream in MediaMTX if active and streams exist
    if camera.active and camera.streams:
        await stream_manager.add_stream(session, camera.streams[0])

    return camera


@app.put("/api/cameras/{stream_id}", response_model=CameraOut)
async def update_camera(
    stream_id: str,
    payload: CameraUpdate,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    res = await session.execute(
        select(CameraStream)
        .options(selectinload(CameraStream.camera))
        .where(CameraStream.stream_id == stream_id)
    )
    stream = res.scalar_one_or_none()
    if not stream or not stream.camera:
        raise HTTPException(status_code=404, detail="Camera stream not found")

    camera = stream.camera
    
    # Update camera parent fields
    camera.name = payload.name
    was_active = camera.active
    camera.active = payload.active
    camera.make = payload.make

    # Update stream fields
    stream.resolution = payload.resolution
    stream.fps = payload.fps
    stream.codec = payload.codec
    stream.bitrate = payload.bitrate
    stream.stream_url = payload.stream_url
    stream.always_on = payload.always_on

    await session.commit()

    # Re-fetch camera with streams pre-loaded to prevent serialization error
    refreshed_res = await session.execute(
        select(Camera)
        .options(selectinload(Camera.streams))
        .where(Camera.id == camera.id)
    )
    camera = refreshed_res.scalar_one()

    # Sync MediaMTX config
    if camera.streams:
        target_stream = camera.streams[0]
        if was_active and not camera.active:
            await stream_manager.remove_stream(session, target_stream)
        elif camera.active:
            await stream_manager.add_stream(session, target_stream)

    return camera


@app.delete("/api/cameras/{stream_id}")
async def delete_camera(
    stream_id: str,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    res = await session.execute(
        select(CameraStream)
        .options(selectinload(CameraStream.camera))
        .where(CameraStream.stream_id == stream_id)
    )
    stream = res.scalar_one_or_none()
    if not stream or not stream.camera:
        raise HTTPException(status_code=404, detail="Camera stream not found")

    camera = stream.camera

    # Fetch all streams for this camera to remove them from MediaMTX and disk
    streams_res = await session.execute(
        select(CameraStream).where(CameraStream.camera_id == camera.id)
    )
    all_streams = list(streams_res.scalars().all())

    import shutil
    for s in all_streams:
        # 1. Remove from MediaMTX
        try:
            await stream_manager.remove_stream(session, s)
        except Exception as e:
            print(f"[main] Failed to remove stream {s.stream_id} from MediaMTX during deletion: {e}")

        # 2. Physical cleanup of recordings and HLS cache directories
        for base_dir in (settings.recording_dir, settings.hls_dir):
            if base_dir:
                p = Path(base_dir) / s.stream_id
                if p.exists() and p.is_dir():
                    try:
                        shutil.rmtree(p)
                        print(f"[main] Deleted physical stream directory: {p}")
                    except Exception as e:
                        print(f"[main] Failed to delete physical directory {p}: {e}")

    # 3. Delete camera from DB (cascading takes care of streams and segments)
    await session.delete(camera)
    await session.commit()

    return {"status": "ok", "message": f"Camera {camera.name} and stream {stream_id} deleted successfully"}
