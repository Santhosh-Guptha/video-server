package com.example.godownvision.services

import android.content.Context
import android.net.wifi.WifiManager
import android.util.Log
import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpHandler
import com.sun.net.httpserver.HttpServer
import java.io.OutputStream
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.NetworkInterface
import java.util.Collections

object LocalCastServer {
    private const val TAG = "LocalCastServer"
    private var httpServer: HttpServer? = null
    private var activePort: Int = 8080
    private var currentCameraName: String = "Live Camera"
    private var currentRtspUrl: String = ""

    fun isRunning(): Boolean = httpServer != null

    fun getCastUrl(context: Context, port: Int = 8080): String {
        val ip = getLocalIpAddress(context)
        return "http://$ip:$port"
    }

    fun startServer(context: Context, port: Int = 8080, cameraName: String, rtspUrl: String): String {
        stopServer()
        activePort = port
        currentCameraName = cameraName
        currentRtspUrl = rtspUrl

        try {
            httpServer = HttpServer.create(InetSocketAddress(activePort), 0)
            httpServer?.createContext("/", IndexHandler())
            httpServer?.createContext("/stream", StreamHandler())
            httpServer?.executor = null
            httpServer?.start()
            Log.i(TAG, "Embedded Local Cast Server started at ${getCastUrl(context, activePort)}")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start Local Cast Server: ${e.message}")
        }
        return getCastUrl(context, activePort)
    }

    fun stopServer() {
        try {
            httpServer?.stop(0)
            httpServer = null
            Log.i(TAG, "Embedded Local Cast Server stopped.")
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping Local Cast Server: ${e.message}")
        }
    }

    fun getLocalIpAddress(context: Context): String {
        try {
            val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
            val wifiInfo = wifiManager?.connectionInfo
            val ipInt = wifiInfo?.ipAddress ?: 0
            if (ipInt != 0) {
                return String.format(
                    "%d.%d.%d.%d",
                    ipInt and 0xff,
                    ipInt shr 8 and 0xff,
                    ipInt shr 16 and 0xff,
                    ipInt shr 24 and 0xff
                )
            }
        } catch (e: Exception) {}

        try {
            val interfaces = Collections.list(NetworkInterface.getNetworkInterfaces())
            for (intf in interfaces) {
                val addrs = Collections.list(intf.inetAddresses)
                for (addr in addrs) {
                    if (!addr.isLoopbackAddress && addr is InetAddress) {
                        val host = addr.hostAddress ?: ""
                        if (!host.contains(":")) {
                            return host
                        }
                    }
                }
            }
        } catch (e: Exception) {}

        return "127.0.0.1"
    }

    private class IndexHandler : HttpHandler {
        override fun handle(exchange: HttpExchange) {
            val htmlPage = """
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>AegisStream Live Cast - ${currentCameraName}</title>
                    <style>
                        * { margin: 0; padding: 0; box-sizing: border-box; }
                        body {
                            background-color: #0F172A;
                            color: #FFFFFF;
                            font-family: system-ui, -apple-system, sans-serif;
                            display: flex;
                            flex-direction: column;
                            height: 100vh;
                            overflow: hidden;
                        }
                        .header {
                            background: rgba(30, 41, 59, 0.9);
                            padding: 12px 20px;
                            display: flex;
                            align-items: center;
                            justify-content: space-between;
                            border-bottom: 1px solid #334155;
                        }
                        .title {
                            font-size: 16px;
                            font-weight: bold;
                            color: #38BDF8;
                            display: flex;
                            align-items: center;
                            gap: 8px;
                        }
                        .badge {
                            background: #10B981;
                            color: #0F172A;
                            font-size: 10px;
                            font-weight: bold;
                            padding: 3px 8px;
                            border-radius: 12px;
                        }
                        .viewport {
                            flex: 1;
                            background: #000000;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            position: relative;
                        }
                        img.stream-img {
                            max-width: 100%;
                            max-height: 100%;
                            object-fit: contain;
                        }
                    </style>
                </head>
                <body>
                    <div class="header">
                        <div class="title">
                            <span>🛡️ AegisStream Live Cast</span>
                            <span>•</span>
                            <span style="color:#FFF;">${currentCameraName}</span>
                        </div>
                        <div class="badge">LIVE CAST ACTIVE</div>
                    </div>
                    <div class="viewport">
                        <img src="/stream" class="stream-img" alt="AegisStream Camera Feed" id="castStream" />
                    </div>
                </body>
                </html>
            """.trimIndent()

            val bytes = htmlPage.toByteArray(Charsets.UTF_8)
            exchange.responseHeaders.add("Content-Type", "text/html; charset=utf-8")
            exchange.sendResponseHeaders(200, bytes.size.toLong())
            val os: OutputStream = exchange.responseBody
            os.write(bytes)
            os.close()
        }
    }

    private class StreamHandler : HttpHandler {
        override fun handle(exchange: HttpExchange) {
            try {
                exchange.responseHeaders.add("Content-Type", "multipart/x-mixed-replace; boundary=--jpgboundary")
                exchange.responseHeaders.add("Cache-Control", "no-cache, private")
                exchange.responseHeaders.add("Pragma", "no-cache")
                exchange.sendResponseHeaders(200, 0)

                val os: OutputStream = exchange.responseBody

                // Stream sample placeholder frame loop
                val dummyJpeg = createSyntheticJpegFrame()
                val boundaryHeader = "\r\n--jpgboundary\r\nContent-Type: image/jpeg\r\nContent-Length: ${dummyJpeg.size}\r\n\r\n"

                var isStreaming = true
                while (isStreaming) {
                    try {
                        os.write(boundaryHeader.toByteArray(Charsets.UTF_8))
                        os.write(dummyJpeg)
                        os.write("\r\n".toByteArray(Charsets.UTF_8))
                        os.flush()
                        Thread.sleep(100) // ~10 FPS MJPEG Stream
                    } catch (e: Exception) {
                        isStreaming = false
                    }
                }
                os.close()
            } catch (e: Exception) {
                Log.d(TAG, "Cast stream handler disconnected: ${e.message}")
            }
        }

        private fun createSyntheticJpegFrame(): ByteArray {
            val bitmap = android.graphics.Bitmap.createBitmap(640, 360, android.graphics.Bitmap.Config.ARGB_8888)
            val canvas = android.graphics.Canvas(bitmap)
            val paint = android.graphics.Paint()
            
            // Dark blue background
            paint.color = android.graphics.Color.parseColor("#0F172A")
            canvas.drawRect(0f, 0f, 640f, 360f, paint)

            // AegisStream overlay text
            paint.color = android.graphics.Color.parseColor("#38BDF8")
            paint.textSize = 28f
            paint.isFakeBoldText = true
            canvas.drawText("AegisStream Live Cast", 40f, 160f, paint)

            paint.color = android.graphics.Color.WHITE
            paint.textSize = 20f
            canvas.drawText("Camera: $currentCameraName", 40f, 210f, paint)

            paint.color = android.graphics.Color.parseColor("#10B981")
            paint.textSize = 16f
            val timeStr = java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.getDefault()).format(java.util.Date())
            canvas.drawText("● LIVE • $timeStr", 40f, 260f, paint)

            val stream = java.io.ByteArrayOutputStream()
            bitmap.compress(android.graphics.Bitmap.CompressFormat.JPEG, 75, stream)
            return stream.toByteArray()
        }
    }
}
