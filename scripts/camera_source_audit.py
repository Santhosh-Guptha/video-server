#!/usr/bin/env python3
"""List invalid local camera sources without printing URL credentials."""

import ipaddress
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "backend" / "data" / "develop.db"


def issue(url):
    if not url:
        return "missing URL"
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        if parts.scheme.lower() not in {"rtsp", "rtsps", "rtmp"}:
            return "unsupported scheme"
        if not host:
            return "missing host"
        if parts.port is not None and not 1 <= parts.port <= 65535:
            return "invalid port"
        if host.replace(".", "").isdigit():
            ipaddress.IPv4Address(host)
    except (ValueError, TypeError):
        return "malformed host or port"
    return None


def main():
    if not DB.exists():
        raise SystemExit(f"Database not found: {DB}")
    with sqlite3.connect(DB) as connection:
        rows = connection.execute("SELECT stream_id, stream_url FROM camera_streams ORDER BY stream_id")
        problems = [{"stream_id": stream_id, "issue": problem} for stream_id, url in rows if (problem := issue(url))]
    print(json.dumps({"invalid_count": len(problems), "streams": problems}, indent=2))


if __name__ == "__main__":
    main()