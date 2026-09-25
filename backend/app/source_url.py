"""Validate camera source URLs before handing them to MediaMTX or FFmpeg."""

import ipaddress
from urllib.parse import urlsplit


def valid_camera_source(url: str | None) -> bool:
    if not url or not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        if parts.scheme.lower() not in {"rtsp", "rtsps", "rtmp"} or not host:
            return False
        if parts.port is not None and not 1 <= parts.port <= 65535:
            return False
        if host.replace(".", "").isdigit():
            ipaddress.IPv4Address(host)
        return True
    except (ValueError, TypeError):
        return False