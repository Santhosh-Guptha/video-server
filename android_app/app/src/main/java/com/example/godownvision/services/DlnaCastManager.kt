package com.example.godownvision.services

import android.content.Context
import android.net.wifi.WifiManager
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.DatagramPacket
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.MulticastSocket
import java.net.URL
import java.util.Locale

data class DlnaDevice(
    val id: String,
    val friendlyName: String,
    val manufacturer: String,
    val ipAddress: String,
    val locationUrl: String,
    var avTransportControlUrl: String = ""
)

object DlnaCastManager {
    private const val TAG = "DlnaCastManager"
    private const val SSDP_MULTICAST_HOST = "239.255.255.250"
    private const val SSDP_PORT = 1900

    private val discoveredDevices = mutableMapOf<String, DlnaDevice>()

    suspend fun discoverDevices(context: Context): List<DlnaDevice> = withContext(Dispatchers.IO) {
        discoveredDevices.clear()
        var multicastLock: WifiManager.MulticastLock? = null
        try {
            val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
            multicastLock = wifiManager?.createMulticastLock("DlnaDiscovery")
            multicastLock?.acquire()

            val socket = MulticastSocket(null)
            socket.reuseAddress = true
            socket.timeToLive = 4

            val group = InetAddress.getByName(SSDP_MULTICAST_HOST)
            val searchMessage = "M-SEARCH * HTTP/1.1\r\n" +
                    "HOST: $SSDP_MULTICAST_HOST:$SSDP_PORT\r\n" +
                    "MAN: \"ssdp:discover\"\r\n" +
                    "MX: 3\r\n" +
                    "ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n"

            val sendData = searchMessage.toByteArray()
            val sendPacket = DatagramPacket(sendData, sendData.size, group, SSDP_PORT)
            socket.send(sendPacket)

            // Fallback SSDP search
            val searchAllMessage = "M-SEARCH * HTTP/1.1\r\n" +
                    "HOST: $SSDP_MULTICAST_HOST:$SSDP_PORT\r\n" +
                    "MAN: \"ssdp:discover\"\r\n" +
                    "MX: 3\r\n" +
                    "ST: ssdp:all\r\n\r\n"
            val sendAllData = searchAllMessage.toByteArray()
            socket.send(DatagramPacket(sendAllData, sendAllData.size, group, SSDP_PORT))

            val receiveData = ByteArray(2048)
            socket.soTimeout = 2500

            val startTime = System.currentTimeMillis()
            while (System.currentTimeMillis() - startTime < 3000) {
                try {
                    val receivePacket = DatagramPacket(receiveData, receiveData.size)
                    socket.receive(receivePacket)
                    val response = String(receivePacket.data, 0, receivePacket.length)
                    parseSsdpResponse(response, receivePacket.address.hostAddress ?: "")
                } catch (e: Exception) {
                    // Timeout expected
                }
            }
            socket.close()
        } catch (e: Exception) {
            Log.e(TAG, "SSDP Discovery error: ${e.message}")
        } finally {
            try { multicastLock?.release() } catch (e: Exception) {}
        }

        return@withContext discoveredDevices.values.toList()
    }

    private fun parseSsdpResponse(response: String, senderIp: String) {
        var location = ""
        val lines = response.split("\r\n")
        for (line in lines) {
            val lower = line.lowercase(Locale.getDefault())
            if (lower.startsWith("location:")) {
                location = line.substring(9).trim()
                break
            }
        }

        if (location.isNotBlank() && !discoveredDevices.containsKey(location)) {
            fetchDeviceDescription(location, senderIp)
        }
    }

    private fun fetchDeviceDescription(locationUrl: String, senderIp: String) {
        try {
            val url = URL(locationUrl)
            val conn = url.openConnection() as HttpURLConnection
            conn.connectTimeout = 2000
            conn.readTimeout = 2000
            if (conn.responseCode == 200) {
                val reader = BufferedReader(InputStreamReader(conn.inputStream))
                val xmlContent = reader.readText()
                reader.close()

                val friendlyName = extractXmlTag(xmlContent, "friendlyName").ifBlank { "Smart TV ($senderIp)" }
                val manufacturer = extractXmlTag(xmlContent, "manufacturer").ifBlank { "Media Renderer" }
                val controlUrl = extractControlUrl(xmlContent, locationUrl)

                val device = DlnaDevice(
                    id = locationUrl,
                    friendlyName = friendlyName,
                    manufacturer = manufacturer,
                    ipAddress = senderIp,
                    locationUrl = locationUrl,
                    avTransportControlUrl = controlUrl
                )
                discoveredDevices[locationUrl] = device
            }
        } catch (e: Exception) {
            Log.d(TAG, "Error fetching device xml from $locationUrl: ${e.message}")
        }
    }

