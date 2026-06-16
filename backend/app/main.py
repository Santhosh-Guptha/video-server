import json
import time
from pathlib import Path
from typing import Annotated
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, Form, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import select, delete, text
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
from .models import Camera, CameraStream, RecordingSegment, StreamState, ProfileType, EdgeConnection
from .schemas import CameraOut, CameraStreamOut, RecordingSegmentOut, SyncResponse
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
    while True:
        await asyncio.sleep(3600) # 1 hour
        try:
            print("[upstream_sync] Running periodic camera synchronization...")
            async for session in get_session():
                await sync_cameras(session)
            print("[upstream_sync] Periodic camera sync complete.")
        except Exception as e:
            print("[upstream_sync] Periodic camera sync error:", e)

@app.on_event("startup")
async def startup():
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
    asyncio.create_task(upstream_sync_loop())
    asyncio.create_task(camera_scheduler_loop())
    asyncio.create_task(camera_gap_recovery_loop())
    asyncio.create_task(camera_archive_cleanup_loop())
    asyncio.create_task(webrtc_session_watchdog_loop())
    asyncio.create_task(health_monitor_loop())
    asyncio.create_task(transcoder_watchdog_loop())

    if settings.edge_receiver_enabled:
        from .edge_receiver import start_edge_receiver
        asyncio.create_task(start_edge_receiver())

@app.on_event("shutdown")
async def shutdown():
    """Clean up all active transcoders on server shutdown."""
    from .transcoder import TranscoderManager
    await TranscoderManager.stop_all()

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
        select(CameraStream).where(CameraStream.stream_id == payload.stream_id)
    )
    stream = res.scalar_one_or_none()
    if not stream:
        raise HTTPException(status_code=400, detail=f"Unregistered stream_id: {payload.stream_id}")
        
    # 3. Verify file exists on local disk and size > 0
    p = Path(payload.file_path)
    if not p.exists():
        print(f"[webhook] File not found: {payload.file_path}")
        raise HTTPException(status_code=400, detail="File does not exist on disk")
        
    try:
        size = p.stat().st_size
        if size == 0:
            print(f"[webhook] Rejecting 0-byte file: {payload.file_path}")
            raise HTTPException(status_code=400, detail="File size is zero")
            
        end_ts = p.stat().st_mtime
    except Exception as e:
        print(f"[webhook] Error checking file stats for {payload.file_path}: {e}")
        raise HTTPException(status_code=400, detail=f"Error checking file: {e}")
        
    # 4. Calculate duration and start timestamp
    duration = await asyncio.to_thread(get_file_duration, payload.file_path, settings.ffmpeg_path)
    start_ts = end_ts - duration
    
    # 5. Insert RecordingSegment idempotent
    seg = RecordingSegment(
        stream_id=payload.stream_id,
        file_path=payload.file_path,
        start_ts=start_ts,
        end_ts=end_ts
    )
    session.add(seg)
    try:
        await session.commit()
        print(f"[webhook] Indexed segment: {payload.file_path} (Duration: {duration}s)")
        await PlaybackTimelineService.invalidate_cache_for_timestamp(payload.stream_id, start_ts)
    except IntegrityError:
        await session.rollback()
        print(f"[webhook] Duplicate segment ignored: {payload.file_path}")
        
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
        await asyncio.sleep(43200) # 12 hours
        async for session in get_session():
            try:
                await index_recordings(session, settings.recording_dir)
            except Exception as e:
                print("[indexer] Recovery scanner loop error:", e)

@app.get("/api/recordings/file")
async def recording_file(path: str):
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(p, media_type="video/mp4")

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
                always_on=always_on_val,
                status=StreamState.REGISTERED
            )
            session.add(stream)
            await session.flush()
        else:
            stream.stream_url = stream_url
            stream.resolution = res_str
            stream.fps = fps_val
            stream.codec = codec_val
            stream.bitrate = bitrate_val
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
    if sync:
        try:
            await sync_cameras(session)
        except Exception as e:
            print(f"[main] Failed to sync upstream cameras: {e}")

    res = await session.execute(
        select(Camera)
        .options(selectinload(Camera.streams))
        .order_by(Camera.name.asc())
    )
    return list(res.scalars().all())

