import re
import httpx
from .config import settings
from .stream_manager import _mtx_request

def double_escape_rtsp_url(url: str) -> str:
    if not url or not url.startswith(("rtsp://", "rtsps://", "rtmp://")):
        return url
    if "@" not in url:
        return url
    parts = url.split("://", 1)
    if len(parts) < 2:
        return url
    scheme, rest = parts
    user_host = rest.rsplit("@", 1)
    if len(user_host) < 2:
        return url
    userinfo, host = user_host
    escaped_userinfo = re.sub(r'%([0-9a-fA-F]{2})', r'%25\1', userinfo)
    return f"{scheme}://{escaped_userinfo}@{host}"

class MediaMTXClient:
    def __init__(self, api_url: str = settings.mediamtx_api_url):
        self.api_url = api_url

    async def get_paths(self) -> set[str]:
        """Queries the active configured paths from MediaMTX."""
        try:
            resp = await _mtx_request("GET", f"{self.api_url}/v3/config/paths/list?page=0&itemsPerPage=10000", timeout=5.0)
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
        try:
            resp = await _mtx_request("GET", f"{self.api_url}/v3/streams/list", timeout=5.0)
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
        payload = {
            "source": source_url,
            "sourceProtocol": "tcp",
            "sourceOnDemand": False if source_url == "publisher" else source_on_demand,
            "record": True,
            "runOnDemand": "",
            "runOnUnDemand": ""
        }
        try:
            resp = await _mtx_request("POST", f"{self.api_url}/v3/config/paths/add/{path_name}", json=payload, timeout=5.0)
            if resp.status_code in (200, 201):
                return True
            # If already exists, we attempt an edit update (via GET + PATCH/skip)
            if "already exists" in resp.text or resp.status_code == 400:
                get_resp = await _mtx_request("GET", f"{self.api_url}/v3/config/paths/get/{path_name}", timeout=5.0)
                if get_resp.status_code == 200:
                    existing = get_resp.json()
                    def normalize_url(u):
                        if not u: return ""
                        return u.replace("%25", "%").replace("&amp;", "&")
                    
                    existing_src = normalize_url(existing.get("source", ""))
                    desired_src = normalize_url(payload.get("source", ""))
                    
                    if (existing_src == desired_src and
                        existing.get("sourceProtocol") == payload.get("sourceProtocol") and
                        existing.get("sourceOnDemand") == payload.get("sourceOnDemand") and
                        existing.get("record") == payload.get("record") and
                        existing.get("runOnDemand", "") == payload.get("runOnDemand", "") and
                        existing.get("runOnUnDemand", "") == payload.get("runOnUnDemand", "")):
                        return True
                    
                    patch_resp = await _mtx_request("PATCH", f"{self.api_url}/v3/config/paths/patch/{path_name}", json=payload, timeout=5.0)
                    if patch_resp.status_code in (200, 201):
                        return True
                
                # Fallback to delete & add if GET/PATCH failed
                await _mtx_request("DELETE", f"{self.api_url}/v3/config/paths/delete/{path_name}", timeout=5.0)
                resp = await _mtx_request("POST", f"{self.api_url}/v3/config/paths/add/{path_name}", json=payload, timeout=5.0)
                return resp.status_code in (200, 201)
        except Exception as e:
            print(f"[mediamtx_client] Error adding path {path_name}: {e}")
        return False

    async def delete_path(self, path_name: str) -> bool:
        """Deletes a path configuration from MediaMTX."""
        try:
            resp = await _mtx_request("DELETE", f"{self.api_url}/v3/config/paths/delete/{path_name}", timeout=5.0)
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"[mediamtx_client] Error deleting path {path_name}: {e}")
        return False

mediamtx_client = MediaMTXClient()
