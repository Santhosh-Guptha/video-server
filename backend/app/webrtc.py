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

async def resolve_stream_by_identifier(
    identifier: str,
    db_session: AsyncSession,
    purpose: str = "live"
) -> Optional[CameraStream]:
    """
    Resolves a camera stream from a flexible identifier (exact stream_id,
    case-insensitive stream_id, stream_id prefix, or camera name).
    """
    if not identifier:
        return None
        
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
        
    # 3. Check if the identifier matches a camera name (case-insensitive)
    # or is a prefix of a stream_id.
    # Let's get all streams that start with this identifier (e.g. IDENTIFIER_HD, IDENTIFIER_NORMAL)
    # or belong to a camera named IDENTIFIER.
    stmt = select(CameraStream).join(Camera).where(
        (func.lower(CameraStream.stream_id).like(f"{identifier.lower()}%")) |
        (func.lower(Camera.name) == identifier.lower())
    )
    res = await db_session.execute(stmt)
    streams = res.scalars().all()
    
    if not streams:
        return None
        
    # If multiple profiles exist, select the preferred profile according to the active policy
    if purpose == "playback":
        from .config import resolve_playback_profile
        preferred_profile_type = resolve_playback_profile()  # Returns "MAIN", "SUB", or "MOBILE"
    else:
        from .config import resolve_live_profile
        preferred_profile_type = resolve_live_profile()  # Returns "MAIN", "SUB", or "MOBILE"
    
    # Try to find the stream matching the preferred profile type
    for s in streams:
        if s.profile_type == preferred_profile_type:
            return s
            
    # Fallback logic
    if purpose == "playback":
        from .config import PLAYBACK_ALLOW_NORMAL_FALLBACK
        fallbacks = []
        if PLAYBACK_ALLOW_NORMAL_FALLBACK:
            fallbacks.append("SUB")
        fallbacks.extend(["MAIN", "SUB", "MOBILE"])
        for profile in fallbacks:
            for s in streams:
                if s.profile_type == profile:
                    return s
    else:
        for profile in ["SUB", "MAIN", "MOBILE"]:
            for s in streams:
                if s.profile_type == profile:
                    return s
                
    return streams[0]

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
        
    # Add TURN server if configured and active
    if settings.turn_server_url:
        from .health_monitor import check_coturn_health
        if await check_coturn_health():
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

    # 3. Dynamically update CameraStream specs in the database based on real-time stats
    try:
        from .models import CameraStream
        stream_res = await session.execute(
            select(CameraStream).where(CameraStream.stream_id == stream_id)
        )
        stream = stream_res.scalar_one_or_none()
        if stream:
            updated = False
            if payload.fps > 0:
                rounded_fps = max(1, int(round(payload.fps)))
                if stream.fps != rounded_fps:
                    print(f"[webrtc] Dynamically updating stream {stream_id} FPS from {stream.fps} to {rounded_fps} (live reported: {payload.fps})")
                    stream.fps = rounded_fps
                    updated = True
            if payload.resolution and stream.resolution != payload.resolution:
                print(f"[webrtc] Dynamically updating stream {stream_id} resolution from {stream.resolution} to {payload.resolution}")
                stream.resolution = payload.resolution
                updated = True
            if payload.bitrate > 0:
                bitrate_val = int(round(payload.bitrate))
                if not stream.bitrate or abs(stream.bitrate - bitrate_val) > 50:
                    print(f"[webrtc] Dynamically updating stream {stream_id} bitrate from {stream.bitrate} to {bitrate_val} kbps")
                    stream.bitrate = bitrate_val
                    updated = True
            if updated:
                session.add(stream)
    except Exception as update_err:
        print(f"[webrtc] Failed to dynamically update stream specs in DB: {update_err}")

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
        
        # Extract resolution if reported in any metrics
        resolution = next((m["resolution"] for m in realtime_metrics if m.get("resolution")), None)
        
        return {
            "active_viewers": count,
            "avg_fps": round(avg_fps, 2),
            "avg_bitrate_kbps": round(avg_bitrate, 2),
            "avg_rtt_ms": round(avg_rtt, 2) if avg_rtt is not None else None,
            "avg_packet_loss": round(avg_loss, 4),
            "resolution": resolution,
            "source": "realtime"
        }
        
    return {
        "active_viewers": len(active_sessions),
        "avg_fps": 0,
        "avg_bitrate_kbps": 0,
        "avg_rtt_ms": None,
        "avg_packet_loss": 0,
        "resolution": None,
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

    # 1. Enforce stream viewer limits (from vms_policy.MAX_WEBRTC_SESSIONS_PER_CAMERA)
    from .config import MAX_WEBRTC_SESSIONS_PER_CAMERA
    viewer_count = await RedisViewerTracker.get_viewer_count(stream_id)
    if viewer_count >= MAX_WEBRTC_SESSIONS_PER_CAMERA:
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

    # 3. Detect H.265 stream codec and route through transcoder if needed
    resolved_stream_id = stream_id
    mediamtx_stream_id = stream_id  # Default: proxy directly to the stream
    is_h265 = False
    try:
        cam_stream = await resolve_stream_by_identifier(stream_id, db_session)
        if cam_stream:
            resolved_stream_id = cam_stream.stream_id
            mediamtx_stream_id = resolved_stream_id
            if cam_stream.codec and cam_stream.codec.upper() == "H265":
                is_h265 = True
                try:
                    mediamtx_stream_id = await transcoder_manager.ensure_transcoder(
                        resolved_stream_id, db_session
                    )
                    print(f"[webrtc] H.265 stream {resolved_stream_id} -> routing to {mediamtx_stream_id}")
                except TranscoderCapacityError as e:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=str(e)
                    )
        else:
            print(f"[webrtc] Warning: could not resolve stream by identifier: {stream_id}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"[webrtc] Error checking stream codec for {stream_id}: {e}")

    body_bytes = await request.body()
    url = f"{settings.mediamtx_webrtc_url}/{mediamtx_stream_id}/{protocol}"
    
    print(f"[webrtc] WHEP POST request for stream_id={stream_id} (resolved to {resolved_stream_id}, proxied to {mediamtx_stream_id})")
    print(f"[webrtc] WHEP POST destination: {url}")
    print(f"[webrtc] WHEP POST offer SDP:\n{body_bytes.decode('utf-8', errors='replace')}")
    
    mtx_resp = None
    try:
        headers_dict = {"Content-Type": request.headers.get("Content-Type", "application/sdp")}
        mtx_resp = await asyncio.to_thread(
            _sync_http_request,
            url,
            "POST",
            body_bytes,
            headers_dict
        )
    except Exception as e:
        import traceback
        print(f"[webrtc] Connection to MediaMTX failed: {e}")
        traceback.print_exc()
        if is_h265:
            try:
                await transcoder_manager.register_viewer_disconnect(resolved_stream_id, db_session)
            except Exception as ex:
                print(f"[webrtc] Error rolling back transcoder viewer count on connection failure: {ex}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to media server signaling endpoint: {e}")
            
    print(f"[webrtc] WHEP POST response status: {mtx_resp.status_code}")
    print(f"[webrtc] WHEP POST response headers: {mtx_resp.headers}")
    print(f"[webrtc] WHEP POST response body:\n{mtx_resp.content.decode('utf-8', errors='replace')}")
            
    for k, v in mtx_resp.headers.items():
        if k.lower() not in ("content-length", "content-encoding", "transfer-encoding", "connection"):
            response.headers[k] = v
            
    response.status_code = mtx_resp.status_code
    
    if mtx_resp.status_code in (200, 201):
        location = mtx_resp.headers.get("Location")
        if location:
            session_id = location.rstrip("/").split("/")[-1]
            client_ip = request.client.host if request.client else "unknown"
            
            # Create DB session and register in viewer tracker under the RESOLVED stream_id
            await create_db_session(session_id, resolved_stream_id, protocol.upper(), client_ip, db_session, user_id)
            await RedisViewerTracker.add_viewer_session(resolved_stream_id, session_id, {
                "user_id": str(user_id) if user_id else None,
                "client_ip": client_ip,
                "protocol": protocol.upper(),
                "created_at": datetime.utcnow().isoformat(),
                "is_h265": is_h265
            })
            
            # Rewrite Location header to refer to the ORIGINAL stream_id
            # (transcoding is transparent to the client)
            if "/api/webrtc" in request.url.path:
                response.headers["Location"] = f"/api/webrtc/play/{stream_id}/{session_id}"
            else:
                response.headers["Location"] = f"/api/streams/{stream_id}/live/{protocol}/{session_id}"
            print(f"[webrtc] WHEP POST session created. Rewrote Location header to: {response.headers.get('Location')}")
    else:
        # Signaling failed in MediaMTX (e.g. 404/400). Roll back the transcoder viewer count.
        if is_h265:
            try:
                await transcoder_manager.register_viewer_disconnect(resolved_stream_id, db_session)
            except Exception as ex:
                print(f"[webrtc] Error rolling back transcoder viewer count on non-2xx status: {ex}")
            
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

    # Detect H.265 stream to route MediaMTX actions to the transcoded path
    resolved_stream_id = stream_id
    mediamtx_stream_id = stream_id
    is_h265 = False
    try:
        cam_stream = await resolve_stream_by_identifier(stream_id, db_session)
        if cam_stream:
            resolved_stream_id = cam_stream.stream_id
            mediamtx_stream_id = resolved_stream_id
            if cam_stream.codec and cam_stream.codec.upper() == "H265":
                is_h265 = True
                mediamtx_stream_id = f"{resolved_stream_id}_h264"
    except Exception as e:
        print(f"[webrtc] Error checking stream codec for action on {stream_id}: {e}")
 
    body_bytes = await request.body()
    url = f"{settings.mediamtx_webrtc_url}/{mediamtx_stream_id}/{protocol}/{session_id}"
    
    print(f"[webrtc] WHEP {request.method} request for stream_id={stream_id} (resolved to {resolved_stream_id}, session_id={session_id}, proxied to {mediamtx_stream_id})")
    print(f"[webrtc] WHEP {request.method} destination: {url}")
    if request.method == "PATCH":
        print(f"[webrtc] WHEP PATCH body:\n{body_bytes.decode('utf-8', errors='replace')}")
        
    try:
        headers_dict = {"Content-Type": request.headers.get("Content-Type", "application/sdp")}
        mtx_resp = await asyncio.to_thread(
            _sync_http_request,
            url,
            request.method,
            body_bytes,
            headers_dict
        )
    except Exception as e:
        import traceback
        print(f"[webrtc] Action proxy to MediaMTX failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Failed to connect to media server session endpoint: {e}")
            
    print(f"[webrtc] WHEP {request.method} response status: {mtx_resp.status_code}")
    print(f"[webrtc] WHEP {request.method} response headers: {mtx_resp.headers}")
    print(f"[webrtc] WHEP {request.method} response body:\n{mtx_resp.content.decode('utf-8', errors='replace')}")
            
    for k, v in mtx_resp.headers.items():
        if k.lower() not in ("content-length", "content-encoding", "transfer-encoding", "connection"):
            response.headers[k] = v
            
    response.status_code = mtx_resp.status_code
    
    if request.method == "DELETE" and mtx_resp.status_code in (200, 204):
        await close_db_session(session_id, db_session)
        await RedisViewerTracker.remove_viewer_session(resolved_stream_id, session_id)
        
        # Notify TranscoderManager of viewer disconnect for H.265 streams
        if is_h265:
            try:
                await transcoder_manager.register_viewer_disconnect(resolved_stream_id, db_session)
            except Exception as e:
                print(f"[webrtc] Error notifying transcoder disconnect for {resolved_stream_id}: {e}")
        
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
