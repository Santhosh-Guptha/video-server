import json
import os
import uuid
import httpx
from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session
from .models import WebRTCSession, StreamMetricHistory, CameraStream, StreamState
from .redis_client import RedisManager
from .redis_viewer_tracker import RedisViewerTracker
from .session_manager import create_db_session, close_db_session

router = APIRouter(prefix="/api/webrtc", tags=["webrtc"])
streams_router = APIRouter(prefix="/api/streams", tags=["streams"])

class StatsPayload(BaseModel):
    session_id: str
    fps: float
    resolution: str | None = None
    bitrate: float
    rtt: float | None = None
    packet_loss: float
    jitter: float | None = None
    frames_dropped: int
    decoder_latency: float | None = None

@router.get("/ice-servers")
async def get_ice_servers(request: Request):
    """Returns the STUN and TURN server configurations for WebRTC players."""
    # Check if WebRTC is enabled
    if not settings.enable_webrtc:
        raise HTTPException(status_code=400, detail="WebRTC is disabled")

    ice_servers = []
    
    # Add STUN servers
    if settings.stun_servers:
        ice_servers.append({
            "urls": settings.stun_servers
        })
        
    # Add TURN server if configured
    if settings.turn_server_url:
        turn_url = settings.turn_server_url
        if "localhost" in turn_url or "127.0.0.1" in turn_url:
            host = request.headers.get("x-forwarded-host") or request.url.hostname or "localhost"
            if ":" in host:
                host = host.split(":")[0]
            turn_url = turn_url.replace("localhost", host).replace("127.0.0.1", host)
            
        turn_config = {
            "urls": [turn_url]
        }
        if settings.turn_server_username:
            turn_config["username"] = settings.turn_server_username
        if settings.turn_server_credential:
            turn_config["credential"] = settings.turn_server_credential
        ice_servers.append(turn_config)
        
    return {"iceServers": ice_servers}

