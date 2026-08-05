package com.example.godownvision.data

data class SecurityQuestion(
    val question: String,
    val answerHash: String
)

data class UserFeatures(
    val liveView: Boolean = true,
    val playback: Boolean = true,
    val hdStream: Boolean = true,
    val snapshotCapture: Boolean = true,
    val clipDownload: Boolean = true
)

data class UserProfile(
    val userId: String,
    val username: String,
    val passwordHash: String,
    val canConfigureCameras: Boolean = false,
    val features: UserFeatures = UserFeatures(),
    val assignedCameraIds: List<Long> = emptyList(),
    val securityQuestions: List<SecurityQuestion> = emptyList()
)

data class AdminProfile(
    val username: String = "admin",
    val passwordHash: String,
    val masterRecoveryKey: String = "",
    val forcePasswordChange: Boolean = true,
    val securityQuestions: List<SecurityQuestion> = emptyList()
)

data class AegisVaultData(
    val vaultVersion: String = "1.0.0",
    val lastUpdated: Long = System.currentTimeMillis(),
    val adminProfile: AdminProfile,
    val users: List<UserProfile> = emptyList(),
    val cameras: List<CameraEntity> = emptyList()
)
