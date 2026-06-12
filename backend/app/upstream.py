import httpx
from .config import settings

async def fetch_upstream_cameras():
    async with httpx.AsyncClient(
        timeout=30,
        verify=False
    ) as client:

        response = await client.get(
            settings.upstream_camera_api_url
        )

        response.raise_for_status()

        return response.json()
