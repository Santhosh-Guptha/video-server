import unittest
import xml.etree.ElementTree as ET
from onvif_client import parse_rtsp_url, CameraConfigClient

class TestONVIFClient(unittest.TestCase):
    def test_rtsp_url_parser(self):
        # 1. Simple RTSP URL
        res1 = parse_rtsp_url("rtsp://admin:admin123@172.20.100.245:554/Streaming/Channels/101")
        self.assertIsNotNone(res1)
        host, user, pwd = res1
        self.assertEqual(host, "172.20.100.245")
        self.assertEqual(user, "admin")
        self.assertEqual(pwd, "admin123")

        # 2. RTSP URL without port
        res2 = parse_rtsp_url("rtsp://vstest:MCL@123@172.20.100.208/live/stream")
        self.assertIsNotNone(res2)
        host, user, pwd = res2
        self.assertEqual(host, "172.20.100.208")
        self.assertEqual(user, "vstest")
        self.assertEqual(pwd, "MCL@123")

        # 3. RTSP URL with special characters in password
        res3 = parse_rtsp_url("rtsp://special_user:pass:word@10.0.0.1:554/path")
        self.assertIsNotNone(res3)
        host, user, pwd = res3
        self.assertEqual(host, "10.0.0.1")
        self.assertEqual(user, "special_user")
        self.assertEqual(pwd, "pass:word")

    def test_wsse_header_generation(self):
        client = CameraConfigClient(ip="172.20.100.245", username="admin", password="password123")
        header_xml = client._create_wsse_header()
        
        # Verify it is valid XML fragment by wrapping in root
        wrapped = f"<root xmlns:soap='http://www.w3.org/2003/05/soap-envelope'>{header_xml}</root>"
        root = ET.fromstring(wrapped)
        
        # Check Username tag
        username_el = root.find('.//{http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd}Username')
        self.assertIsNotNone(username_el)
        self.assertEqual(username_el.text, "admin")

        # Check digest is present
        pwd_el = root.find('.//{http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd}Password')
        self.assertIsNotNone(pwd_el)
        self.assertTrue(len(pwd_el.text) > 10)

    def test_soap_capabilities_parsing(self):
        # Mock SOAP Response for GetCapabilities
        mock_response = """<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:tt="http://www.onvif.org/ver10/schema">
  <SOAP-ENV:Body>
    <tds:GetCapabilitiesResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
      <tds:Capabilities>
        <tt:Media>
          <tt:XAddr>https://172.20.100.245/onvif/media_service</tt:XAddr>
        </tt:Media>
      </tds:Capabilities>
    </tds:GetCapabilitiesResponse>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
        
        root = ET.fromstring(mock_response)
        namespaces = {
            'soap': 'http://www.w3.org/2003/05/soap-envelope',
            'tt': 'http://www.onvif.org/ver10/schema'
        }
        media_xaddr_el = root.find('.//tt:Media/tt:XAddr', namespaces)
        self.assertIsNotNone(media_xaddr_el)
        self.assertEqual(media_xaddr_el.text, "https://172.20.100.245/onvif/media_service")

if __name__ == "__main__":
    unittest.main()
