import asyncio
from datetime import datetime
from sqlalchemy import select
from ..db import get_session
from ..models import WebRTCSession
from ..registries.session_registry import SessionRegistry
from ..services.webrtc_service import WebRTCService
from ..config import settings

async def session_cleanup_worker_loop():
    """Background worker that periodically evicts expired sessions from DB and Redis."""
    print("[worker] Starting session cleanup worker loop...")
    await asyncio.sleep(5.0)

    while True:
        try:
            async for db_session in get_session():
                # Fetch active sessions from MediaMTX to cross-reference
                client = await WebRTCService.get_http_client()
                try:
                    resp = await client.get(f"{settings.mediamtx_api_url}/v3/webrtcsessions", timeout=5.0)
                    if resp.status_code == 200:
                        items = resp.json().get("items", [])
                        active_mediamtx_ids = {item.get("id") for item in items if isinstance(item, dict) and "id" in item}
                    else:
                        active_mediamtx_ids = set()
                except Exception as e:
                    print(f"[worker] Session cleanup could not fetch MediaMTX sessions: {e}")
                    active_mediamtx_ids = None

                if active_mediamtx_ids is not None:
                    # Query active DB sessions
                    stmt = select(WebRTCSession).where(WebRTCSession.status == "ACTIVE")
                    res = await db_session.execute(stmt)
                    active_sessions = res.scalars().all()

                    for db_s in active_sessions:
                        if db_s.session_id not in active_mediamtx_ids:
                            print(f"[worker] Session cleanup detected dead session: {db_s.session_id}. Evicting.")
                            await SessionRegistry.close_session(db_s.session_id, db_session)
            
        except Exception as e:
            print(f"[worker] Session cleanup loop error: {e}")
        
        await asyncio.sleep(10)
