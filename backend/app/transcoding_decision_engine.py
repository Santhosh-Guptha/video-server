import asyncio
from typing import Optional, Dict, Any
from .policy_loader import PolicyLoader

class TranscodingDecisionEngine:
    # Cached status of cloud transcoding platform
    _cloud_healthy: bool = True
    _lock = asyncio.Lock()

    @classmethod
    async def set_cloud_health(cls, healthy: bool):
        """Sets the cloud platform health status in memory (called by background health pinger)."""
        async with cls._lock:
            cls._cloud_healthy = healthy

    @classmethod
    async def get_cloud_health(cls) -> bool:
        """Instantly returns the cached cloud health status without making network calls."""
        async with cls._lock:
            return cls._cloud_healthy

    @classmethod
    async def determine_route(
        cls,
        codec: str,
        client_profile: Dict[str, Any],
        admin_force_h264: bool = False
    ) -> str:
        """
        Calculates the transcoding route instantly from cached status.
        Returns: "direct" | "cloud" | "local"
        """
        # Rule 1: Never transcode H.264
        if codec.upper() == "H264":
            return "direct"

        # Rule 2: If browser/client capability profile natively supports H265, stream directly
        supports_h265 = client_profile.get("supports_h265", False)
        
        # Check override policy settings
        transcode_override = PolicyLoader.get("transcoder_policy.yaml", "force_h264_transcode", admin_force_h264)
        
        if supports_h265 and not transcode_override:
            return "direct"

        # Rule 3: Client needs transcoding (supports_h265 == False or override == True)
        # Check cluster settings to see if cloud is enabled
        cloud_enabled = PolicyLoader.get("cluster_policy.yaml", "cloud_enabled", True)
        if not cloud_enabled:
            return "local"

        # Check cached health status instantly
        cloud_healthy = await cls.get_cloud_health()
        if cloud_healthy:
            return "cloud"
        else:
            print("[decision_engine] Cloud transcoder is unhealthy/offline. Selecting local fallback.")
            return "local"
