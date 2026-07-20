import json
import os
import uuid
import http.client
http.client._MAXHEADERS = 100000
import httpx
import asyncio
import urllib.request
import urllib.error
from datetime import datetime
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session
from .models import WebRTCSession, StreamMetricHistory, CameraStream, StreamState, Camera
from .redis_client import RedisManager
from .redis_viewer_tracker import RedisViewerTracker
from .session_manager import create_db_session, close_db_session
from .transcoder import transcoder_manager, TranscoderManager, TranscoderCapacityError

class DummyResponse:
    def __init__(self, content: bytes, status_code: int, headers: dict):
        self.content = content
        self.status_code = status_code
        self.headers = headers

def _sync_http_request(url: str, method: str, content: bytes, headers: dict) -> DummyResponse:
    req = urllib.request.Request(
        url,
        data=content if method in ("POST", "PUT", "PATCH") else None,
        headers=headers,
        method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            resp_headers = {k: v for k, v in resp.headers.items()}
            print(f"[webrtc] WHEP proxy succeeded. Status: {resp.status}, Response Headers Count: {len(resp.headers.keys())}")
            return DummyResponse(
                content=resp.read(),
                status_code=resp.status,
                headers=resp_headers
            )
    except urllib.error.HTTPError as e:
        resp_headers = {k: v for k, v in e.headers.items()}
        return DummyResponse(
            content=e.read(),
            status_code=e.code,
            headers=resp_headers
        )
    except Exception as e:
        raise e

router = APIRouter(prefix="/api/webrtc", tags=["webrtc"])
streams_router = APIRouter(prefix="/api/streams", tags=["streams"])

def is_private_rtsp_url(url: str) -> bool:
    if not url:
        return False
    try:
        host = url.split("://", 1)[-1].split("@")[-1].split("/")[0].split(":")[0]
        if host == "localhost" or host == "127.0.0.1":
            return True
        if host.startswith("10.") or host.startswith("192.168."):
            return True
        if host.startswith("172."):
            parts = host.split(".")
            if len(parts) >= 2:
                try:
                    second_octet = int(parts[1])
                    if 16 <= second_octet <= 31:
                        return True
                except ValueError:
                    pass
    except Exception:
        pass
    return False

async def resolve_stream_by_identifier(
    identifier: str,
    db_session: AsyncSession,
    purpose: str = "live"
) -> Optional[CameraStream]:
    """
    Resolves a camera stream from a flexible identifier (exact stream_id,
    case-insensitive stream_id, server_camera_id, source_camera_id,
    stream_id prefix, or camera name).
    Always returns the best matching stream config, prioritizing MAIN/HD streams.
    """
    if not identifier:
        return None
        
    def get_best_stream(streams_list):
        if not streams_list:
            return None
        
        pref = settings.preferred_profile.upper() if hasattr(settings, "preferred_profile") else "HD"
        fallback_enabled = settings.live_stream_fallback if hasattr(settings, "live_stream_fallback") else True
        if pref in ("NORMAL", "SUB"):
            target_profile = "SUB"
            fallback_profile = "MAIN"
        else:
            target_profile = "MAIN"
            fallback_profile = "SUB"
            
        def sort_key(s: CameraStream):
            is_active = s.status in (StreamState.ONLINE, StreamState.WARM)
            
            profile_str = getattr(s, "profile_type", "")
            profile_str = profile_str.value if hasattr(profile_str, 'value') else str(profile_str)
            profile_upper = profile_str.upper()
            
            is_preferred = (profile_upper == target_profile or 
                            (target_profile == "SUB" and profile_upper == "NORMAL") or
                            (target_profile == "MAIN" and profile_upper == "HD"))
                            
            is_fallback = (profile_upper == fallback_profile or 
                           (fallback_profile == "SUB" and profile_upper == "NORMAL") or
                           (fallback_profile == "MAIN" and profile_upper == "HD"))
            
            if is_active and is_preferred:
                score = 0
            elif is_active and is_fallback and fallback_enabled:
                score = 1
            elif is_preferred:
                score = 2
            elif is_fallback and fallback_enabled:
                score = 3
            else:
                score = 4
                
            return (score, s.stream_id)
            
        return sorted(streams_list, key=sort_key)[0]

    # 1. Exact match on stream_id
    stmt = select(CameraStream).where(CameraStream.stream_id == identifier)
    res = await db_session.execute(stmt)
    stream = res.scalar_one_or_none()
    if stream:
        return stream
        
    # 2. Case-insensitive match on stream_id
    stmt = select(CameraStream).where(func.lower(CameraStream.stream_id) == identifier.lower())
    res = await db_session.execute(stmt)
    stream = res.scalar_one_or_none()
    if stream:
        return stream

    # 3. Match on integer source_camera_id
    try:
        cam_id_int = int(identifier)
        stmt = select(CameraStream).join(Camera).where(Camera.source_camera_id == cam_id_int)
        res = await db_session.execute(stmt)
        streams = res.scalars().all()
        if streams:
            return get_best_stream(streams)
    except ValueError:
        pass
        
    # 4. Check if the identifier matches a camera server_camera_id, name, or stream_id prefix
    stmt = select(CameraStream).join(Camera).where(
        (func.lower(CameraStream.stream_id).like(f"{identifier.lower()}%")) |
        (func.lower(Camera.server_camera_id) == identifier.lower()) |
        (func.lower(Camera.name) == identifier.lower())
    )
    res = await db_session.execute(stmt)
    streams = res.scalars().all()
    
    if streams:
        return get_best_stream(streams)
        
    return None

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
            host = None
            referer = request.headers.get("referer")
            if referer:
                try:
                    from urllib.parse import urlparse
                    host = urlparse(referer).hostname
                except Exception:
                    pass
            if not host:
                origin = request.headers.get("origin")
                if origin:
                    try:
                        from urllib.parse import urlparse
                        host = urlparse(origin).hostname
                    except Exception:
                        pass
            if not host:
                host = request.headers.get("x-forwarded-host")
                if host and ":" in host:
                    host = host.split(":")[0]
            if not host:
                host = request.url.hostname
                
            host = host or "localhost"
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

from .services.webrtc_service import WebRTCService
from .registries.session_registry import SessionRegistry
from .registries.stream_registry import StreamRegistry

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

    # Resolve stream_id dynamically to prioritize MAIN/HD
    stream = await resolve_stream_by_identifier(stream_id, db_session)
    if stream:
        stream_id = stream.stream_id

    # 1. Enforce stream viewer limits
    from .config import MAX_WEBRTC_SESSIONS_PER_CAMERA
    viewer_count = await RedisViewerTracker.get_viewer_count(stream_id)
    if viewer_count >= MAX_WEBRTC_SESSIONS_PER_CAMERA:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Stream viewer limit exceeded"
        )
    
    # 2. Extract user_id and browser_tab_id
    user_id_str = request.query_params.get("user_id") or str(uuid.uuid4())
    browser_tab_id = request.query_params.get("browser_tab_id")
    client_ip = request.client.host if request.client else "unknown"
    
    body_bytes = await request.body()
    sdp_offer = body_bytes.decode("utf-8", errors="replace")
    
    # 3. Call Service layer
    sdp_answer, session_id = await WebRTCService.proxy_whep_offer(
        stream_id=stream_id,
        sdp_offer=sdp_offer,
        user_id=user_id_str,
        browser_tab_id=browser_tab_id,
        client_ip=client_ip,
        db_session=db_session
    )
    
    # 4. Construct Location header
    if "/api/webrtc" in request.url.path:
        location_url = f"/api/webrtc/play/{stream_id}/{session_id}"
    else:
        location_url = f"/api/streams/{stream_id}/live/whep/{session_id}"
        
    return Response(
        content=sdp_answer,
        status_code=201,
        headers={
            "Content-Type": "application/sdp",
            "Location": location_url
        }
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

    # Resolve stream_id dynamically to prioritize MAIN/HD
    stream = await resolve_stream_by_identifier(stream_id, db_session)
    if stream:
        stream_id = stream.stream_id

    body_bytes = await request.body()
    content_type = request.headers.get("Content-Type", "application/sdp")
    
    return await WebRTCService.proxy_whep_action(
        stream_id=stream_id,
        session_id=session_id,
        method=request.method,
        content=body_bytes,
        content_type=content_type,
        db_session=db_session
    )

    response.status_code = mtx_resp.status_code
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
