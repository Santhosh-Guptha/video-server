import sys
sys.path.append('/app')
import asyncio
import socket
from urllib.parse import urlparse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.db import SessionLocal
from app.models import Camera

def check_connection(host, port, timeout=1.0):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, int(port)))
        sock.close()
        return result == 0
    except Exception:
        return False

async def main():
    async with SessionLocal() as session:
        # Fetch all cameras sorted alphabetically by name
        res = await session.execute(
            select(Camera)
            .where(Camera.active == True)
            .options(selectinload(Camera.streams))
            .order_by(Camera.name.asc())
        )
        cameras = res.scalars().all()
        print(f"Total active cameras in DB: {len(cameras)}")
        
        online_count = 0
        for idx, cam in enumerate(cameras):
            for s in cam.streams:
                url = s.stream_url or ""
                if not url:
                    continue
                try:
                    # Clean up URL format for urlparse
                    if not url.startswith("rtsp://") and not url.startswith("rtsps://") and not url.startswith("rtmp://"):
                        url_parsed = "rtsp://" + url
                    else:
                        url_parsed = url
                        
                    parsed = urlparse(url_parsed)
                    host = parsed.hostname
                    port = parsed.port or 554
                    
                    if host:
                        is_online = check_connection(host, port)
                        if is_online:
                            online_count += 1
                            page = (idx // 12) + 1
                            print(f"[{online_count}] Camera: '{cam.name}' | Stream: {s.stream_id} | Host: {host}:{port} | Alphabetical Index: {idx} | Page: {page}")
                            break
                except Exception as e:
                    print(f"Failed parsing {url}: {e}")

asyncio.run(main())
