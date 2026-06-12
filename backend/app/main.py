import json
import time
from pathlib import Path
from typing import Annotated
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import asyncio
import httpx
import os
import tempfile

from .indexer import index_recordings
from .config import settings
from .db import engine, Base, get_session
from .models import Camera, CameraStream, RecordingSegment, StreamState, ProfileType
from .schemas import CameraOut, CameraStreamOut, RecordingSegmentOut, SyncResponse
from .upstream import fetch_upstream_cameras
from .redis_client import RedisManager
from .stream_manager import stream_manager

app = FastAPI(title=settings.app_name)

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

@app.on_event("startup")
async def startup():
    # Attempt to auto-create PostgreSQL tables on start (fallback logic)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        print(f"[startup] PostgreSQL connection/migration failed: {e}. Falling back to local SQLite.")
        from .db import reset_db_engine
        sqlite_url = "sqlite+aiosqlite:///./data/app.db"
        Path("./data").mkdir(parents=True, exist_ok=True)
        reset_db_engine(sqlite_url)
        # Create SQLite tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    Path(settings.recording_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.hls_dir).mkdir(parents=True, exist_ok=True)

    # Sync registered camera streams with MediaMTX on boot
    async def initial_sync():
        await asyncio.sleep(2.0) # Wait for MediaMTX to boot up fully in Compose
        async for session in get_session():
            try:
                res = await session.execute(
                    select(CameraStream).join(Camera).where(Camera.active == True)
                )
                streams = res.scalars().all()
                print(f"[startup] Syncing {len(streams)} active streams with MediaMTX...")
                for stream in streams:
                    await stream_manager.add_stream(session, stream)
            except Exception as e:
                print(f"[startup] Error performing initial MediaMTX path sync: {e}")

    asyncio.create_task(initial_sync())

    # Start periodic watchdog loops
    asyncio.create_task(recording_index_loop())
    
    from .schedulers import (
        camera_scheduler_loop,
        camera_gap_recovery_loop,
        camera_archive_cleanup_loop
    )
    asyncio.create_task(camera_scheduler_loop())
    asyncio.create_task(camera_gap_recovery_loop())
    asyncio.create_task(camera_archive_cleanup_loop())

async def recording_index_loop():
    while True:
        async for session in get_session():
            try:
                await index_recordings(session, settings.recording_dir)
            except Exception as e:
                print("[indexer] Loop error:", e)
        await asyncio.sleep(5)

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
        res = await session.execute(
            select(Camera).where(Camera.source_camera_id == source_id)
        )
        camera = res.scalar_one_or_none()
        if not camera:
            camera = Camera(source_camera_id=source_id, name=name, active=active)
            session.add(camera)
            await session.flush()
        else:
            camera.name = name
            camera.active = active
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
            await session.flush()

        # Register in MediaMTX config
        if camera.active:
            await stream_manager.add_stream(session, stream)
        else:
            await stream_manager.remove_stream(session, stream)

        updated_count += 1

    await session.commit()
    return SyncResponse(total=len(raw_cameras), created_or_updated=updated_count, source=settings.upstream_camera_api_url)

@app.get("/api/cameras", response_model=List[CameraOut])
async def list_cameras(session: Annotated[AsyncSession, Depends(get_session)], sync: bool = Query(default=True)):
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
@app.get("/api/playback/{stream_id}", response_model=List[RecordingSegmentOut])
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
        select(CameraStream).where(CameraStream.stream_id == stream_id)
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

@app.get("/api/playback/{stream_id}/summary")
async def playback_summary(stream_id: str, session: Annotated[AsyncSession, Depends(get_session)]):
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
                proc.kill()
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

@app.get("/")
async def root():
    return {"message": "Enterprise VMS FastAPI backend is running"}
