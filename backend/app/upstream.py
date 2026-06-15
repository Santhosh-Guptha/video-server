import json
import os
import httpx
from .config import settings

async def fetch_upstream_cameras():
    try:
        async with httpx.AsyncClient(
            timeout=settings.upstream_timeout_seconds,
            verify=False
        ) as client:
            response = await client.get(settings.upstream_camera_api_url)
            response.raise_for_status()
            print(f"[upstream] Successfully fetched cameras from upstream API: {settings.upstream_camera_api_url}")
            return response.json()
    except Exception as e:
        print(f"[upstream] Failed to fetch from upstream API ({settings.upstream_camera_api_url}): {e}. Falling back to local sample_cameras.json.")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        sample_path = os.path.join(base_dir, "sample_cameras.json")
        try:
            with open(sample_path, "r") as f:
                return json.load(f)
        except Exception as file_err:
            print(f"[upstream] Error loading sample_cameras.json: {file_err}")
            return []