@app.get("/api/cameras/{stream_id}", response_model=CameraOut)
async def get_camera(stream_id: str, session: Annotated[AsyncSession, Depends(get_session)]):
    # Retrieve the parent Camera for the requested stream ID
    res = await session.execute(
        select(CameraStream)
        .where(CameraStream.stream_id == stream_id)
        .options(selectinload(CameraStream.camera))
    )
    stream = res.scalar_one_or_none()
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
    res = await session.execute(
        select(CameraStream).where(CameraStream.stream_id == stream_id)
    )
    stream = res.scalar_one_or_none()
    if not stream:
        raise HTTPException(status_code=404, detail="Camera stream not found")

    await stream_manager.add_stream(session, stream)
    return {
        "stream_id": stream_id,
        "status": "started",
        "hls": f"/api/streams/{stream_id}/live/index.m3u8"
    }

@app.post("/api/cameras/{stream_id}/live/stop")
async def stop_live(stream_id: str, session: Annotated[AsyncSession, Depends(get_session)]):
    res = await session.execute(
        select(CameraStream).where(CameraStream.stream_id == stream_id)
    )
    stream = res.scalar_one_or_none()
    if not stream:
        raise HTTPException(status_code=404, detail="Camera stream not found")

    await stream_manager.remove_stream(session, stream)
    return {"stream_id": stream_id, "status": "stopped"}

@app.post("/api/cameras/{stream_id}/live/restart")
async def restart_live(stream_id: str, session: Annotated[AsyncSession, Depends(get_session)]):
    res = await session.execute(
        select(CameraStream).where(CameraStream.stream_id == stream_id)
    )
    stream = res.scalar_one_or_none()
    if not stream:
        raise HTTPException(status_code=404, detail="Camera stream not found")

    await stream_manager.restart_stream(session, stream)
    return {"stream_id": stream_id, "status": "restarted"}

# ----------------------------------------------------
# MediaMTX HLS Reverse Proxy Endpoints
# ----------------------------------------------------
@app.get("/api/streams/{stream_id}/live/index.m3u8")
async def hls_playlist(stream_id: str):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{settings.mediamtx_api_url.replace(':9997', ':8080')}/{stream_id}/index.m3u8")
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
        except Exception as e:
            print(f"[main] Error proxying index.m3u8 for {stream_id}: {e}")
    raise HTTPException(404, "Playlist not ready")

@app.get("/api/streams/{stream_id}/live/{filename}")
async def hls_segment(stream_id: str, filename: str):
    async with httpx.AsyncClient() as client:
        try:
            # Match endpoints and format params
            url = f"{settings.mediamtx_api_url.replace(':9997', ':8080')}/{stream_id}/{filename}"
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
    stream = stream_res.scalar_one_or_none()
    cam_name = stream.camera.name if stream and stream.camera else stream_id

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
        return

@app.get("/api/playback/{stream_id}/available-dates")
async def available_dates(stream_id: str, session: Annotated[AsyncSession, Depends(get_session)]):
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
        abs_path = os.path.abspath(seg.file_path)
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

    if not stream:
        if not settings.allow_unknown_edge_devices:
            raise HTTPException(status_code=403, detail="Forbidden: Unknown edge stream ID")
        
        # Auto-registration in development mode
        max_id_stmt = select(func.max(Camera.source_camera_id))
        max_id_res = await session.execute(max_id_stmt)
        max_id = max_id_res.scalar() or 0
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
    else:
        # Check active and synced_from_api
        camera = stream.camera
        if not settings.allow_unknown_edge_devices:
            if not camera or not camera.active or not camera.synced_from_api:
                raise HTTPException(status_code=403, detail="Forbidden: Device is inactive or not synchronized from Video Server API")

    # 2. Timestamp Extraction
    parsed_start_ts = start_ts
    if parsed_start_ts is None:
        filename = file.filename or ""
        # Try YYYYMMDD_HHMMSS
        match = re.search(r"(\d{8})_(\d{6})", filename)
        if match:
            try:
                date_str, time_str = match.groups()
                dt = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
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
    stmt_check = select(RecordingSegment).where(
        RecordingSegment.stream_id == stream_id,
        RecordingSegment.file_path == str(file_path)
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
        file_path=str(file_path),
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
