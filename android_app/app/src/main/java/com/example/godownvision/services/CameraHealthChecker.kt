package com.example.godownvision.services

import android.content.Context
import com.example.godownvision.data.BookmarkIncident
import com.example.godownvision.data.CameraRepository
import com.example.godownvision.data.VaultRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.InetSocketAddress
import java.net.Socket
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap

object CameraHealthChecker {

    // Thread-safe map tracking previous connection state per camera (true = ONLINE, false = OFFLINE)
    private val previousStateMap = ConcurrentHashMap<Long, Boolean>()

    suspend fun checkAllCameras(context: Context) = withContext(Dispatchers.IO) {
        val vaultRepo = VaultRepository(context)
        val vaultData = vaultRepo.loadVault()
        val cameras = vaultData.cameras

        val timeFormatter = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
        val currentTimestamp = timeFormatter.format(Date())

        cameras.forEach { camera ->
            val isOnline = testCameraSocket(camera.localIp, if (camera.rtspPort > 0) camera.rtspPort else 554)
            val wasOnline = previousStateMap[camera.id]

            // Record current state
            previousStateMap[camera.id] = isOnline

            // State Transition Trigger: ONLY on ONLINE -> OFFLINE to prevent alert spamming!
            if (wasOnline == true && !isOnline) {
                // 1. Send High-Priority Push Notification
                CameraAlertNotificationHelper.sendOfflineAlertNotification(
                    context = context,
                    cameraId = camera.id,
                    cameraName = camera.name,
                    timestampStr = currentTimestamp
                )

                // 2. Auto-Save "CAMERA_OFFLINE_INCIDENT" Bookmark with status = "UNREVIEWED" to omnisight_vault.bin
                val autoBookmark = BookmarkIncident(
                    cameraId = camera.id,
                    cameraName = camera.name,
                    timestamp = currentTimestamp,
                    note = "ALERT: Camera Signal Disrupted (RTSP socket unreachable at ${camera.localIp}:${camera.rtspPort})",
                    type = "CAMERA_OFFLINE_INCIDENT",
                    status = "UNREVIEWED",
                    createdBy = "SYSTEM_HEALTH_MONITOR"
                )
                vaultRepo.addBookmark(autoBookmark)
            } else if (wasOnline == null && !isOnline) {
                // First boot check - record initial offline state
                previousStateMap[camera.id] = false
            }
        }
    }

    private fun testCameraSocket(ip: String, port: Int): Boolean {
        if (ip.isBlank()) return false
        return try {
            Socket().use { socket ->
                socket.connect(InetSocketAddress(ip, port), 3000) // 3-second TCP socket timeout
                true
            }
        } catch (e: Exception) {
            false
        }
    }
}
