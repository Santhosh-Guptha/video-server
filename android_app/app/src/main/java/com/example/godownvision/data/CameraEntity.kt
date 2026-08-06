package com.example.godownvision.data

enum class NvrBrand {
    HIKVISION, DAHUA, UNIVIEW, ONVIF, CUSTOM
}

enum class StreamMode {
    LOCAL, REMOTE
}

enum class StreamQuality {
    MAIN, SUB
}

data class CameraEntity(
    val id: Long = 0,
    val name: String,
    val location: String,
    val localIp: String,
    val remoteHost: String,
    val rtspPort: Int = 554,
    val httpPort: Int = 80,
    val username: String,
    val password: String,
    val channel: Int = 1,
    val nvrBrand: String = "HIKVISION",
    val streamQuality: String = "MAIN",
    val isNvr: Boolean = true,
    val customRtspUrl: String = "",
    val createdAt: Long = System.currentTimeMillis()
)
