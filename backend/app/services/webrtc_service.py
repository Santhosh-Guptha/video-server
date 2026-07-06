import httpx
from typing import Optional
from fastapi import Request, Response, HTTPException, status
from ..config import settings
from ..registries.session_registry import SessionRegistry
from ..registries.stream_registry import StreamRegistry
from ..services.mediamtx_cache import MediaMTXCache

class WebRTCService:
    _http_client: Optional[httpx.AsyncClient] = None

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
        url = f"{settings.mediamtx_webrtc_url}/{stream_id}/whep"
        
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

            # Register in registries
            await SessionRegistry.create_session(
                session_id=session_id,
                stream_id=stream_id,
                protocol="WHEP",
                client_ip=client_ip,
                user_id=user_id,
                browser_tab_id=browser_tab_id,
                db_session=db_session
            )
                
            return resp.text, session_id
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Connection to media server failed: {e}"
            )

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
        url = f"{settings.mediamtx_webrtc_url}/{stream_id}/whep/{session_id}"
        
        headers = {"Content-Type": content_type}
        try:
            resp = await client.request(method, url, content=content, headers=headers)
            
            if method == "DELETE" and resp.status_code in (200, 204, 404):
                # Close the session cleanly in the registries
                await SessionRegistry.close_session(session_id, db_session, stream_id=stream_id)
                
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
