import uuid
import asyncio
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
        db_session: Optional[AsyncSession] = None
    ) -> None:
        """Register a new active viewer session (Redis first, DB deferred in background)."""
        # 1. Update viewer count in Redis atomically (instant, non-blocking)
        details = {
            "user_id": str(user_id) if user_id else None,
            "browser_tab_id": browser_tab_id,
            "client_ip": client_ip,
            "protocol": protocol,
            "created_at": datetime.utcnow().isoformat()
        }
        try:
            await RedisViewerTracker.add_viewer_session(stream_id, session_id, details)
            print(f"[session_registry] Session {session_id} registered in Redis for stream {stream_id}")
        except Exception as e:
            print(f"[session_registry] Failed to add viewer to Redis: {e}")

        # 2. Defer PostgreSQL insert to a background task so it doesn't block signaling paths
        asyncio.create_task(SessionRegistry.create_session_in_db(
            session_id=session_id,
            stream_id=stream_id,
            protocol=protocol,
            client_ip=client_ip,
            user_id=user_id
        ))

    @staticmethod
    async def create_session_in_db(
        session_id: str,
        stream_id: str,
        protocol: str,
        client_ip: str,
        user_id: Optional[uuid.UUID]
    ):
        """Asynchronously saves the session record to PostgreSQL database in background."""
        from ..session_manager import create_db_session, close_db_session
        db = create_db_session()
        try:
            stmt = select(WebRTCSession).where(WebRTCSession.session_id == session_id)
            res = await db.execute(stmt)
            existing = res.scalar_one_or_none()
            if not existing:
                session_record = WebRTCSession(
                    session_id=session_id,
                    stream_id=stream_id,
                    status="ACTIVE",
                    protocol=protocol,
                    client_ip=client_ip,
                    user_id=user_id
                )
                db.add(session_record)
                await db.commit()
                print(f"[session_registry] Session {session_id} saved to DB in background.")
        except Exception as e:
            print(f"[session_registry] Error saving session {session_id} to DB: {e}")
        finally:
            close_db_session(db)

    @staticmethod
    async def close_session(
        session_id: str,
        db_session: Optional[AsyncSession] = None,
        stream_id: Optional[str] = None
    ) -> None:
        """Purge and terminate an active session (Redis first, DB deferred)."""
        if stream_id:
            try:
                await RedisViewerTracker.remove_viewer_session(stream_id, session_id)
                print(f"[session_registry] Session {session_id} removed from Redis instantly.")
            except Exception as e:
                print(f"[session_registry] Error removing session {session_id} from Redis: {e}")

        asyncio.create_task(SessionRegistry.close_session_in_db(session_id, stream_id))

    @staticmethod
    async def close_session_in_db(session_id: str, known_stream_id: Optional[str] = None):
        """Asynchronously updates the session status to CLOSED in the background."""
        from ..session_manager import create_db_session, close_db_session
        db = create_db_session()
        try:
            stmt = select(WebRTCSession).where(
                WebRTCSession.session_id == session_id,
                WebRTCSession.status == "ACTIVE"
            )
            res = await db.execute(stmt)
            sess = res.scalar_one_or_none()
            if sess:
                sess.status = "CLOSED"
                sess.ended_at = datetime.utcnow()
                stream_id = known_stream_id or sess.stream_id
                await db.commit()
                print(f"[session_registry] Session {session_id} marked CLOSED in DB.")
                
                if not known_stream_id:
                    await RedisViewerTracker.remove_viewer_session(stream_id, session_id)
            else:
                if known_stream_id:
                    await RedisViewerTracker.remove_viewer_session(known_stream_id, session_id)
        except Exception as e:
            print(f"[session_registry] Error closing session {session_id} in DB: {e}")
        finally:
            close_db_session(db)
