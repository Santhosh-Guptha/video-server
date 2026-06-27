import asyncio
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from .models import CameraStream
from .transcoding_decision_engine import TranscodingDecisionEngine
from .session_registry import SessionRegistry, SessionState
from .event_bus import EventBus
from .local_transcoder import LocalTranscoder
from .transcoding_client import TranscodingClient
from .config import settings

class StreamRouter:
    @classmethod
    async def route_live(
        cls,
        stream: CameraStream,
        session_id: str,
        client_profile: Dict[str, Any],
        db_session: AsyncSession
    ) -> str:
        """
        Routes a live streaming request instantly without blocking.
        Decides between Direct (H264/native H265), Cloud, or Local fallbacks.
        """
        codec = stream.codec or "H264"
        
        # 1. Ask Transcoding Decision Engine (O(1) cached check)
        route_choice = await TranscodingDecisionEngine.determine_route(
            codec=codec,
            client_profile=client_profile
        )

        print(f"[stream_router] Live routing choice for {stream.stream_id}: {route_choice}")
        target_path = stream.stream_id

        # 2. Execute selected path
        if route_choice == "cloud":
            # Cloud transcoding H265 -> H264
            target_path = f"{stream.stream_id}_h264"
            
            # Formulate RTSP URLs
            vms_ip = settings.mediamtx_api_url.replace("http://", "").split(":")[0]
            if vms_ip == "127.0.0.1" or vms_ip == "localhost":
                # Fallback to discoverable container name or network IP
                import socket
                try:
                    vms_ip = socket.gethostbyname(socket.gethostname())
                except:
                    vms_ip = "127.0.0.1"
                    
            source_url = f"rtsp://{vms_ip}:8554/{stream.stream_id}"
            target_url = f"rtsp://{vms_ip}:8554/{target_path}"
            
            # Start cloud session asynchronously
            success = await TranscodingClient.start_session(
                stream_id=stream.stream_id,
                session_id=session_id,
                source_url=source_url,
                target_url=target_url
            )
            
            if not success:
                # Immediate failover to local fallback transcoding if cloud API fails
                print("[stream_router] Cloud session failed to start. Falling back to local.")
                route_choice = "local"
                target_path = await LocalTranscoder.start_session(
                    stream.stream_id, session_id, db_session
                )
            
        elif route_choice == "local":
            # Local transcoding H265 -> H264
            target_path = await LocalTranscoder.start_session(
                stream.stream_id, session_id, db_session
            )

        # 3. Register in Session Registry
        session_state = SessionState(
            session_id=session_id,
            stream_id=stream.stream_id,
            session_type="live",
            source_type=route_choice,
            codec=codec,
            resolution=stream.resolution,
            fps=stream.fps
        )
        await SessionRegistry.register_session(session_state)

        # 4. Publish Event
        await EventBus.publish("stream_started", {
            "stream_id": stream.stream_id,
            "session_id": session_id,
            "route": route_choice
        })

        return target_path

    @classmethod
    async def release_live(
        cls,
        stream_id: str,
        session_id: str,
        db_session: AsyncSession
    ) -> None:
        """Called when a live viewer disconnects."""
        session = await SessionRegistry.unregister_session(session_id)
        if session:
            if session.source_type == "cloud":
                await TranscodingClient.stop_session(stream_id, session_id)
            elif session.source_type == "local":
                await LocalTranscoder.stop_session(stream_id, session_id, db_session)
                
            await EventBus.publish("stream_stopped", {
                "stream_id": stream_id,
                "session_id": session_id,
                "route": session.source_type
            })

    @classmethod
    async def route_playback(
        cls,
        stream: CameraStream,
        start_ts: float,
        end_ts: float,
        client_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Determines playback routing. Returns dictionary containing route specs:
        {
          "transcode": bool,
          "vcodec": str, # "copy" or "libx264"
          "codec": str
        }
        """
        codec = stream.codec or "H264"
        supports_h265 = client_profile.get("supports_h265", False)
        
        # H264 is never transcoded
        if codec.upper() == "H264":
            return {"transcode": False, "vcodec": "copy", "codec": "H264"}
            
        # H265 played on H265-supported client is not transcoded
        if supports_h265:
            return {"transcode": False, "vcodec": "copy", "codec": "H265"}
            
        # Needs playback transcoding H265 -> H264
        return {"transcode": True, "vcodec": "libx264", "codec": "H265"}

    @classmethod
    async def route_ai(cls, stream_id: str) -> str:
        """AI always consumes the original stream. Never transcoded."""
        vms_ip = "127.0.0.1"
        return f"rtsp://{vms_ip}:8554/{stream_id}"

    @classmethod
    async def route_recording(cls, stream_id: str) -> str:
        """Recording always saves the original stream bytes without transcoding."""
        return stream_id
