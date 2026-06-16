import re
from datetime import datetime
from .config import settings

class PlaybackRecoveryProvider:
    """
    Interface/base class for manufacturer-specific playback recovery URL builder.
    """
    def build_playback_url(self, stream, start_ts: float, end_ts: float) -> str:
        raise NotImplementedError("Subclasses must implement build_playback_url")

class GenericProvider(PlaybackRecoveryProvider):
    """
    Standard RTSP playback provider using settings.recovery_rtsp_template
    with ISO 8601 timestamps.
    """
    def build_playback_url(self, stream, start_ts: float, end_ts: float) -> str:
        base_rtsp = stream.stream_url.strip()
        dt_start = datetime.fromtimestamp(start_ts)
        dt_end = datetime.fromtimestamp(end_ts)

        start_iso = dt_start.strftime("%Y%m%dT%H%M%SZ")
        end_iso = dt_end.strftime("%Y%m%dT%H%M%SZ")
        start_time_local = dt_start.strftime("%Y_%m_%d_%H_%M_%S")
        end_time_local = dt_end.strftime("%Y_%m_%d_%H_%M_%S")

        return settings.recovery_rtsp_template.format(
            rtsp_url=base_rtsp,
            start_iso=start_iso,
            end_iso=end_iso,
            start_time_local=start_time_local,
            end_time_local=end_time_local
        )

class UNVProvider(PlaybackRecoveryProvider):
    """
    Uniview/UNV specific RTSP playback recovery URL builder.
    Format: rtsp://[creds]@[host]:[port]/c[channel]/b[start_ts]/e[end_ts]/replay/
    """
    def build_playback_url(self, stream, start_ts: float, end_ts: float) -> str:
        base_rtsp = stream.stream_url.strip()
        
        # 1. Parse prefix (creds, ip, port)
        prefix_match = re.match(r'^(rtsp[s]?://[^/]+)', base_rtsp)
        prefix = prefix_match.group(1) if prefix_match else base_rtsp

        # 2. Parse channel number (e.g., c1, c2)
        channel = "1"
        channel_match = (
            re.search(r'/[cC](\d+)\b', base_rtsp) or
            re.search(r'channel_id=(\d+)', base_rtsp) or
            re.search(r'channel=(\d+)', base_rtsp)
        )
        if channel_match:
            channel = channel_match.group(1)

        # Convert timestamps to integer epoch seconds
        b_time = int(start_ts)
        e_time = int(end_ts)

        return f"{prefix}/c{channel}/b{b_time}/e{e_time}/replay/"

class HikvisionProvider(PlaybackRecoveryProvider):
    def build_playback_url(self, stream, start_ts: float, end_ts: float) -> str:
        raise NotImplementedError("Hikvision playback recovery is not implemented yet")

class DahuaProvider(PlaybackRecoveryProvider):
    def build_playback_url(self, stream, start_ts: float, end_ts: float) -> str:
        raise NotImplementedError("Dahua playback recovery is not implemented yet")

class AxisProvider(PlaybackRecoveryProvider):
    def build_playback_url(self, stream, start_ts: float, end_ts: float) -> str:
        raise NotImplementedError("Axis playback recovery is not implemented yet")

class HanwhaProvider(PlaybackRecoveryProvider):
    def build_playback_url(self, stream, start_ts: float, end_ts: float) -> str:
        raise NotImplementedError("Hanwha playback recovery is not implemented yet")


class EdgePlaybackProvider:
    """
    Future edge-playback provider to retrieve footage directly from edge devices.
    """
    def request_recording(self, stream_id: str, start_ts: float, end_ts: float) -> None:
        raise NotImplementedError("EdgePlaybackProvider.request_recording is not implemented yet")


def get_playback_recovery_provider(make: str | None) -> PlaybackRecoveryProvider:
    """
    Factory to select the appropriate PlaybackRecoveryProvider based on the camera make.
    Only synchronization values from the Video Server API are trusted.
    """
    if not make:
        print("[recovery] Camera make missing from Video Server API. Using GenericProvider.")
        return GenericProvider()

    # Exact matches based on synced data, no lowercase conversion or normalization
    if make in ("UNV", "Uniview"):
        return UNVProvider()
    elif make == "Hikvision":
        return HikvisionProvider()
    elif make == "Dahua":
        return DahuaProvider()
    elif make == "Axis":
        return AxisProvider()
    elif make == "Hanwha":
        return HanwhaProvider()
    else:
        print(f"[recovery] Unknown camera make '{make}' from Video Server API. Using GenericProvider.")
        return GenericProvider()
