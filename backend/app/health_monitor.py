import asyncio
import socket
import httpx
from datetime import datetime
from sqlalchemy import select
from .config import settings
from .db import get_session
from .models import StreamRegistry, StreamState, CameraStream
from .stream_manager import stream_manager
from .redis_viewer_tracker import RedisViewerTracker

NODE_URLS = {
    "node1": settings.mediamtx_api_url,
}

async def check_coturn_health() -> bool:
    """Checks coturn health by attempting to open a TCP connection to its port."""
    try:
        host = "localhost"
        port = 3478
        if settings.turn_server_url:
            parts = settings.turn_server_url.replace("turn:", "").split(":")
            host = parts[0]
            if len(parts) > 1:
                port = int(parts[1])
        
        loop = asyncio.get_event_loop()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        await loop.run_in_executor(None, s.connect, (host, port))
        s.close()
        return True
    except Exception:
        return False

async def check_node_health(node_name: str, api_url: str) -> bool:
    """Checks a MediaMTX node health by calling its API endpoint."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{api_url}/v3/config/paths/list", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

async def health_monitor_loop():
    """Periodically checks the health of coturn and MediaMTX nodes, handling node failures and reassignments."""
    print("[health_monitor] Starting node and coturn health watchdog...")
    while True:
        try:
            # 1. Check coturn health
            coturn_ok = await check_coturn_health()
            if not coturn_ok:
                print("[health_monitor] WARNING: coturn (TURN server) is offline or unreachable on port 3478!")
            else:
                await RedisViewerTracker.set_stream_health("coturn", "ONLINE")
            
            # 2. Check each configured MediaMTX node
            node_status = {}
            for name, url in NODE_URLS.items():
                ok = await check_node_health(name, url)
                node_status[name] = ok
                # Update health cache
                await RedisViewerTracker.set_stream_health(f"node:{name}", "ONLINE" if ok else "OFFLINE", None if ok else "Node unreachable")
                if not ok:
                    print(f"[health_monitor] MediaMTX node '{name}' is offline!")

            # 3. Handle offline nodes (Failover / Recovery)
            async for db_session in get_session():
                for node_name, is_online in node_status.items():
                    if not is_online:
                        # Find streams registered on this offline node
                        stmt = select(StreamRegistry).where(
                            StreamRegistry.mediamtx_node == node_name,
                            StreamRegistry.status != "RECOVERING"
                        )
                        res = await db_session.execute(stmt)
                        registry_entries = res.scalars().all()
                        
                        if registry_entries:
                            print(f"[health_monitor] Node '{node_name}' is offline. Marking {len(registry_entries)} streams as RECOVERING.")
                            
                            # Find healthy nodes
                            healthy_nodes = [name for name, ok in node_status.items() if ok]
                            
                            for entry in registry_entries:
                                entry.status = "RECOVERING"
                                entry.last_seen = datetime.utcnow()
                                await RedisViewerTracker.set_stream_health(entry.stream_id, "RECOVERING", f"Node {node_name} offline")
                                
                                # If there is a healthy node to failover to, reassign it
                                if healthy_nodes:
                                    target_node = healthy_nodes[0]
                                    print(f"[health_monitor] Reassigning stream {entry.stream_id} from {node_name} to {target_node}")
                                    entry.mediamtx_node = target_node
                                    entry.status = "REGISTERED"
                                    
                                    # Update the camera stream status in db
                                    camera_stream_stmt = select(CameraStream).where(CameraStream.stream_id == entry.stream_id)
                                    cs_res = await db_session.execute(camera_stream_stmt)
                                    camera_stream = cs_res.scalar_one_or_none()
                                    if camera_stream:
                                        await stream_manager.set_stream_state(db_session, camera_stream, StreamState.RECOVERING, f"Failover from {node_name} to {target_node}")
                                        # Force add_stream to recreate the path configuration on the new node
                                        await stream_manager.add_stream(db_session, camera_stream)
                                else:
                                    # No healthy nodes available, update status to OFFLINE
                                    camera_stream_stmt = select(CameraStream).where(CameraStream.stream_id == entry.stream_id)
                                    cs_res = await db_session.execute(camera_stream_stmt)
                                    camera_stream = cs_res.scalar_one_or_none()
                                    if camera_stream:
                                        await stream_manager.set_stream_state(db_session, camera_stream, StreamState.OFFLINE, f"Node {node_name} offline, no failover target available")
                            
                            await db_session.commit()
                            
        except Exception as e:
            print(f"[health_monitor] Error in health monitor loop: {e}")
            
        await asyncio.sleep(settings.scheduler_interval_seconds)
