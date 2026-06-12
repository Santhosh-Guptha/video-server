import json
import time
from pathlib import Path
from typing import Annotated
from urllib.parse import quote
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
from .indexer import index_recordings
from .config import settings
from .db import engine, Base, get_session
from .models import Camera, RecordingSegment
from .schemas import CameraOut, RecordingSegmentOut, SyncResponse
from .upstream import fetch_upstream_cameras
from .media import media_manager

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def normalize_camera(raw: dict) -> dict:
    camera_id = int(raw.get("cameraId") or raw.get("id"))
    stream_type = str(raw.get("streamType") or "").upper()
    stream_id = str(raw.get("streamId") or f"{raw.get('serverCameraId','camera')}_{stream_type}")

    return {
        "source_camera_id": camera_id,
        "stream_id": stream_id,
        "name": str(raw.get("name") or f"Camera {camera_id}"),
        "stream_type": stream_type,
        "rtsp_url": str(raw.get("rtspUrl") or ""),
        "fps": int(raw["fps"]) if raw.get("fps") is not None else None,
        "width": int(raw["width"]) if raw.get("width") is not None else None,
        "height": int(raw["height"]) if raw.get("height") is not None else None,
        "archive_type": str(raw.get("archiveType") or ""),
        "active": bool(raw.get("active", True)),
        "transcode": bool(raw.get("transcode", False)),
        "bitrate": int(raw["bitrate"]) if raw.get("bitrate") is not None else None,
        "camera_type": str(raw.get("cameraType") or ""),
        "decode_type": str(raw.get("decodeType") or ""),
        "server_http_port": int(raw["serverHttpPort"]) if raw.get("serverHttpPort") is not None else None,
        "raw_json": json.dumps(raw),
    }

@app.on_event("startup")
async def startup():

    # Ensure parent directory for database exists if using SQLite
    if "sqlite" in settings.database_url:
        parts = settings.database_url.split(":///")
        if len(parts) > 1:
            db_path = parts[1].split("?")[0]
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all
        )

    Path(settings.recording_dir).mkdir(
        parents=True,
        exist_ok=True
    )

    Path(settings.hls_dir).mkdir(
        parents=True,
        exist_ok=True
    )

    asyncio.create_task(
        recording_index_loop()
    )

@app.get(
    "/api/recordings/file"
)
async def recording_file(
    path: str
):
    p = Path(path)

    if not p.exists():
        raise HTTPException(
            404,
            "File not found"
        )

    return FileResponse(
        p,
        media_type="video/mp4"
    )


@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/api/cameras/sync", response_model=SyncResponse)
async def sync_cameras(session: Annotated[AsyncSession, Depends(get_session)]):
    raw_cameras = await fetch_upstream_cameras()
    updated = 0
    for raw in raw_cameras:
        item = normalize_camera(raw)
        stmt = select(Camera).where(Camera.stream_id == item["stream_id"])
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            for k, v in item.items():
                setattr(existing, k, v)
        else:
            session.add(Camera(**item))
        updated += 1
    await session.commit()
    return SyncResponse(total=len(raw_cameras), created_or_updated=updated, source=settings.upstream_camera_api_url)

@app.get("/api/cameras", response_model=list[CameraOut])
async def list_cameras(session: Annotated[AsyncSession, Depends(get_session)], sync: bool = Query(default=True)):
    if sync:
        raw_cameras = await fetch_upstream_cameras()
        for raw in raw_cameras:
            item = normalize_camera(raw)
            result = await session.execute(select(Camera).where(Camera.stream_id == item["stream_id"]))
            existing = result.scalar_one_or_none()
            if existing:
                for k, v in item.items():
                    setattr(existing, k, v)
            else:
                session.add(Camera(**item))
        await session.commit()

    res = await session.execute(select(Camera).order_by(Camera.name.asc(), Camera.stream_type.asc()))
    return list(res.scalars().all())

