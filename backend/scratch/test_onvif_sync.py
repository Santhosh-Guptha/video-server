import os
import sys
import time
from onvif import ONVIFCamera
from zeep.transports import Transport
from urllib.parse import urlparse, urlunparse

def main():
    if len(sys.argv) < 6:
        print("Usage: python test_onvif_sync.py <ip> <port> <username> <password> <target_fps>")
        sys.stdout.flush()
        sys.exit(1)

    ip = sys.argv[1]
    port = int(sys.argv[2])
    username = sys.argv[3]
    password = sys.argv[4]
    target_fps = int(sys.argv[5])

    WSDL_DIR = "/opt/video-backend-venv/lib/python3.10/site-packages/wsdl"
    print(f"Connecting to camera {ip}:{port} over ONVIF...")
    sys.stdout.flush()

    transport = Transport(timeout=15.0, operation_timeout=15.0)
    try:
        cam = ONVIFCamera(ip, port, username, password, WSDL_DIR, transport=transport)
        
        # Rewrite xaddrs for NAT/port-forwarded setups
        for ns, xaddr in list(cam.xaddrs.items()):
            parsed = urlparse(xaddr)
            cam.xaddrs[ns] = urlunparse(parsed._replace(netloc=f"{ip}:{port}"))

        media = cam.create_media_service()
        profiles = media.GetProfiles()
        if not profiles:
            print("Error: No profiles found.")
            return

        # Use main profile
        profile = profiles[0]
        cfg = profile.VideoEncoderConfiguration
        if not cfg:
            print(f"Error: No VideoEncoderConfiguration on profile {profile.Name}")
            return

        old_fps = int(cfg.RateControl.FrameRateLimit)
        old_resolution = f"{cfg.Resolution.Width}x{cfg.Resolution.Height}"
        print(f"Successfully connected to profile: {profile.Name}")
        print(f"Current Settings: FPS={old_fps}, Resolution={old_resolution}")
        sys.stdout.flush()

        if old_fps == target_fps:
            print(f"Camera is already configured with target FPS: {target_fps}")
            return

        print(f"Applying new FPS setting: {target_fps}...")
        sys.stdout.flush()

        cfg.RateControl.FrameRateLimit = target_fps
        media.SetVideoEncoderConfiguration({
            'Configuration': cfg,
            'ForcePersistence': True
        })
        print("SetVideoEncoderConfiguration called successfully! Waiting 3 seconds for camera to apply...")
        sys.stdout.flush()
        time.sleep(3)

        # Fetch settings again to verify
        print("Re-fetching configuration to verify settings...")
        sys.stdout.flush()
        profiles_after = media.GetProfiles()
        cfg_after = profiles_after[0].VideoEncoderConfiguration
        new_fps = int(cfg_after.RateControl.FrameRateLimit)
        print(f"Updated Settings on Camera: FPS={new_fps}")
        sys.stdout.flush()

        if new_fps == target_fps:
            print("SUCCESS: Camera successfully accepted and applied the FPS configuration!")
        else:
            print(f"FAILED: Target FPS was {target_fps}, but camera reports {new_fps}")
        sys.stdout.flush()

    except Exception as e:
        print(f"Connection/Configuration failed: {e}")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
