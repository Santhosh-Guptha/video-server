import abc
import httpx
from .config import settings

class RecordingProvider(abc.ABC):
    @abc.abstractmethod
    async def start_recording(self, stream_id: str, profile_type=None) -> None:
        """Enable recording for the specified stream_id.
        
        Args:
            stream_id: The stream identifier in MediaMTX.
            profile_type: Optional ProfileType — used to enforce HD-only policy.
                          If RECORD_HD_ONLY is True and profile_type is not MAIN,
                          recording will be skipped.
        """
        pass

    @abc.abstractmethod
    async def stop_recording(self, stream_id: str, profile_type=None) -> None:
        """Disable recording for the specified stream_id."""
        pass

    @abc.abstractmethod
    async def get_recording_status(self, stream_id: str) -> bool:
        """Get the current recording configuration status for the specified stream_id."""
        pass

class MediaMTXRecordingProvider(RecordingProvider):
    def __init__(self, api_url: str = settings.mediamtx_api_url):
        self.api_url = api_url

    async def start_recording(self, stream_id: str, profile_type=None) -> None:
        """
        Enable recording for the specified stream_id.

        Respects the active vms_policy recording configuration:
          - RECORD_HD_ONLY=True  → only MAIN/HD profile streams are recorded
          - RECORD_NORMAL=True   → also records SUB/NORMAL streams
          - RECORD_MOBILE=True   → also records MOBILE streams

        Non-eligible streams are silently skipped (they remain available for live viewing).
        """
        from .vms_policy import should_record_profile
        from .models import ProfileType
        if profile_type is not None:
            profile_val = profile_type.value if hasattr(profile_type, 'value') else str(profile_type)
            if not should_record_profile(profile_val):
                print(f"[recording] Policy: skipping recording for stream {stream_id} (profile={profile_val} not in allowed recording profiles)")
                return

        async with httpx.AsyncClient() as client:
            get_url = f"{self.api_url}/v3/config/paths/get/{stream_id}"
            try:
                get_resp = await client.get(get_url)
                if get_resp.status_code == 200:
                    config = get_resp.json()
                    if config.get("record") is True:
                        print(f"[recording] Stream {stream_id} is already recording. Skipping.")
                        return
                
                # PATCH
                patch_url = f"{self.api_url}/v3/config/paths/patch/{stream_id}"
                patch_resp = await client.patch(patch_url, json={"record": True})
                if patch_resp.status_code in (200, 201):
                    return
                print(f"[recording] Failed to patch path on start_recording for {stream_id}: {patch_resp.text}")
            except Exception as e:
                print(f"[recording] Connection error starting MediaMTX recording for {stream_id}: {e}")

    async def stop_recording(self, stream_id: str, profile_type=None) -> None:
        """Disable recording. profile_type accepted for API consistency but not enforced — always safe to stop."""
        async with httpx.AsyncClient() as client:
            get_url = f"{self.api_url}/v3/config/paths/get/{stream_id}"
            try:
                get_resp = await client.get(get_url)
                if get_resp.status_code == 200:
                    config = get_resp.json()
                    if config.get("record") is False:
                        print(f"[recording] Stream {stream_id} is already not recording. Skipping.")
                        return
                
                # PATCH
                patch_url = f"{self.api_url}/v3/config/paths/patch/{stream_id}"
                patch_resp = await client.patch(patch_url, json={"record": False})
                if patch_resp.status_code in (200, 201):
                    return
                print(f"[recording] Failed to patch path on stop_recording for {stream_id}: {patch_resp.text}")
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
