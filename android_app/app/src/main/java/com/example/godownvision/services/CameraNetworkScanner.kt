package com.example.godownvision.services

import android.content.Context
import android.net.wifi.WifiManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStream
import java.net.DatagramPacket
import java.net.Inet4Address
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.MulticastSocket
import java.net.NetworkInterface
import java.net.Socket
import java.util.UUID

enum class DeviceAuthStatus {
    PUBLIC,
    RESTRICTED,
    UNKNOWN
}

data class DiscoveredDevice(
    val ip: String,
    val primaryPort: Int = 554,
    val openPorts: List<Int> = emptyList(),
    val authStatus: DeviceAuthStatus = DeviceAuthStatus.UNKNOWN,
    val brand: String = "Network CCTV Device",
    val serviceName: String = "Camera Stream"
)

object CameraNetworkScanner {

    private const val SOCKET_TIMEOUT_MS = 400
    private val TARGET_PORTS = listOf(554, 8000, 80)

    /**
     * Dynamically extracts /24 Subnet Prefix from any IP (e.g. "10.0.0.45" -> "10.0.0.")
     */
    fun extractSubnetPrefix(ip: String): String {
        val parts = ip.trim().split(".")
        return if (parts.size == 4) {
            "${parts[0]}.${parts[1]}.${parts[2]}."
        } else {
            ""
        }
    }

    /**
     * Dynamically retrieves local device IP address from active Wi-Fi / network interfaces
     */
    fun getLocalWifiIpAddress(context: Context): String {
        try {
            val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
            val ipInt = wifiManager?.connectionInfo?.ipAddress ?: 0
            if (ipInt != 0) {
                return String.format(
                    "%d.%d.%d.%d",
                    ipInt and 0xff,
                    ipInt shr 8 and 0xff,
                    ipInt shr 16 and 0xff,
                    ipInt shr 24 and 0xff
                )
            }
        } catch (e: Exception) {
            // Network interface fallback
        }

        try {
            val interfaces = NetworkInterface.getNetworkInterfaces()
            while (interfaces.hasMoreElements()) {
                val iface = interfaces.nextElement()
                if (iface.isLoopback || !iface.isUp) continue
                val addrs = iface.inetAddresses
                while (addrs.hasMoreElements()) {
                    val addr = addrs.nextElement()
                    if (!addr.isLoopbackAddress && addr is Inet4Address) {
                        val host = addr.hostAddress
                        if (!host.isNullOrBlank()) return host
                    }
                }
            }
        } catch (e: Exception) {
            // Ignore
        }
        return ""
    }

    /**
     * Feature A: Targeted Subnet IP Range Scanner
     * Sweeps /24 IP subnet dynamically (1-254) across ports 554, 8000, 80 with 400ms timeout
     */
    suspend fun sweepSubnetRange(
        baseIp: String,
        onProgress: (Int, Int) -> Unit
    ): List<DiscoveredDevice> = withContext(Dispatchers.IO) {
        val prefix = extractSubnetPrefix(baseIp)
        if (prefix.isBlank()) return@withContext emptyList()

        val discoveredList = mutableListOf<DiscoveredDevice>()
        val totalIps = 254

        coroutineScope {
            val deferredList = (1..totalIps).map { i ->
                async {
                    val targetIp = "$prefix$i"
                    val activePorts = mutableListOf<Int>()

                    for (port in TARGET_PORTS) {
                        if (isPortOpen(targetIp, port, SOCKET_TIMEOUT_MS)) {
                            activePorts.add(port)
                        }
                    }

                    if (activePorts.isNotEmpty()) {
                        val mainPort = if (activePorts.contains(554)) 554 else activePorts.first()
                        val typeDescription = when {
                            activePorts.contains(8000) -> "NVR / Camera Server"
                            activePorts.contains(554) -> "RTSP Video Feed"
                            else -> "HTTP Video Endpoint"
                        }

                        DiscoveredDevice(
                            ip = targetIp,
                            primaryPort = mainPort,
                            openPorts = activePorts,
                            authStatus = DeviceAuthStatus.UNKNOWN,
                            brand = typeDescription,
                            serviceName = "Device $targetIp:$mainPort"
                        )
                    } else null
                }
            }

            var completed = 0
            deferredList.forEach { deferred ->
                val result = deferred.await()
                completed++
                onProgress(completed, totalIps)
                if (result != null) {
                    discoveredList.add(result)
                }
            }
        }

        discoveredList
    }

