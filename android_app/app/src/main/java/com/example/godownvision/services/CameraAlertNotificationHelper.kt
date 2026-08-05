package com.example.godownvision.services

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.example.godownvision.MainActivity

object CameraAlertNotificationHelper {

    private const val CHANNEL_ID = "aegis_camera_alerts"
    private const val CHANNEL_NAME = "Camera Health & Offline Alerts"

    fun createNotificationChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "High-priority alerts when RTSP camera signals drop offline"
                enableVibration(true)
                vibrationPattern = longArrayOf(0, 500, 200, 500)
            }
            val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            manager.createNotificationChannel(channel)
        }
    }

    fun sendOfflineAlertNotification(context: Context, cameraId: Long, cameraName: String, timestampStr: String) {
        createNotificationChannel(context)

        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("EXTRA_CAMERA_ID", cameraId)
            putExtra("EXTRA_TIMESTAMP", timestampStr)
            putExtra("EXTRA_NAVIGATE_TAB", "BOOKMARKS")
        }

        val pendingIntent = PendingIntent.getActivity(
            context,
            cameraId.toInt(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_notify_error)
            .setContentTitle("🚨 Camera Offline Alert: $cameraName")
            .setContentText("$cameraName lost connection at $timestampStr. Tap to inspect.")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .build()

        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify((System.currentTimeMillis() % 10000).toInt(), notification)
    }
}
