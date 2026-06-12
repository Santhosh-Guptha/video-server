import abc
import httpx
from .config import settings

class RecordingProvider(abc.ABC):
    @abc.abstractmethod
    async def start_recording(self, stream_id: str) -> None:
        """Enable recording for the specified stream_id."""
        pass

    @abc.abstractmethod
    async def stop_recording(self, stream_id: str) -> None:
        """Disable recording for the specified stream_id."""
        pass

    @abc.abstractmethod
    async def get_recording_status(self, stream_id: str) -> bool:
        """Get the current recording configuration status for the specified stream_id."""
        pass

class MediaMTXRecordingProvider(RecordingProvider):
    def __init__(self, api_url: str = settings.mediamtx_api_url):
        self.api_url = api_url

    async def start_recording(self, stream_id: str) -> None:
        async with httpx.AsyncClient() as client:
            url = f"{self.api_url}/v3/config/paths/edit/{stream_id}"
            try:
                response = await client.post(url, json={"record": True})
                if response.status_code not in (200, 201):
                    print(f"[recording] Failed to start MediaMTX recording for {stream_id}: {response.text}")
            except Exception as e:
                print(f"[recording] Connection error starting MediaMTX recording for {stream_id}: {e}")

    async def stop_recording(self, stream_id: str) -> None:
        async with httpx.AsyncClient() as client:
            url = f"{self.api_url}/v3/config/paths/edit/{stream_id}"
            try:
                response = await client.post(url, json={"record": False})
                if response.status_code not in (200, 201):
                    print(f"[recording] Failed to stop MediaMTX recording for {stream_id}: {response.text}")
            except Exception as e:
                print(f"[recording] Connection error stopping MediaMTX recording for {stream_id}: {e}")

    async def get_recording_status(self, stream_id: str) -> bool:
        async with httpx.AsyncClient() as client:
            url = f"{self.api_url}/v3/config/paths/get/{stream_id}"
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("record", False)
            except Exception as e:
                print(f"[recording] Connection error checking MediaMTX recording status for {stream_id}: {e}")
        return False

# Global provider instance
recording_provider = MediaMTXRecordingProvider()
