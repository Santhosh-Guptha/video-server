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
                client = await WebRTCService.get_http_client()
                response = None
                
                # 1. Query MediaMTX WHEP sessions
                try:
                    response = await client.get(f"{settings.mediamtx_api_url}/v3/webrtcsessions/list", timeout=5.0)
                except Exception:
                    response = None
                    
                if response is None or response.status_code != 200:
                    try:
                        response = await client.get(f"{settings.mediamtx_api_url}/v3/webrtcsessions", timeout=5.0)
                    except Exception:
                        response = None
                
                # 2. Skip checks if MediaMTX queries fail (prevents total flush on transient network blips)
                if response is None or response.status_code != 200:
                    break
                
                # 3. Parse active sessions correctly
                data = response.json()
                items = data.get("items", {})
                active_mediamtx_ids = set()
                
                if isinstance(items, dict):
                    active_mediamtx_ids = set(items.keys())
                elif isinstance(items, list):
                    active_mediamtx_ids = {item.get("id") for item in items if isinstance(item, dict) and "id" in item}
 
                # 4. Prune dead sessions from DB and Redis
                stmt = select(WebRTCSession).where(WebRTCSession.status == "ACTIVE")
                res = await db_session.execute(stmt)
                active_sessions = res.scalars().all()
 
                for db_s in active_sessions:
                    if db_s.session_id not in active_mediamtx_ids:
                        print(f"[worker] Session cleanup detected dead session: {db_s.session_id}. Evicting.")
                        await SessionRegistry.close_session(db_s.session_id, db_session)
                break
            
        except Exception as e:
            print(f"[worker] Session cleanup loop error: {e}")
        
        await asyncio.sleep(10)
