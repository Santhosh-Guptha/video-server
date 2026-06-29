import os
import re
import base64
import hashlib
import datetime
import xml.etree.ElementTree as ET
from typing import Optional, Dict, List, Tuple
import httpx

# System logger reference
import logging
logger = logging.getLogger("camera_video_platform")

def parse_rtsp_url(rtsp_url: str) -> Optional[Tuple[str, str, str]]:
    """
    Parses RTSP url to extract host (IP), username, and password.
    Splits by last '@' and first ':' to handle password special characters.
    """
    if not rtsp_url:
        return None
    try:
        url_part = rtsp_url
        if rtsp_url.lower().startswith("rtsp://"):
            url_part = rtsp_url[7:]
        
        if "@" in url_part:
            creds_part, host_part = url_part.rsplit("@", 1)
            if ":" in creds_part:
                username, password = creds_part.split(":", 1)
            else:
                username = creds_part
                password = ""
        else:
            username = ""
            password = ""
            host_part = url_part
            
        host_only = host_part.split("/", 1)[0]
        if ":" in host_only:
            host, _ = host_only.split(":", 1)
        else:
            host = host_only
            
        return host, username, password
    except Exception as e:
        logger.error(f"[ONVIFClient] Failed to parse RTSP URL: {rtsp_url}. Error: {e}")
        return None

class CameraConfigClient:
    """
    Unified client to communicate with IP cameras for configuration updates.
    Attempts ONVIF SOAP requests first, and falls back to vendor APIs (Hikvision ISAPI / Dahua CGI).
    """
    def __init__(self, ip: str, username: str, password: str, base_url: Optional[str] = None):
        self.ip = ip
        self.username = username
        self.password = password
        
        # If user supplies full base URL (e.g. https://172.20.100.245)
        if base_url:
            self.base_url = base_url.rstrip('/')
        else:
            # Default fallback list (HTTPS first, then HTTP port 80, then 8899)
            self.base_url = f"https://{ip}"
            
    def _create_wsse_header(self) -> str:
        """
        Generates WS-Security UsernameToken header XML string with password digest.
        """
        nonce = os.urandom(16)
        created = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # SHA1 Digest = Base64( SHA-1( Nonce + Created + Password ) )
        sha1 = hashlib.sha1()
        sha1.update(nonce + created.encode('utf-8') + self.password.encode('utf-8'))
        digest = sha1.digest()
        
        nonce_b64 = base64.b64encode(nonce).decode('utf-8')
        digest_b64 = base64.b64encode(digest).decode('utf-8')
        
        return f"""<soap:Header>
  <Security soap:mustUnderstand="1" xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
    <UsernameToken>
      <Username>{self.username}</Username>
      <Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest_b64}</Password>
      <Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_b64}</Nonce>
      <Created>{created}</Created>
    </UsernameToken>
  </Security>
</soap:Header>"""

    async def _post_soap(self, url: str, action: str, body: str) -> str:
        """
        Sends an authenticated ONVIF SOAP request to the target URL.
        """
        header = self._create_wsse_header()
        envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" 
               xmlns:s="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
               xmlns:tds="http://www.onvif.org/ver10/device/wsdl" 
               xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
               xmlns:tt="http://www.onvif.org/ver10/schema">
  {header}
  <soap:Body>
    {body}
  </soap:Body>
