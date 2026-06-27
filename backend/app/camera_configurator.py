import os
import re
import asyncio
from urllib.parse import urlparse
import onvif
from onvif import ONVIFCamera

# Set WSDL directory from onvif package with fallback to site-packages root
package_dir = os.path.dirname(onvif.__file__)
WSDL_DIR = os.path.join(package_dir, 'wsdl')
if not os.path.exists(os.path.join(WSDL_DIR, 'devicemgmt.wsdl')):
    WSDL_DIR = os.path.join(os.path.dirname(package_dir), 'wsdl')


def parse_camera_ip(rtsp_url: str) -> str:
    """Parses the hostname/IP from the camera RTSP URL."""
    url_to_parse = rtsp_url.strip()
    if not url_to_parse.startswith(("rtsp://", "rtsps://", "rtmp://", "http://", "https://")):
        url_to_parse = f"rtsp://{url_to_parse}"
    
    try:
        parsed = urlparse(url_to_parse)
        hostname = parsed.hostname
        if hostname:
            return hostname
    except Exception:
        pass
        
    # Regex fallback for IP addresses or domains
    match = re.search(r'@?([a-zA-Z0-9.-]+)(?::\d+)?', rtsp_url)
    if match:
        return match.group(1)
    return ""

async def get_onvif_camera_client(ip: str, username: str, password: str, override_port: int | None = None) -> tuple[ONVIFCamera, int]:
    """
    Tries to connect to the camera on common ONVIF ports.
    If override_port is provided, it is tried first.
    Returns the ONVIFCamera client and the successful port.
    """
    common_ports = [80, 8899, 8000, 5000, 8081]
    if override_port:
        if override_port in common_ports:
            common_ports.remove(override_port)
        common_ports = [override_port] + common_ports

    last_exception = None

    for port in common_ports:
        try:
            # We wrap the blocking zeep initialization in an executor with timeout
            def init_cam():
                from zeep.transports import Transport
                from urllib.parse import urlparse, urlunparse
                
                # Set timeouts suitable for high-latency cellular connections (which can reach 4-5s ping)
                transport = Transport(timeout=20.0, operation_timeout=20.0)
                cam = ONVIFCamera(ip, port, username, password, WSDL_DIR, transport=transport)
                
                # Rewrite xaddrs to use the public IP/port (vital for NAT/port-forwarded cameras)
                for ns, xaddr in list(cam.xaddrs.items()):
                    try:
                        parsed_xaddr = urlparse(xaddr)
                        new_netloc = f"{ip}:{port}"
                        new_xaddr = urlunparse(parsed_xaddr._replace(netloc=new_netloc))
                        cam.xaddrs[ns] = new_xaddr
                    except Exception:
                        pass
                
                # Test call to verify connection and auth
                media = cam.create_media_service()
                media.GetProfiles()
                return cam

            cam = await asyncio.wait_for(
                asyncio.to_thread(init_cam),
                timeout=65.0
            )
            return cam, port
        except Exception as e:
            last_exception = e
            continue

    err_msg = f"{type(last_exception).__name__}: {last_exception}" if last_exception else "Unknown error"
    raise Exception(f"Failed to connect to ONVIF service on ports {common_ports}. Last error: {err_msg}")


async def apply_camera_configuration(
    rtsp_url: str,
    username: str,
    password: str,
    stream_type: str,
    target_width: int,
    target_height: int,
    target_fps: int,
    target_bitrate_kbps: int | None = None,
    onvif_port: int | None = None
) -> dict:
    """
    Connects to the physical camera via ONVIF, checks the current configuration,
    and applies target changes if they differ.
    """
    ip = parse_camera_ip(rtsp_url)
    if not ip:
        raise Exception(f"Could not parse IP address from RTSP URL: {rtsp_url}")

    # Connect to camera
    cam, port = await get_onvif_camera_client(ip, username, password, override_port=onvif_port)
    
    # Run media queries in a thread pool since they make blocking SOAP requests
    def configure_process():
        media = cam.create_media_service()
        profiles = media.GetProfiles()
        if not profiles:
            raise Exception("No ONVIF profiles found on this camera.")

        # Match target profile
        target_profile = None
        stream_type_upper = stream_type.upper()
        
        if stream_type_upper in ("MAIN", "HD"):
            target_profile = profiles[0]
        else:
            # Search for sub/normal profile
            for p in profiles:
                if any(x in p.Name.lower() for x in ("sub", "normal", "substream", "mobile")):
                    target_profile = p
                    break
            if not target_profile and len(profiles) > 1:
                target_profile = profiles[1]
            elif not target_profile:
                target_profile = profiles[0]

        cfg = target_profile.VideoEncoderConfiguration
        if not cfg:
            raise Exception(f"No VideoEncoderConfiguration found for profile: {target_profile.Name}")

        # Current values
        current_width = int(cfg.Resolution.Width)
        current_height = int(cfg.Resolution.Height)
        current_fps = int(cfg.RateControl.FrameRateLimit)
        current_bitrate = int(cfg.RateControl.BitrateLimit)

        # Check if changes are needed
        width_diff = current_width != target_width
        height_diff = current_height != target_height
        fps_diff = current_fps != target_fps
        
        bitrate_diff = False
        if target_bitrate_kbps is not None:
            # Cameras might return bitrate in bps or kbps, let's normalize check
            if current_bitrate > 100000: # looks like bps
                bitrate_diff = abs(current_bitrate - (target_bitrate_kbps * 1000)) > 50000
            else: # looks like kbps
                bitrate_diff = abs(current_bitrate - target_bitrate_kbps) > 50

        if not (width_diff or height_diff or fps_diff or bitrate_diff):
            return {
                "status": "already_configured",
                "ip": ip,
                "port": port,
                "profile": target_profile.Name,
                "fps": current_fps,
                "resolution": f"{current_width}x{current_height}",
                "bitrate": current_bitrate
            }

        # Apply modifications
        cfg.Resolution.Width = target_width
        cfg.Resolution.Height = target_height
        cfg.RateControl.FrameRateLimit = target_fps
        
        if target_bitrate_kbps is not None:
            if current_bitrate > 100000:
                cfg.RateControl.BitrateLimit = target_bitrate_kbps * 1000
            else:
                cfg.RateControl.BitrateLimit = target_bitrate_kbps

        # Write changes
        media.SetVideoEncoderConfiguration({
            'Configuration': cfg,
            'ForcePersistence': True
        })

        return {
            "status": "configured",
            "ip": ip,
            "port": port,
            "profile": target_profile.Name,
            "old_settings": {
                "fps": current_fps,
                "resolution": f"{current_width}x{current_height}",
                "bitrate": current_bitrate
            },
            "new_settings": {
                "fps": target_fps,
                "resolution": f"{target_width}x{target_height}",
                "bitrate": target_bitrate_kbps
            }
        }

    return await asyncio.to_thread(configure_process)
