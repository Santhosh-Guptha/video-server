import uuid
import asyncio
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import SessionLocal
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
        db_session: Optional[AsyncSession] = None,
    ) -> None:
        details = {
            "user_id": str(user_id) if user_id else None,
            "browser_tab_id": browser_tab_id,
            "client_ip": client_ip,
            "protocol": protocol,
            "created_at": datetime.utcnow().isoformat(),
        }
        try:
            await RedisViewerTracker.add_viewer_session(stream_id, session_id, details)
            print(f"[session_registry] Session {session_id} registered in Redis for stream {stream_id}")
        except Exception as exc:
            print(f"[session_registry] Failed to add viewer to Redis: {exc}")

        asyncio.create_task(
            SessionRegistry.create_session_in_db(
                session_id, stream_id, protocol, client_ip, user_id
            )
        )

    @staticmethod
    async def create_session_in_db(
        session_id: str,
        stream_id: str,
        protocol: str,
        client_ip: str,
        user_id: Optional[uuid.UUID],
    ) -> None:
        async with SessionLocal() as db:
            try:
                result = await db.execute(
                    select(WebRTCSession).where(WebRTCSession.session_id == session_id)
                )
                if result.scalar_one_or_none() is None:
                    db.add(
                        WebRTCSession(
                            session_id=session_id,
                            stream_id=stream_id,
                            status="ACTIVE",
                            protocol=protocol,
                            client_ip=client_ip,
                            user_id=user_id,
                        )
                    )
                    await db.commit()
                    print(f"[session_registry] Session {session_id} saved to DB in background.")
            except Exception as exc:
                await db.rollback()
                print(f"[session_registry] Error saving session {session_id} to DB: {exc}")

    @staticmethod
    async def close_session(
        session_id: str,
        db_session: Optional[AsyncSession] = None,
        stream_id: Optional[str] = None,
    ) -> None:
        if stream_id:
            try:
                await RedisViewerTracker.remove_viewer_session(stream_id, session_id)
                print(f"[session_registry] Session {session_id} removed from Redis instantly.")
            except Exception as exc:
                print(f"[session_registry] Error removing session {session_id} from Redis: {exc}")

        asyncio.create_task(SessionRegistry.close_session_in_db(session_id, stream_id))

    @staticmethod
    async def close_session_in_db(
        session_id: str, known_stream_id: Optional[str] = None
    ) -> None:
        async with SessionLocal() as db:
            try:
                result = await db.execute(
                    select(WebRTCSession).where(
                        WebRTCSession.session_id == session_id,
                        WebRTCSession.status == "ACTIVE",
                    )
                )
                session = result.scalar_one_or_none()
                if session:
                    session.status = "CLOSED"
                    session.ended_at = datetime.utcnow()
                    stream_id = known_stream_id or session.stream_id
                    await db.commit()
                    print(f"[session_registry] Session {session_id} marked CLOSED in DB.")
                    if not known_stream_id:
                        await RedisViewerTracker.remove_viewer_session(stream_id, session_id)
                elif known_stream_id:
                    await RedisViewerTracker.remove_viewer_session(known_stream_id, session_id)
            except Exception as exc:
                await db.rollback()
                print(f"[session_registry] Error closing session {session_id} in DB: {exc}")
