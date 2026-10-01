import hashlib
import json
import os
import httpx
from fastapi import HTTPException
from .config import settings

async def fetch_upstream_cameras():
    backup_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backup_cameras_" + hashlib.sha256(settings.upstream_camera_api_url.encode()).hexdigest()[:16] + ".json")
    try:
        async with httpx.AsyncClient(
            timeout=settings.upstream_timeout_seconds,
            verify=False
        ) as client:
            response = await client.get(settings.upstream_camera_api_url)
            response.raise_for_status()
            data = response.json()
            print(f"[upstream] Successfully fetched cameras from upstream API: {settings.upstream_camera_api_url}")

            # Save a backup of the successfully fetched configuration
            try:
                with open(backup_path, "w") as f:
                    json.dump(data, f)
                print(f"[upstream] Saved backup configuration to {backup_path}")
            except Exception as backup_err:
                print(f"[upstream] Failed to save backup configuration: {backup_err}")

            return data
    except Exception as e:
        print(f"[upstream] Failed to fetch from upstream API ({settings.upstream_camera_api_url}): {e}. Falling back to cached backup...")
        if os.path.exists(backup_path):
            try:
                with open(backup_path, "r") as f:
                    data = json.load(f)
                print(f"[upstream] Loaded cached backup configuration from {backup_path}")
                return data
            except Exception as backup_load_err:
                print(f"[upstream] Failed to load backup configuration file: {backup_load_err}")
        raise HTTPException(status_code=503, detail="Camera configuration service is unreachable and no cached configuration is available. Existing cameras were preserved; retry Sync Cameras when the upstream service returns.")