@router.post("/streams/{stream_id}/stats")
async def report_stream_stats(
    stream_id: str,
    payload: StatsPayload,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    """Stores real-time stats in Redis and historical stats in PostgreSQL."""
    # 1. Store in Redis for real-time visualization (30 second TTL)
    redis_key = f"vms:stats:realtime:{stream_id}:{payload.session_id}"
    serialized_payload = json.dumps(payload.dict())
    
    from .redis_client import redis_client
    if redis_client:
        try:
            await redis_client.set(redis_key, serialized_payload, ex=30)
        except Exception as e:
            print(f"[webrtc] Failed to cache stats in Redis: {e}")
            RedisManager._memory_cache[redis_key] = serialized_payload
    else:
        RedisManager._memory_cache[redis_key] = serialized_payload

    # 2. Write to historical PostgreSQL database
    history = StreamMetricHistory(
        stream_id=stream_id,
        session_id=payload.session_id,
        fps=payload.fps,
        resolution=payload.resolution,
        bitrate=payload.bitrate,
        rtt=payload.rtt,
        packet_loss=payload.packet_loss,
        jitter=payload.jitter,
        frames_dropped=payload.frames_dropped,
        decoder_latency=payload.decoder_latency
    )
    session.add(history)
    await session.commit()
    
    return {"status": "ok"}

@router.get("/streams/{stream_id}/stats")
async def get_stream_stats(
    stream_id: str,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    """
    Fetches real-time aggregated stats of all active viewers on a stream.
    Falls back to querying historical averages if no real-time sessions are active.
    """
    # 1. Fetch all active sessions for this stream from DB
    res = await session.execute(
        select(WebRTCSession).where(
            WebRTCSession.stream_id == stream_id,
            WebRTCSession.status == "ACTIVE"
        )
    )
    active_sessions = res.scalars().all()
    active_session_ids = {s.session_id for s in active_sessions}
    
    realtime_metrics = []
    
    # 2. Pull stats from Redis cache
    from .redis_client import redis_client
    for sid in active_session_ids:
        redis_key = f"vms:stats:realtime:{stream_id}:{sid}"
        data = None
        if redis_client:
            try:
                data = await redis_client.get(redis_key)
            except Exception:
                pass
        if not data and RedisManager._memory_cache:
            data = RedisManager._memory_cache.get(redis_key)
            
        if data:
            try:
                realtime_metrics.append(json.loads(data))
            except Exception:
                pass
                
    if realtime_metrics:
        count = len(realtime_metrics)
        avg_fps = sum(m["fps"] for m in realtime_metrics) / count
        avg_bitrate = sum(m["bitrate"] for m in realtime_metrics) / count
        avg_rtt = sum(m["rtt"] for m in realtime_metrics if m.get("rtt") is not None) / count if any(m.get("rtt") is not None for m in realtime_metrics) else None
        avg_loss = sum(m["packet_loss"] for m in realtime_metrics) / count
        
        return {
            "active_viewers": count,
            "avg_fps": round(avg_fps, 2),
            "avg_bitrate_kbps": round(avg_bitrate, 2),
            "avg_rtt_ms": round(avg_rtt, 2) if avg_rtt is not None else None,
            "avg_packet_loss": round(avg_loss, 4),
            "source": "realtime"
        }
        
    return {
        "active_viewers": len(active_sessions),
        "avg_fps": 0,
        "avg_bitrate_kbps": 0,
        "avg_rtt_ms": None,
        "avg_packet_loss": 0,
        "source": "inactive"
    }

# Helper for generic WHEP/WHIP signaling proxy
async def proxy_signaling_session(
    stream_id: str,
    protocol: str,
    request: Request,
    response: Response,
    db_session: AsyncSession
):
    if not settings.enable_webrtc:
        raise HTTPException(status_code=400, detail="WebRTC streaming is disabled")

    if request.method == "OPTIONS":
        return Response(status_code=204)

    # 1. Enforce stream viewer limits
    viewer_count = await RedisViewerTracker.get_viewer_count(stream_id)
    if viewer_count >= settings.max_subscribers_per_stream:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Stream viewer limit exceeded"
        )
    
    # 2. Extract or dynamically generate user_id to enforce user session limits
    user_id_str = request.query_params.get("user_id")
    user_id = None
    if user_id_str:
        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            pass
            
    # Auto-generate user_id if not present
    if not user_id:
        user_id = uuid.uuid4()
            
    if user_id:
        # Count active user sessions
        stmt = select(WebRTCSession).where(
            WebRTCSession.user_id == user_id,
            WebRTCSession.status == "ACTIVE"
        )
        res = await db_session.execute(stmt)
        active_user_sess = res.scalars().all()
        if len(active_user_sess) >= 32: # Limit to 32 concurrent sessions per user (supports grid views)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Active session limit exceeded for this user"
            )

    body_bytes = await request.body()
    url = f"{settings.mediamtx_webrtc_url}/{stream_id}/{protocol}"
    
    async with httpx.AsyncClient() as client:
        try:
            mtx_resp = await client.post(
                url,
                content=body_bytes,
                headers={"Content-Type": request.headers.get("Content-Type", "application/sdp")},
                timeout=15.0
            )
        except Exception as e:
            import traceback
            print(f"[webrtc] Connection to MediaMTX failed: {e}")
            traceback.print_exc()
            raise HTTPException(status_code=502, detail=f"Failed to connect to media server signaling endpoint: {e}")
            
    for k, v in mtx_resp.headers.items():
        if k.lower() not in ("content-length", "content-encoding", "transfer-encoding", "connection"):
            response.headers[k] = v
            
    response.status_code = mtx_resp.status_code
    
    if mtx_resp.status_code in (200, 201):
        location = mtx_resp.headers.get("Location")
        if location:
            session_id = location.rstrip("/").split("/")[-1]
            client_ip = request.client.host if request.client else "unknown"
            
            # Create DB session and register in viewer tracker
            await create_db_session(session_id, stream_id, protocol.upper(), client_ip, db_session, user_id)
            await RedisViewerTracker.add_viewer_session(stream_id, session_id, {
                "user_id": str(user_id) if user_id else None,
                "client_ip": client_ip,
                "protocol": protocol.upper(),
                "created_at": datetime.utcnow().isoformat()
            })
            
            # Rewrite Location header dynamically based on the incoming request route prefix
            if "/api/webrtc" in request.url.path:
                response.headers["Location"] = f"/api/webrtc/play/{stream_id}/{session_id}"
            else:
                response.headers["Location"] = f"/api/streams/{stream_id}/live/{protocol}/{session_id}"
            
    return Response(
        content=mtx_resp.content,
        status_code=mtx_resp.status_code,
        headers=dict(response.headers)
    )

