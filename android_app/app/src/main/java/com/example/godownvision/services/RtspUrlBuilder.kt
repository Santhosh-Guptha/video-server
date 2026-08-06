package com.example.godownvision.services

import com.example.godownvision.data.CameraEntity
import java.net.URLEncoder

object RtspUrlBuilder {

    /**
     * Dynamically constructs live RTSP stream URL based on NVR Brand, host mode (local vs remote),
     * username, password, port, channel, and stream quality (MAIN vs SUB) without any hardcoded values.
     */
    fun buildLiveRtspUrl(
        camera: CameraEntity,
        isRemoteMode: Boolean,
        overrideQuality: String? = null
    ): String {
        if (camera.customRtspUrl.isNotBlank()) {
            return camera.customRtspUrl.trim()
        }

        val host = if (isRemoteMode) camera.remoteHost.ifBlank { camera.localIp } else camera.localIp.ifBlank { camera.remoteHost }
        val port = if (camera.rtspPort > 0) camera.rtspPort else 554
        val user = URLEncoder.encode(camera.username, "UTF-8")
        val pass = URLEncoder.encode(camera.password, "UTF-8")
        val auth = if (user.isNotEmpty() && pass.isNotEmpty()) "$user:$pass@" else ""
        val ch = if (camera.channel > 0) camera.channel else 1
        val qualityToUse = overrideQuality ?: camera.streamQuality
        val isSubStream = qualityToUse.equals("SUB", ignoreCase = true)

        return when (camera.nvrBrand.uppercase()) {
            "HIKVISION" -> {
                val streamId = if (isSubStream) "${ch}02" else "${ch}01"
                "rtsp://$auth$host:$port/Streaming/channels/$streamId"
            }
            "DAHUA" -> {
                val subtype = if (isSubStream) 1 else 0
                "rtsp://$auth$host:$port/cam/realmonitor?channel=$ch&subtype=$subtype"
            }
            "UNIVIEW" -> {
                val stream = if (isSubStream) 1 else 0
                "rtsp://$auth$host:$port/unicast/c$ch/s$stream/live"
            }
            "ONVIF", "CUSTOM" -> {
                val quality = if (isSubStream) "sub" else "main"
                "rtsp://$auth$host:$port/h264/ch$ch/$quality/av_stream"
            }
            else -> {
                val streamId = if (isSubStream) "${ch}02" else "${ch}01"
                "rtsp://$auth$host:$port/Streaming/channels/$streamId"
            }
        }
    }

    /**
     * Dynamically constructs NVR Recorded Footage Playback RTSP stream URL with exact user-selected
     * start and end timestamps.
     */
    fun buildPlaybackRtspUrl(
        camera: CameraEntity,
        isRemoteMode: Boolean,
        startDateStr: String, // YYYYMMDD
        startTimeStr: String, // HHMMSS
        endDateStr: String,   // YYYYMMDD
        endTimeStr: String    // HHMMSS
    ): String {
        if (camera.customRtspUrl.isNotBlank()) {
            val base = camera.customRtspUrl.trim()
            val delim = if (base.contains("?")) "&" else "?"
            val start = "${startDateStr}T${startTimeStr}Z"
            val end = "${endDateStr}T${endTimeStr}Z"
            return "$base${delim}starttime=$start&endtime=$end"
        }
        val host = if (isRemoteMode) camera.remoteHost.ifBlank { camera.localIp } else camera.localIp.ifBlank { camera.remoteHost }
        val port = if (camera.rtspPort > 0) camera.rtspPort else 554
        val user = URLEncoder.encode(camera.username, "UTF-8")
        val pass = URLEncoder.encode(camera.password, "UTF-8")
        val auth = if (user.isNotEmpty() && pass.isNotEmpty()) "$user:$pass@" else ""
        val ch = if (camera.channel > 0) camera.channel else 1

        return when (camera.nvrBrand.uppercase()) {
            "HIKVISION" -> {
                val start = "${startDateStr}T${startTimeStr}Z"
                val end = "${endDateStr}T${endTimeStr}Z"
                val trackId = "${ch}01"
                "rtsp://$auth$host:$port/Streaming/tracks/$trackId?starttime=$start&endtime=$end"
            }
            "DAHUA" -> {
                val formattedStart = "${startDateStr.take(4)}-${startDateStr.substring(4, 6)}-${startDateStr.substring(6, 8)}_${startTimeStr.take(2)}:${startTimeStr.substring(2, 4)}:${startTimeStr.substring(4, 6)}"
                val formattedEnd = "${endDateStr.take(4)}-${endDateStr.substring(4, 6)}-${endDateStr.substring(6, 8)}_${endTimeStr.take(2)}:${endTimeStr.substring(2, 4)}:${endTimeStr.substring(4, 6)}"
                "rtsp://$auth$host:$port/cam/realmonitor?channel=$ch&subtype=0&starttime=$formattedStart&endtime=$formattedEnd"
            }
            else -> {
                val start = "${startDateStr}T${startTimeStr}Z"
                val end = "${endDateStr}T${endTimeStr}Z"
                "rtsp://$auth$host:$port/playback/ch$ch?starttime=$start&endtime=$end"
            }
        }
    }

    /**
     * Formats RTSP URL into native vlc:// deep link for Android VLC App.
     */
    fun getVlcDeepLink(rtspUrl: String): String {
        return "vlc://$rtspUrl"
    }
}
