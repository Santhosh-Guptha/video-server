from datetime import datetime
import httpx
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .config import settings
from .models import WebRTCSession

async def create_db_session(
    session_id: str,
    stream_id: str,
    protocol: str,
    client_ip: str,
    db_session: AsyncSession,
    user_id: uuid.UUID | None = None
):
    """Inserts an active WebRTC session into the database."""
    res = await db_session.execute(
        select(WebRTCSession).where(WebRTCSession.session_id == session_id)
    )
    existing = res.scalar_one_or_none()
    if existing:
        return
        
    db_sess = WebRTCSession(
        session_id=session_id,
        stream_id=stream_id,
        status="ACTIVE",
        protocol=protocol,
        client_ip=client_ip,
        user_id=user_id
    )
    db_session.add(db_sess)
    await db_session.commit()
    print(f"[session_manager] Created DB session {session_id} for stream {stream_id} from IP {client_ip}")

async def close_db_session(session_id: str, db_session: AsyncSession):
    """Closes an active WebRTC session in the database."""
    res = await db_session.execute(
        select(WebRTCSession).where(
            WebRTCSession.session_id == session_id,
            WebRTCSession.status == "ACTIVE"
        )
    )
    db_sess = res.scalar_one_or_none()
    if db_sess:
        db_sess.status = "CLOSED"
        db_sess.ended_at = datetime.utcnow()
        await db_session.commit()
        print(f"[session_manager] Closed DB session {session_id}")

async def webrtc_session_watchdog_cleanup(db_session: AsyncSession):
    """Watchdog process that cleans up database sessions that are no longer active in MediaMTX."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{settings.mediamtx_api_url}/v3/webrtcsessions/list", timeout=5.0)
            if response.status_code != 200:
                response = await client.get(f"{settings.mediamtx_api_url}/v3/webrtcsessions", timeout=5.0)
                
            if response.status_code == 200:
                sessions_data = response.json().get("items", {})
                active_mediamtx_ids = set()
                if isinstance(sessions_data, dict):
                    active_mediamtx_ids = set(sessions_data.keys())
                elif isinstance(sessions_data, list):
                    active_mediamtx_ids = {item.get("id") for item in sessions_data if isinstance(item, dict) and "id" in item}
                
                res = await db_session.execute(
                    select(WebRTCSession).where(WebRTCSession.status == "ACTIVE")
                )
                db_sessions = res.scalars().all()
                
                # Collect stream IDs of pruned H.265 sessions for transcoder disconnect
                h265_disconnect_streams = set()
                
                for db_s in db_sessions:
                    if db_s.session_id not in active_mediamtx_ids:
                        print(f"[session_manager] Watchdog found dead session {db_s.session_id} in DB. Pruning.")
                        db_s.status = "CLOSED"
                        db_s.ended_at = datetime.utcnow()
                        
                        # Clean up Redis viewer tracking
                        try:
                            from .redis_viewer_tracker import RedisViewerTracker
                            await RedisViewerTracker.remove_viewer_session(db_s.stream_id, db_s.session_id)
                        except Exception as e:
                            print(f"[session_manager] Error cleaning viewer tracking for {db_s.session_id}: {e}")
                        
                        # Check if this stream is H.265 for transcoder disconnect
                        try:
                            from .models import CameraStream
                            stream_res = await db_session.execute(
                                select(CameraStream).where(CameraStream.stream_id == db_s.stream_id)
                            )
                            cam_stream = stream_res.scalar_one_or_none()
                            if cam_stream and cam_stream.codec and cam_stream.codec.upper() == "H265":
                                h265_disconnect_streams.add(db_s.stream_id)
                        except Exception as e:
                            print(f"[session_manager] Error checking codec for {db_s.stream_id}: {e}")
                
                await db_session.commit()
                
                # Notify TranscoderManager for H.265 streams that lost sessions
                if h265_disconnect_streams:
                    from .transcoder import TranscoderManager
                    for sid in h265_disconnect_streams:
                        try:
                            await TranscoderManager.register_viewer_disconnect(sid, db_session)
                        except Exception as e:
                            print(f"[session_manager] Error notifying transcoder disconnect for {sid}: {e}")
                            
        except Exception as e:
            print(f"[session_manager] Error running session watchdog cleanup: {e}")