async def proxy_signaling_action(
    stream_id: str,
    session_id: str,
    protocol: str,
    request: Request,
    response: Response,
    db_session: AsyncSession
):
    if not settings.enable_webrtc:
        raise HTTPException(status_code=400, detail="WebRTC streaming is disabled")

    if request.method == "OPTIONS":
        return Response(status_code=204)
        
    body_bytes = await request.body()
    url = f"{settings.mediamtx_webrtc_url}/{stream_id}/{protocol}/{session_id}"
    
    async with httpx.AsyncClient() as client:
        try:
            mtx_resp = await client.request(
                method=request.method,
                url=url,
                content=body_bytes,
                headers={"Content-Type": request.headers.get("Content-Type", "application/sdp")},
                timeout=15.0
            )
        except Exception as e:
            import traceback
            print(f"[webrtc] Action proxy to MediaMTX failed: {e}")
            traceback.print_exc()
            raise HTTPException(status_code=502, detail=f"Failed to connect to media server session endpoint: {e}")
            
    for k, v in mtx_resp.headers.items():
        if k.lower() not in ("content-length", "content-encoding", "transfer-encoding", "connection"):
            response.headers[k] = v
            
    response.status_code = mtx_resp.status_code
    
    if request.method == "DELETE" and mtx_resp.status_code in (200, 204):
        await close_db_session(session_id, db_session)
        await RedisViewerTracker.remove_viewer_session(stream_id, session_id)
        
    return Response(
        content=mtx_resp.content,
        status_code=mtx_resp.status_code,
        headers=dict(response.headers)
    )

# WHEP Routes
@streams_router.post("/{stream_id}/live/whep")
@streams_router.options("/{stream_id}/live/whep")
async def whep_post(
    stream_id: str,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    return await proxy_signaling_session(stream_id, "whep", request, response, session)

@streams_router.api_route("/{stream_id}/live/whep/{session_id}", methods=["POST", "PATCH", "DELETE", "OPTIONS"])
async def whep_session_route(
    stream_id: str,
    session_id: str,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    return await proxy_signaling_action(stream_id, session_id, "whep", request, response, session)

# WHIP Routes
@streams_router.post("/{stream_id}/live/whip")
@streams_router.options("/{stream_id}/live/whip")
async def whip_post(
    stream_id: str,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    return await proxy_signaling_session(stream_id, "whip", request, response, session)

@streams_router.api_route("/{stream_id}/live/whip/{session_id}", methods=["POST", "PATCH", "DELETE", "OPTIONS"])
async def whip_session_route(
    stream_id: str,
    session_id: str,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    return await proxy_signaling_action(stream_id, session_id, "whip", request, response, session)


# New Dynamic WebRTC play API for camera_id (where camera_id corresponds to stream_id)
@router.post("/play/{camera_id}")
@router.options("/play/{camera_id}")
async def webrtc_play_camera(
    camera_id: str,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    """Serve live WebRTC WHEP signaling for a camera ID.
    Validates stream status, auto-generates missing user_id, and proxies to MediaMTX.
    """
    return await proxy_signaling_session(camera_id, "whep", request, response, session)

@router.api_route("/play/{camera_id}/{session_id}", methods=["POST", "PATCH", "DELETE", "OPTIONS"])
async def webrtc_play_session_route(
    camera_id: str,
    session_id: str,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    """Handle WebRTC WHEP session actions (Trickle ICE, Session Termination) for camera ID."""
    return await proxy_signaling_action(camera_id, session_id, "whep", request, response, session)