</soap:Envelope>"""

        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8",
            "SOAPAction": action
        }
        
        # standard SSL verification disabled for local self-signed cameras
        async with httpx.AsyncClient(verify=False, timeout=12.0) as client:
            response = await client.post(url, content=envelope, headers=headers)
            response.raise_for_status()
            return response.text

    async def run_onvif_setup(self, width: Optional[int], height: Optional[int], fps: Optional[int], bitrate: Optional[int]) -> bool:
        """
        Locates the ONVIF Media service endpoint and updates the Video Encoder Configuration.
        """
        # 1. Resolve Device Service XAddr
        endpoints = [
            f"{self.base_url}/onvif/device_service",
            f"http://{self.ip}/onvif/device_service",
            f"http://{self.ip}:8899/onvif/device_service"
        ]
        
        device_service_url = None
        last_err = None
        for ep in endpoints:
            try:
                # Test connection using GetCapabilities
                body = "<tds:GetCapabilities><tds:Category>Media</tds:Category></tds:GetCapabilities>"
                response_text = await self._post_soap(ep, "http://www.onvif.org/ver10/device/wsdl/GetCapabilities", body)
                device_service_url = ep
                break
            except Exception as e:
                last_err = e
                continue
                
        if not device_service_url:
            logger.error(f"[ONVIFClient] Could not reach ONVIF device service. Last Error: {last_err}")
            return False

        try:
            # 2. Extract Media Service Address
            root = ET.fromstring(response_text)
            namespaces = {
                'soap': 'http://www.w3.org/2003/05/soap-envelope',
                'tds': 'http://www.onvif.org/ver10/device/wsdl',
                'tt': 'http://www.onvif.org/ver10/schema'
            }
            media_xaddr_el = root.find('.//tt:Media/tt:XAddr', namespaces)
            if media_xaddr_el is None:
                # Try fallback tag search
                media_xaddr_el = root.find('.//{http://www.onvif.org/ver10/schema}XAddr')
                
            if media_xaddr_el is None or not media_xaddr_el.text:
                logger.error("[ONVIFClient] ONVIF Capabilities response did not contain a Media service XAddr.")
                return False
                
            media_url = media_xaddr_el.text
            # Replace localhost inside URL if returned by camera loopback config
            if "127.0.0.1" in media_url or "localhost" in media_url:
                media_url = media_url.replace("127.0.0.1", self.ip).replace("localhost", self.ip)
                
            logger.info(f"[ONVIFClient] Resolved Media service address: {media_url}")

            # 3. Retrieve Current Encoder Settings
            get_config_body = "<trt:GetVideoEncoderConfigurations />"
            configs_response = await self._post_soap(media_url, "http://www.onvif.org/ver10/media/wsdl/GetVideoEncoderConfigurations", get_config_body)
            configs_root = ET.fromstring(configs_response)
            
            # Find the primary main profile configuration token
            media_ns = {'tt': 'http://www.onvif.org/ver10/schema', 'trt': 'http://www.onvif.org/ver10/media/wsdl'}
            configs = configs_root.findall('.//trt:Configurations', media_ns)
            if not configs:
                # Try wildcard namespace find
                configs = configs_root.findall('.//{http://www.onvif.org/ver10/schema}Configurations')
                if not configs:
                    configs = configs_root.findall('.//{http://www.onvif.org/ver10/media/wsdl}Configurations')
            
            if not configs:
                logger.error("[ONVIFClient] No VideoEncoderConfigurations returned by camera.")
                return False
                
            # Select target config (typically the first one is the Main profile)
            config_el = configs[0]
            token = config_el.get('token')
            name_el = config_el.find('.//tt:Name', media_ns) or config_el.find('.//{http://www.onvif.org/ver10/schema}Name')
            name = name_el.text if name_el is not None else "VideoEncoder"
            use_count_el = config_el.find('.//tt:UseCount', media_ns) or config_el.find('.//{http://www.onvif.org/ver10/schema}UseCount')
            use_count = int(use_count_el.text) if use_count_el is not None else 1
            encoding_el = config_el.find('.//tt:Encoding', media_ns) or config_el.find('.//{http://www.onvif.org/ver10/schema}Encoding')
            encoding = encoding_el.text if encoding_el is not None else "H264"
            
            # Parse existing values to merge changes
            width_el = config_el.find('.//tt:Resolution/tt:Width', media_ns) or config_el.find('.//{http://www.onvif.org/ver10/schema}Width')
            height_el = config_el.find('.//tt:Resolution/tt:Height', media_ns) or config_el.find('.//{http://www.onvif.org/ver10/schema}Height')
            fps_el = config_el.find('.//tt:RateControl/tt:FrameRateLimit', media_ns) or config_el.find('.//{http://www.onvif.org/ver10/schema}FrameRateLimit')
            bitrate_el = config_el.find('.//tt:RateControl/tt:BitrateLimit', media_ns) or config_el.find('.//{http://www.onvif.org/ver10/schema}BitrateLimit')

            final_width = width if width is not None else (int(width_el.text) if width_el is not None else 1920)
            final_height = height if height is not None else (int(height_el.text) if height_el is not None else 1080)
            final_fps = fps if fps is not None else (int(fps_el.text) if fps_el is not None else 15)
            final_bitrate = bitrate if bitrate is not None else (int(bitrate_el.text) if bitrate_el is not None else 2048)

            # 4. Set Video Encoder Configuration
            set_body = f"""<trt:SetVideoEncoderConfiguration>
      <trt:Configuration token="{token}">
        <tt:Name>{name}</tt:Name>
        <tt:UseCount>{use_count}</tt:UseCount>
        <tt:Encoding>{encoding}</tt:Encoding>
        <tt:Resolution>
          <tt:Width>{final_width}</tt:Width>
          <tt:Height>{final_height}</tt:Height>
        </tt:Resolution>
        <tt:RateControl>
          <tt:FrameRateLimit>{final_fps}</tt:FrameRateLimit>
          <tt:EncodingInterval>1</tt:EncodingInterval>
          <tt:BitrateLimit>{final_bitrate}</tt:BitrateLimit>
        </tt:RateControl>
      </trt:Configuration>
      <trt:ForcePersistence>true</trt:ForcePersistence>
    </trt:SetVideoEncoderConfiguration>"""

            await self._post_soap(media_url, "http://www.onvif.org/ver10/media/wsdl/SetVideoEncoderConfiguration", set_body)
            logger.info(f"[ONVIFClient] Successfully configured camera via ONVIF: Token={token}, Resolution={final_width}x{final_height}, FPS={final_fps}, Bitrate={final_bitrate} kbps")
            return True
            
        except Exception as e:
            logger.error(f"[ONVIFClient] Failed to execute ONVIF operation: {e}")
            return False

    async def run_hikvision_fallback(self, fps: Optional[int], bitrate: Optional[int], width: Optional[int], height: Optional[int]) -> bool:
        """
        Configures Hikvision cameras using native ISAPI XML interface.
        """
        url = f"{self.base_url}/ISAPI/Streaming/channels/101"
        try:
            auth = httpx.DigestAuth(self.username, self.password)
            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                # 1. Fetch channel XML configuration
                response = await client.get(url, auth=auth)
                if response.status_code == 401:
                    # Retry with basic auth
                    auth = httpx.BasicAuth(self.username, self.password)
                    response = await client.get(url, auth=auth)
                
                response.raise_for_status()
                channel_xml = response.text
                
                # 2. Modify XML parameters
                # Remove namespaces for easy parsing/regex modifications
                xml_clean = re.sub(r'\sxmlns="[^"]+"', '', channel_xml)
                
                if fps is not None:
                    xml_clean = re.sub(r'<videoFramerate>[^<]+</videoFramerate>', f'<videoFramerate>{fps}</videoFramerate>', xml_clean)
                if bitrate is not None:
                    # Convert to bps if required, Hikvision uses kbps or bps depending on version, usually bps (e.g. 2048000)
                    xml_clean = re.sub(r'<maxBitrate>[^<]+</maxBitrate>', f'<maxBitrate>{bitrate * 1000}</maxBitrate>', xml_clean)
                if width is not None and height is not None:
                    xml_clean = re.sub(r'<videoResolutionWidth>[^<]+</videoResolutionWidth>', f'<videoResolutionWidth>{width}</videoResolutionWidth>', xml_clean)
                    xml_clean = re.sub(r'<videoResolutionHeight>[^<]+</videoResolutionHeight>', f'<videoResolutionHeight>{height}</videoResolutionHeight>', xml_clean)

                # 3. Save configuration back
                headers = {"Content-Type": "application/xml"}
                put_response = await client.put(url, content=xml_clean, headers=headers, auth=auth)
                put_response.raise_for_status()
                logger.info(f"[HikvisionFallback] Configured parameters successfully on ISAPI channel 101.")
                return True
        except Exception as e:
            logger.error(f"[HikvisionFallback] Failed to configure Hikvision camera: {e}")
            return False

    async def run_dahua_fallback(self, fps: Optional[int], bitrate: Optional[int], width: Optional[int], height: Optional[int]) -> bool:
        """
        Configures Dahua cameras using Dahua configManager CGI endpoints.
        """
        try:
            auth = httpx.DigestAuth(self.username, self.password)
            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                # 1. Build CGI URL params
                params = {}
                if fps is not None:
                    params["Encode[0].MainFormat[0].Video.FPS"] = fps
                if bitrate is not None:
                    params["Encode[0].MainFormat[0].Video.BitRate"] = bitrate
                if width is not None:
                    params["Encode[0].MainFormat[0].Video.Width"] = width
                if height is not None:
                    params["Encode[0].MainFormat[0].Video.Height"] = height
                    
                query_str = "&".join([f"{k}={v}" for k, v in params.items()])
                url = f"{self.base_url}/cgi-bin/configManager.cgi?action=setConfig&{query_str}"
                
                response = await client.get(url, auth=auth)
                if response.status_code == 401:
                    auth = httpx.BasicAuth(self.username, self.password)
                    response = await client.get(url, auth=auth)
                    
                response.raise_for_status()
                if "OK" in response.text:
                    logger.info("[DahuaFallback] Configuration applied successfully via Dahua CGI configManager.")
                    return True
                else:
                    logger.error(f"[DahuaFallback] Dahua server returned error: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"[DahuaFallback] Failed to configure Dahua camera: {e}")
            return False

    async def configure(self, width: Optional[int] = None, height: Optional[int] = None, 
                        fps: Optional[int] = None, bitrate: Optional[int] = None, 
                        make: Optional[str] = None) -> bool:
        """
        Unified method to apply the encoder configuration.
        Tries ONVIF first, then falls back to vendor specific APIs.
        """
        logger.info(f"[CameraConfigClient] Attempting configuration updates for {self.ip} (ONVIF -> Fallbacks)...")
        
        # 1. Try ONVIF
        success = await self.run_onvif_setup(width, height, fps, bitrate)
        if success:
            return True
            
        # 2. Try Vendor Specific Fallbacks
        brand = (make or "").lower()
        if "hikvision" in brand:
            logger.info("[CameraConfigClient] ONVIF failed. Trying Hikvision ISAPI fallback...")
            return await self.run_hikvision_fallback(fps, bitrate, width, height)
        elif "dahua" in brand:
            logger.info("[CameraConfigClient] ONVIF failed. Trying Dahua CGI fallback...")
            return await self.run_dahua_fallback(fps, bitrate, width, height)
        else:
            # Try both if brand is generic or Sparsh
            logger.info("[CameraConfigClient] ONVIF failed. Testing all vendor specific fallback interfaces...")
            dahua_ok = await self.run_dahua_fallback(fps, bitrate, width, height)
            if dahua_ok:
                return True
            return await self.run_hikvision_fallback(fps, bitrate, width, height)
