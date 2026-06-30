import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import WebRTCSession
from ..services.redis_viewer_tracker import RedisViewerTracker

class SessionRegistry:
    @staticmethod
    async def create_session(
        session_id: str,
        stream_id: str,
        protocol: str,
        client_ip: str,
        user_id: Optional[uuid.UUID],
        browser_tab_id: Optional[str],
        db_session: AsyncSession
    ) -> WebRTCSession:
        """Register a new active viewer session and increment metrics."""
        stmt = select(WebRTCSession).where(WebRTCSession.session_id == session_id)
        res = await db_session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            return existing

        session_record = WebRTCSession(
            session_id=session_id,
            stream_id=stream_id,
            status="ACTIVE",
            protocol=protocol,
            client_ip=client_ip,
            user_id=user_id
        )
        db_session.add(session_record)
        await db_session.commit()

        # Update viewer count in Redis atomically
        details = {
            "user_id": str(user_id) if user_id else None,
            "browser_tab_id": browser_tab_id,
            "client_ip": client_ip,
            "protocol": protocol,
            "created_at": datetime.utcnow().isoformat()
        }
        await RedisViewerTracker.add_viewer_session(stream_id, session_id, details)
        print(f"[session_registry] Session {session_id} created for stream {stream_id}")
        return session_record

    @staticmethod
    async def close_session(session_id: str, db_session: AsyncSession) -> None:
        """Purge and terminate an active session."""
        stmt = select(WebRTCSession).where(
            WebRTCSession.session_id == session_id,
            WebRTCSession.status == "ACTIVE"
        )
        res = await db_session.execute(stmt)
        sess = res.scalar_one_or_none()
        if sess:
            sess.status = "CLOSED"
            sess.ended_at = datetime.utcnow()
            await db_session.commit()

            # Atomically remove from Redis and update counters
            await RedisViewerTracker.remove_viewer_session(sess.stream_id, session_id)
            print(f"[session_registry] Closed session {session_id} for stream {sess.stream_id}")
