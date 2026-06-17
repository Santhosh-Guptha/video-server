import httpx
from .config import settings

class MediaMTXClient:
    def __init__(self, api_url: str = settings.mediamtx_api_url):
        self.api_url = api_url

    async def get_paths(self) -> set[str]:
        """Queries the active configured paths from MediaMTX."""
        url = f"{self.api_url}/v3/config/paths/list"
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json().get("items", {})
                    if isinstance(data, dict):
                        return set(data.keys())
                    elif isinstance(data, list):
                        return {item.get("name") for item in data if isinstance(item, dict) and "name" in item}
            except Exception as e:
                print(f"[mediamtx_client] Error listing config paths: {e}")
        return set()

    async def get_active_streams(self) -> dict:
        """Queries the active streaming feeds from MediaMTX."""
        url = f"{self.api_url}/v3/streams/list"
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json().get("items", {})
                    streams = {}
                    if isinstance(data, dict):
                        streams = data
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and "name" in item:
                                streams[item["name"]] = item
                    return streams
            except Exception as e:
                print(f"[mediamtx_client] Error listing active streams: {e}")
        return {}

    async def add_path(self, path_name: str, source_url: str, source_on_demand: bool = False) -> bool:
        """Adds a path configuration on MediaMTX."""
        url = f"{self.api_url}/v3/config/paths/add/{path_name}"
        payload = {
            "source": source_url,
            "sourceOnDemand": False if source_url == "publisher" else source_on_demand,
            "record": True,
            "runOnDemand": "",
            "runOnUnDemand": ""
        }
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json=payload, timeout=5.0)
                if resp.status_code in (200, 201):
                    return True
                # If already exists, we attempt an edit update (via delete & re-add)
                if "already exists" in resp.text or resp.status_code == 400:
                    delete_url = f"{self.api_url}/v3/config/paths/delete/{path_name}"
                    await client.delete(delete_url, timeout=5.0)
                    resp = await client.post(url, json=payload, timeout=5.0)
                    return resp.status_code in (200, 201)
            except Exception as e:
                print(f"[mediamtx_client] Error adding path {path_name}: {e}")
        return False

    async def delete_path(self, path_name: str) -> bool:
        """Deletes a path configuration from MediaMTX."""
        url = f"{self.api_url}/v3/config/paths/delete/{path_name}"
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.delete(url, timeout=5.0)
                return resp.status_code in (200, 204)
            except Exception as e:
                print(f"[mediamtx_client] Error deleting path {path_name}: {e}")
        return False

mediamtx_client = MediaMTXClient()
