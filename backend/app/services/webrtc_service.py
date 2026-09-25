import logging
import httpx
from typing import Optional
from fastapi import Request, Response, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from ..models import CameraStream, StreamState
from ..registries.session_registry import SessionRegistry
from ..registries.stream_registry import StreamRegistry
from ..services.mediamtx_cache import MediaMTXCache
from ..transcoder import transcoder_manager, TranscoderCapacityError

logger = logging.getLogger(__name__)

class WebRTCService:
    _http_client: Optional[httpx.AsyncClient] = None
    # MediaMTX can expose a different path from the source stream when an
    # H.265 camera needs an H.264 compatibility stream.
    _session_paths: dict[str, tuple[str, str, bool]] = {}

    @classmethod
    async def get_http_client(cls) -> httpx.AsyncClient:
        """Lazily initialize shared async HTTP client for MediaMTX queries."""
        if cls._http_client is None or cls._http_client.is_closed:
            cls._http_client = httpx.AsyncClient(
                limits=httpx.Limits(max_connections=500, max_keepalive_connections=200),
                timeout=httpx.Timeout(10.0, connect=3.0)
            )
        return cls._http_client

    @classmethod
    async def proxy_whep_offer(
        cls,
        stream_id: str,
        sdp_offer: str,
        user_id: Optional[str],
        browser_tab_id: Optional[str],
        client_ip: str,
        db_session
    ) -> tuple[str, str]:
        """Proxies WHEP SDP offer to passive MediaMTX and returns (SDP answer, session ID)."""
        client = await cls.get_http_client()
        source_stream_id = stream_id
        media_stream_id, transcoded = await cls._select_browser_compatible_path(
            source_stream_id, db_session, sdp_offer
        )
        url = f"{settings.mediamtx_webrtc_url}/{media_stream_id}/whep"
        
        headers = {"Content-Type": "application/sdp"}
        try:
            resp = await client.post(url, content=sdp_offer, headers=headers)
            if resp.status_code not in (200, 201):
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"MediaMTX signaling failed: {resp.text}"
                )

            # Extract session ID from Location header
            location = resp.headers.get("Location")
            session_id = None
            if location:
                session_id = location.rstrip("/").split("/")[-1]
            if not session_id:
                import uuid
                session_id = str(uuid.uuid4())

            cls._session_paths[session_id] = (
                media_stream_id,
                source_stream_id,
                transcoded,
            )

            # Register in registries
            await SessionRegistry.create_session(
                session_id=session_id,
                stream_id=source_stream_id,
                protocol="WHEP",
                client_ip=client_ip,
                user_id=user_id,
                browser_tab_id=browser_tab_id,
                db_session=db_session
            )
                
            return resp.text, session_id
        except Exception as e:
            if transcoded:
                await transcoder_manager.register_viewer_disconnect(source_stream_id, db_session)
            if isinstance(e, httpx.RequestError):
                raise HTTPException(status_code=502, detail="Connection to media server failed") from e
            raise

    @classmethod
    async def proxy_whep_action(
        cls,
        stream_id: str,
        session_id: str,
        method: str,
        content: bytes,
        content_type: str,
        db_session
    ) -> Response:
        """Proxies WHEP actions (PATCH, DELETE) to MediaMTX session endpoints."""
        client = await cls.get_http_client()
        session_path = cls._session_paths.get(session_id)
        media_stream_id = session_path[0] if session_path else stream_id
        source_stream_id = session_path[1] if session_path else stream_id
        was_transcoded = session_path[2] if session_path else False
        url = f"{settings.mediamtx_webrtc_url}/{media_stream_id}/whep/{session_id}"
        
        headers = {"Content-Type": content_type}
        try:
            resp = await client.request(method, url, content=content, headers=headers)
            
            if method == "DELETE" and resp.status_code in (200, 204, 404):
                # Close the session cleanly in the registries
                await SessionRegistry.close_session(session_id, db_session, stream_id=source_stream_id)
                cls._session_paths.pop(session_id, None)
                if was_transcoded:
                    await transcoder_manager.register_viewer_disconnect(
                        source_stream_id, db_session
                    )
                return Response(status_code=204)

            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=dict(resp.headers)
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=502,
                detail=f"MediaMTX connection error: {e}"
            )

    @classmethod
    async def _select_browser_compatible_path(
        cls,
        stream_id: str,
        db_session,
        sdp_offer: str = "",
    ) -> tuple[str, bool]:
        """Preserve source quality when the browser offers H.265; otherwise
        use an H.264 source of the same profile or the shared transcoder.
        """
        result = await db_session.execute(
            select(CameraStream).where(CameraStream.stream_id == stream_id)
        )
        stream = result.scalar_one_or_none()
        live_codecs = await cls._path_codecs(stream_id)
        declared_codec = str(stream.codec or "").upper() if stream else ""
        is_h265 = "H265" in live_codecs or (not live_codecs and declared_codec == "H265")
        if not is_h265:
            return stream_id, False

        # MediaMTX 1.21 negotiates H.265 for browsers that explicitly offer it.
        # Preserve the requested HD profile instead of silently choosing a SUB feed.
        if any(line.startswith("a=rtpmap:") and " H265/90000" in line
               for line in sdp_offer.splitlines()):
            return stream_id, False

        siblings_result = await db_session.execute(
            select(CameraStream).where(
                CameraStream.camera_id == stream.camera_id,
                CameraStream.codec == "H264",
                CameraStream.profile_type == stream.profile_type,
            )
        )
        siblings = list(siblings_result.scalars().all())
        if siblings:
            def sibling_score(item: CameraStream):
                profile = getattr(item.profile_type, "value", item.profile_type)
                profile = str(profile or "").upper()
                # Lower-resolution SUB/NORMAL profiles start faster and are
                # the most reliable choice for mobile and multi-camera grids.
                return (0 if profile in ("SUB", "NORMAL") else 1, item.stream_id)

            for selected in sorted(siblings, key=sibling_score):
                sibling_codecs = await cls._path_codecs(selected.stream_id)
                if "H264" in sibling_codecs:
                    return selected.stream_id, False

        if not settings.enable_h265_transcoding:
            raise HTTPException(
                status_code=415,
                detail="Camera publishes H.265 and browser-compatible transcoding is disabled",
            )

        try:
            target = await transcoder_manager.ensure_transcoder(
                stream_id, db_session, increment_viewer=True
            )
            target_codecs = await cls._path_codecs(target)
            if "H264" not in target_codecs:
                await transcoder_manager.register_viewer_disconnect(stream_id, db_session)
                fallback = await cls._compatible_camera_fallback(stream, stream_id, db_session)
                if fallback:
                    return fallback, False
                raise HTTPException(
                    status_code=503,
                    detail="H.264 compatibility stream could not start because the source camera is unavailable",
                )
            return target, True
        except TranscoderCapacityError as exc:
            fallback = await cls._compatible_camera_fallback(stream, stream_id, db_session)
            if fallback:
                return fallback, False
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @classmethod
    async def _compatible_camera_fallback(cls, stream: CameraStream | None, stream_id: str, db_session: AsyncSession) -> str | None:
        """Use a verified H.264 sibling only after requested HD conversion fails."""
        if not stream:
            return None
        result = await db_session.execute(
            select(CameraStream).where(
                CameraStream.camera_id == stream.camera_id,
                CameraStream.stream_id != stream_id,
            )
        )
        candidates = list(result.scalars().all())
        candidates.sort(key=lambda item: (0 if str(getattr(item.profile_type, "value", item.profile_type)).upper() in ("MAIN", "HD") else 1, item.stream_id))
        for candidate in candidates:
            if "H264" in await cls._path_codecs(candidate.stream_id):
                print(f"[webrtc] Using H.264 sibling {candidate.stream_id} after conversion of {stream_id} failed")
                return candidate.stream_id
        return None

    @classmethod
    async def _path_codecs(cls, stream_id: str) -> set[str]:
        """Read codecs from the active MediaMTX path.

        Camera metadata can lag behind device configuration changes, while
        MediaMTX tracks describe the stream that WHEP will actually receive.
        """
        client = await cls.get_http_client()
        try:
            response = await client.get(
                f"{settings.mediamtx_api_url}/v3/paths/get/{stream_id}",
                timeout=2.0,
            )
            if response.status_code != 200:
                return set()
            payload = response.json()
            if not payload.get("ready"):
                return set()
            return {str(codec).upper() for codec in payload.get("tracks", [])}
        except (httpx.RequestError, ValueError):
            return set()