@app.get("/api/cameras/{stream_id}", response_model=CameraOut)
async def get_camera(stream_id: str, session: Annotated[AsyncSession, Depends(get_session)]):
    res = await session.execute(select(Camera).where(Camera.stream_id == stream_id))
    camera = res.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera

@app.post("/api/cameras/{stream_id}/live/start")
async def start_live(
    stream_id: str,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    res = await session.execute(
        select(Camera).where(Camera.stream_id == stream_id)
    )

    camera = res.scalar_one_or_none()

    if not camera:
        raise HTTPException(
            status_code=404,
            detail="Camera not found"
        )

    if not camera.rtsp_url:
        raise HTTPException(
            status_code=400,
            detail="RTSP URL missing"
        )

    raw = json.loads(camera.raw_json)

    username = raw.get("username")
    password = raw.get("password")

    rtsp_url = camera.rtsp_url.strip()

    if not rtsp_url.startswith(("rtsp://", "rtsps://")):
        rtsp_url = f"rtsp://{rtsp_url}"

    if username and password:

        protocol, rest = rtsp_url.split("://", 1)

        encoded_username = quote(str(username), safe="")
        encoded_password = quote(str(password), safe="")

        rtsp_url = (
            f"{protocol}://"
            f"{encoded_username}:{encoded_password}@"
            f"{rest}"
        )

    print(f"Starting stream: {stream_id}")
    print(f"RTSP URL: {rtsp_url}")

    await media_manager.start_rtsp_stream(
        stream_id,
        rtsp_url,
        settings.recording_dir,
        settings.hls_dir
    )

    return {
        "stream_id": stream_id,
        "status": "started",
        "hls": f"/api/streams/{stream_id}/live/index.m3u8"
    }


async def recording_index_loop():

    while True:

        async for session in get_session():

            try:
                await index_recordings(
                    session,
                    settings.recording_dir
                )
            except Exception as e:
                print("Indexer:", e)

        await asyncio.sleep(5)

@app.post("/api/cameras/{stream_id}/live/stop")
async def stop_live(stream_id: str):
    await media_manager.stop(stream_id)
    return {"stream_id": stream_id, "status": "stopped"}

@app.get("/api/streams/{stream_id}/live/index.m3u8")
async def hls_playlist(stream_id: str):
    path = Path(settings.hls_dir) / stream_id / "index.m3u8"
    if not path.exists():
        raise HTTPException(404, "Playlist not ready")
    return FileResponse(path)

@app.get("/api/streams/{stream_id}/live/{filename}")
async def hls_segment(stream_id: str, filename: str):
    path = Path(settings.hls_dir) / stream_id / filename
    if not path.exists():
        raise HTTPException(404, "Segment not found")
    return FileResponse(path)

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
    return segments

@app.get("/api/cameras/{stream_id}/recordings")
async def list_recordings(stream_id: str, session: Annotated[AsyncSession, Depends(get_session)]):
    res = await session.execute(
        select(RecordingSegment)
        .where(RecordingSegment.stream_id == stream_id)
        .order_by(RecordingSegment.start_ts.desc())
    )
    return [
        {
            "id": row.id,
            "stream_id": row.stream_id,
            "camera_name": row.camera_name,
            "file_path": row.file_path,
            "start_ts": row.start_ts,
            "end_ts": row.end_ts,
        }
        for row in res.scalars().all()
    ]

@app.websocket("/ws/status")
async def ws_status(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            payload = {
                "ts": time.time(),
                "streams": [
                    {
                        "stream_id": sid,
                        "running": proc.proc.returncode is None,
                        "subscribers": len(proc.subscribers),
                    }
                    for sid, proc in media_manager.streams.items()
                ],
            }
            await ws.send_json(payload)
            await ws.receive_text()
    except WebSocketDisconnect:
        return

@app.get("/")
async def root():
    return {"message": "Camera video platform backend is running"}