    private fun extractXmlTag(xml: String, tag: String): String {
        val startTag = "<$tag>"
        val endTag = "</$tag>"
        val start = xml.indexOf(startTag)
        val end = xml.indexOf(endTag)
        return if (start != -1 && end != -1 && end > start) {
            xml.substring(start + startTag.length, end).trim()
        } else ""
    }

    private fun extractControlUrl(xml: String, baseUrlStr: String): String {
        var controlPath = ""
        val serviceStart = xml.indexOf("urn:schemas-upnp-org:service:AVTransport:1")
        if (serviceStart != -1) {
            val serviceBlock = xml.substring(serviceStart)
            controlPath = extractXmlTag(serviceBlock, "controlURL")
        }

        if (controlPath.isBlank()) {
            controlPath = extractXmlTag(xml, "controlURL")
        }

        return if (controlPath.startsWith("http://") || controlPath.startsWith("https://")) {
            controlPath
        } else if (controlPath.isNotBlank()) {
            val baseUrl = URL(baseUrlStr)
            val portStr = if (baseUrl.port != -1) ":${baseUrl.port}" else ""
            val prefix = "${baseUrl.protocol}://${baseUrl.host}$portStr"
            if (controlPath.startsWith("/")) "$prefix$controlPath" else "$prefix/$controlPath"
        } else {
            ""
        }
    }

    suspend fun playMediaOnTv(device: DlnaDevice, mediaUrl: String): Boolean = withContext(Dispatchers.IO) {
        if (device.avTransportControlUrl.isBlank()) return@withContext false

        try {
            val setUriSoap = """
                <?xml version="1.0" encoding="utf-8"?>
                <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
                    <s:Body>
                        <u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
                            <InstanceID>0</InstanceID>
                            <CurrentURI>$mediaUrl</CurrentURI>
                            <CurrentURIMetaData></CurrentURIMetaData>
                        </u:SetAVTransportURI>
                    </s:Body>
                </s:Envelope>
            """.trimIndent()

            postSoapAction(device.avTransportControlUrl, "urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI", setUriSoap)

            val playSoap = """
                <?xml version="1.0" encoding="utf-8"?>
                <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
                    <s:Body>
                        <u:Play xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
                            <InstanceID>0</InstanceID>
                            <Speed>1</Speed>
                        </u:Play>
                    </s:Body>
                </s:Envelope>
            """.trimIndent()

            postSoapAction(device.avTransportControlUrl, "urn:schemas-upnp-org:service:AVTransport:1#Play", playSoap)
            return@withContext true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send DLNA play request to ${device.friendlyName}: ${e.message}")
            return@withContext false
        }
    }

    suspend fun stopMediaOnTv(device: DlnaDevice): Boolean = withContext(Dispatchers.IO) {
        if (device.avTransportControlUrl.isBlank()) return@withContext false

        try {
            val stopSoap = """
                <?xml version="1.0" encoding="utf-8"?>
                <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
                    <s:Body>
                        <u:Stop xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
                            <InstanceID>0</InstanceID>
                        </u:Stop>
                    </s:Body>
                </s:Envelope>
            """.trimIndent()

            postSoapAction(device.avTransportControlUrl, "urn:schemas-upnp-org:service:AVTransport:1#Stop", stopSoap)
            return@withContext true
        } catch (e: Exception) {
            return@withContext false
        }
    }

    private fun postSoapAction(controlUrl: String, soapAction: String, xmlPayload: String) {
        val url = URL(controlUrl)
        val conn = url.openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.connectTimeout = 3000
        conn.readTimeout = 3000
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "text/xml; charset=\"utf-8\"")
        conn.setRequestProperty("SOAPACTION", "\"$soapAction\"")

        val writer = OutputStreamWriter(conn.outputStream, "UTF-8")
        writer.write(xmlPayload)
        writer.flush()
        writer.close()

        val responseCode = conn.responseCode
        Log.d(TAG, "SOAP Action $soapAction returned response code: $responseCode")
    }
}