    /**
     * Feature B: WS-Discovery Multicast & Auth Validation Engine
     */
    suspend fun scanWifiOnvifMulticast(
        context: Context,
        onProgress: (String) -> Unit
    ): List<DiscoveredDevice> = withContext(Dispatchers.IO) {
        val results = mutableMapOf<String, DiscoveredDevice>()
        onProgress("Broadcasting WS-Discovery Multicast Probe...")

        var multicastSocket: MulticastSocket? = null
        var wifiLock: WifiManager.MulticastLock? = null

        try {
            val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
            wifiLock = wifiManager?.createMulticastLock("ws_discovery_lock")
            wifiLock?.acquire()

            val group = InetAddress.getByName("239.255.255.250")
            multicastSocket = MulticastSocket(3702)
            multicastSocket.soTimeout = 2500

            val uuidStr = UUID.randomUUID().toString()
            val probeXml = """
                <?xml version="1.0" encoding="UTF-8"?>
                <e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
                            xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
                            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
                            xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
                    <e:Header>
                        <w:MessageID>urn:uuid:$uuidStr</w:MessageID>
                        <w:To>urn:schemas-xmlsoap-org:ws:2004:08:addressing:role:anonymous</w:To>
                        <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
                    </e:Header>
                    <e:Body>
                        <d:Probe>
                            <d:Types>dn:NetworkVideoTransmitter</d:Types>
                        </d:Probe>
                    </e:Body>
                </e:Envelope>
            """.trimIndent()

            val sendData = probeXml.toByteArray()
            val packet = DatagramPacket(sendData, sendData.size, group, 3702)
            multicastSocket.send(packet)

            val recvBuf = ByteArray(4096)
            val startTime = System.currentTimeMillis()

            while (System.currentTimeMillis() - startTime < 2500) {
                try {
                    val recvPacket = DatagramPacket(recvBuf, recvBuf.size)
                    multicastSocket.receive(recvPacket)
                    val senderIp = recvPacket.address.hostAddress ?: continue
                    if (senderIp.isNotBlank() && !results.containsKey(senderIp)) {
                        onProgress("Discovered camera $senderIp. Testing authentication...")
                        val authStatus = validateCameraAuth(senderIp, 554)
                        results[senderIp] = DiscoveredDevice(
                            ip = senderIp,
                            primaryPort = 554,
                            openPorts = listOf(554, 80),
                            authStatus = authStatus,
                            brand = if (authStatus == DeviceAuthStatus.PUBLIC) "Unsecured Camera Feed" else "Secured Camera Feed",
                            serviceName = "ONVIF Camera $senderIp"
                        )
                    }
                } catch (e: Exception) {
                    break
                }
            }
        } catch (e: Exception) {
            // Multicast exception handling
        } finally {
            try {
                multicastSocket?.close()
            } catch (e: Exception) {}
            try {
                wifiLock?.let { if (it.isHeld) it.release() }
            } catch (e: Exception) {}
        }

        // Dynamic Subnet Fallback if multicast returns 0 devices
        if (results.isEmpty()) {
            val localIp = getLocalWifiIpAddress(context)
            if (localIp.isNotBlank()) {
                val prefix = extractSubnetPrefix(localIp)
                if (prefix.isNotBlank()) {
                    onProgress("Scanning subnet $prefix* for video feeds...")
                    coroutineScope {
                        val deferredList = (1..254).map { i ->
                            async {
                                val targetIp = "$prefix$i"
                                if (isPortOpen(targetIp, 554, 300) || isPortOpen(targetIp, 8000, 300)) {
                                    val authStatus = validateCameraAuth(targetIp, 554)
                                    DiscoveredDevice(
                                        ip = targetIp,
                                        primaryPort = 554,
                                        openPorts = listOf(554),
                                        authStatus = authStatus,
                                        brand = if (authStatus == DeviceAuthStatus.PUBLIC) "Unsecured Video Feed" else "Secured Video Feed",
                                        serviceName = "Network Camera $targetIp"
                                    )
                                } else null
                            }
                        }
                        deferredList.awaitAll().filterNotNull().forEach { dev ->
                            results[dev.ip] = dev
                        }
                    }
                }
            }
        }

        results.values.toList()
    }

    /**
     * Headless RTSP DESCRIBE probe for Auth classification (200 OK -> PUBLIC, 401/403 -> RESTRICTED)
     */
    private fun validateCameraAuth(ip: String, port: Int): DeviceAuthStatus {
        var socket: Socket? = null
        return try {
            socket = Socket()
            socket.connect(InetSocketAddress(ip, port), 600)
            socket.soTimeout = 800

            val os: OutputStream = socket.getOutputStream()
            val reader = BufferedReader(InputStreamReader(socket.getInputStream()))

            val rtspRequest = "DESCRIBE rtsp://$ip:$port/live.sdp RTSP/1.0\r\nCSeq: 1\r\nUser-Agent: AegisStreamScanner/1.0\r\n\r\n"
            os.write(rtspRequest.toByteArray(Charsets.UTF_8))
            os.flush()

            val responseLine = reader.readLine() ?: ""
            when {
                responseLine.contains("200 OK", ignoreCase = true) -> DeviceAuthStatus.PUBLIC
                responseLine.contains("401", ignoreCase = true) || responseLine.contains("403", ignoreCase = true) -> DeviceAuthStatus.RESTRICTED
                else -> DeviceAuthStatus.RESTRICTED
            }
        } catch (e: Exception) {
            DeviceAuthStatus.RESTRICTED
        } finally {
            try {
                socket?.close()
            } catch (e: Exception) {}
        }
    }

    private fun isPortOpen(ip: String, port: Int, timeoutMs: Int): Boolean {
        var socket: Socket? = null
        return try {
            socket = Socket()
            socket.connect(InetSocketAddress(ip, port), timeoutMs)
            true
        } catch (e: Exception) {
            false
        } finally {
            try {
                socket?.close()
            } catch (e: Exception) {}
        }
    }
}
