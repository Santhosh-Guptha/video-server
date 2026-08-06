package com.example.godownvision.data

import android.content.Context
import android.os.Environment
import com.example.godownvision.security.VaultCryptoEngine
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

class VaultRepository(private val context: Context) {

    private fun getVaultCandidateFiles(): List<File> {
        val candidates = mutableListOf<File>()

        // 1. Public Documents (Survives uninstall)
        try {
            val docsDir = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS), "AegisVault")
            if (!docsDir.exists()) docsDir.mkdirs()
            candidates.add(File(docsDir, "aegis_vault.bin"))
        } catch (e: Exception) {}

        // 2. Public Downloads (Survives uninstall)
        try {
            val dlDir = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "AegisVault")
            if (!dlDir.exists()) dlDir.mkdirs()
            candidates.add(File(dlDir, "aegis_vault.bin"))
        } catch (e: Exception) {}

        // 3. /sdcard/AegisVault (Survives uninstall)
        try {
            val sdDir = File(Environment.getExternalStorageDirectory(), "AegisVault")
            if (!sdDir.exists()) sdDir.mkdirs()
            candidates.add(File(sdDir, "aegis_vault.bin"))
        } catch (e: Exception) {}

        // 4. Android/media package directory
        try {
            val mediaDir = File(Environment.getExternalStorageDirectory(), "Android/media/${context.packageName}")
            if (!mediaDir.exists()) mediaDir.mkdirs()
            candidates.add(File(mediaDir, "aegis_vault.bin"))
        } catch (e: Exception) {}

        // 5. Internal filesDir
        candidates.add(File(context.filesDir, "aegis_vault.bin"))

        return candidates
    }

    private val _vaultData = MutableStateFlow<AegisVaultData>(createInitialVault())
    val vaultData: StateFlow<AegisVaultData> = _vaultData

    init {
        loadVault()
    }

    fun generateMasterKey(): String {
        val rand = UUID.randomUUID().toString().replace("-", "").uppercase().take(16)
        return "AEGIS-${rand.substring(0, 4)}-${rand.substring(4, 8)}-${rand.substring(8, 12)}-${rand.substring(12, 16)}"
    }

    @Synchronized
    private fun createInitialVault(): AegisVaultData {
        val defaultAdminHash = VaultCryptoEngine.hashPassword("Admin@123")
        return AegisVaultData(
            adminProfile = AdminProfile(
                username = "admin",
                passwordHash = defaultAdminHash,
                masterRecoveryKey = generateMasterKey(),
                forcePasswordChange = true,
                securityQuestions = emptyList()
            ),
            users = emptyList(),
            cameras = emptyList()
        )
    }

    @Synchronized
    fun loadVault(): AegisVaultData {
        val candidates = getVaultCandidateFiles()
        var foundBytes: ByteArray? = null

        for (file in candidates) {
            if (file.exists() && file.length() > 0L) {
                try {
                    val bytes = file.readBytes()
                    if (bytes.isNotEmpty()) {
                        val testDecrypted = VaultCryptoEngine.decrypt(bytes)
                        if (testDecrypted.isNotBlank()) {
                            foundBytes = bytes
                            break
                        }
                    }
                } catch (e: Exception) {}
            }
        }

        if (foundBytes == null) {
            val initial = createInitialVault()
            saveVault(initial)
            return initial
        }

        try {
            val jsonStr = VaultCryptoEngine.decrypt(foundBytes)
            if (jsonStr.isBlank()) {
                val initial = createInitialVault()
                saveVault(initial)
                return initial
            }

            val root = JSONObject(jsonStr)
            val version = root.optString("vault_version", "1.0.0")
            val lastUpdated = root.optLong("last_updated", System.currentTimeMillis())

            // Parse Admin
            val adminObj = root.optJSONObject("admin_profile")
            val adminHash = adminObj?.optString("password_hash") ?: VaultCryptoEngine.hashPassword("Admin@123")
            val masterKey = adminObj?.optString("master_recovery_key")?.ifBlank { generateMasterKey() } ?: generateMasterKey()
            val forceChange = adminObj?.optBoolean("force_password_change", true) ?: true
            
            val adminQuestionsArray = adminObj?.optJSONArray("security_questions") ?: JSONArray()
            val adminQuestions = mutableListOf<SecurityQuestion>()
            for (i in 0 until adminQuestionsArray.length()) {
                val qObj = adminQuestionsArray.getJSONObject(i)
                adminQuestions.add(
                    SecurityQuestion(
                        question = qObj.optString("question", ""),
                        answerHash = qObj.optString("answer_hash", "")
                    )
                )
            }

            val adminProfile = AdminProfile(
                username = adminObj?.optString("username", "admin") ?: "admin",
                passwordHash = adminHash,
                masterRecoveryKey = masterKey,
                forcePasswordChange = forceChange,
                securityQuestions = adminQuestions
            )

            // Parse Users
            val usersArray = root.optJSONArray("users") ?: JSONArray()
            val usersList = mutableListOf<UserProfile>()
            for (i in 0 until usersArray.length()) {
                val uObj = usersArray.getJSONObject(i)
                val featObj = uObj.optJSONObject("features") ?: JSONObject()
                val feat = UserFeatures(
                    liveView = featObj.optBoolean("live_view", true),
                    playback = featObj.optBoolean("playback", true),
                    hdStream = featObj.optBoolean("hd_stream", true),
                    snapshotCapture = featObj.optBoolean("snapshot_capture", true),
                    clipDownload = featObj.optBoolean("clip_download", true)
                )
                val camArray = uObj.optJSONArray("assigned_camera_ids") ?: JSONArray()
                val camIds = mutableListOf<Long>()
                for (j in 0 until camArray.length()) {
                    camIds.add(camArray.getLong(j))
                }

                val uQuestionsArray = uObj.optJSONArray("security_questions") ?: JSONArray()
                val uQuestions = mutableListOf<SecurityQuestion>()
                for (j in 0 until uQuestionsArray.length()) {
                    val qObj = uQuestionsArray.getJSONObject(j)
                    uQuestions.add(
                        SecurityQuestion(
                            question = qObj.optString("question", ""),
                            answerHash = qObj.optString("answer_hash", "")
                        )
                    )
                }

                usersList.add(
                    UserProfile(
                        userId = uObj.optString("user_id", "usr_$i"),
                        username = uObj.optString("username", "operator"),
                        passwordHash = uObj.optString("password_hash", ""),
                        canConfigureCameras = uObj.optBoolean("can_configure_cameras", false),
                        features = feat,
                        assignedCameraIds = camIds,
                        securityQuestions = uQuestions
                    )
                )
            }

            // Parse Cameras
            val camsArray = root.optJSONArray("cameras") ?: JSONArray()
            val camsList = mutableListOf<CameraEntity>()
            for (i in 0 until camsArray.length()) {
                val cObj = camsArray.getJSONObject(i)
                camsList.add(
                    CameraEntity(
                        id = cObj.optLong("id", (i + 1).toLong()),
                        name = cObj.optString("name", "Camera"),
                        location = cObj.optString("location", ""),
                        localIp = cObj.optString("localIp", ""),
                        remoteHost = cObj.optString("remoteHost", ""),
                        rtspPort = cObj.optInt("rtspPort", 554),
                        httpPort = cObj.optInt("httpPort", 80),
                        username = cObj.optString("username", "admin"),
                        password = cObj.optString("password", ""),
                        channel = cObj.optInt("channel", 1),
                        nvrBrand = cObj.optString("nvrBrand", "HIKVISION"),
                        streamQuality = cObj.optString("streamQuality", "MAIN")
                    )
                )
            }

            val bookmarksArray = root.optJSONArray("bookmarks") ?: JSONArray()
            val bookmarksList = mutableListOf<BookmarkIncident>()
            for (i in 0 until bookmarksArray.length()) {
                val bObj = bookmarksArray.getJSONObject(i)
                bookmarksList.add(
                    BookmarkIncident(
                        id = bObj.optString("id", UUID.randomUUID().toString()),
                        cameraId = bObj.optLong("camera_id", 0L),
                        cameraName = bObj.optString("camera_name", "Camera"),
                        timestamp = bObj.optString("timestamp", ""),
                        note = bObj.optString("note", ""),
                        snapshotBase64 = bObj.optString("snapshot_base64", ""),
                        createdBy = bObj.optString("created_by", "admin"),
                        createdAt = bObj.optLong("created_at", System.currentTimeMillis()),
                        type = bObj.optString("type", "MANUAL_INCIDENT"),
                        status = bObj.optString("status", "UNREVIEWED"),
                        reviewedBy = bObj.optString("reviewed_by", ""),
                        reviewedAt = bObj.optLong("reviewed_at", 0L)
                    )
                )
            }

            val data = AegisVaultData(
                vaultVersion = version,
                lastUpdated = lastUpdated,
                adminProfile = adminProfile,
                users = usersList,
                cameras = camsList,
                bookmarks = bookmarksList
            )
            _vaultData.value = data
            // Mirror restored vault across all persistent locations
            saveVault(data)
            return data
        } catch (e: Exception) {
            val initial = createInitialVault()
            saveVault(initial)
            return initial
        }
    }

    @Synchronized
    fun saveVault(data: AegisVaultData) {
        val root = JSONObject().apply {
            put("vault_version", data.vaultVersion)
            put("last_updated", System.currentTimeMillis())

            put("admin_profile", JSONObject().apply {
                put("username", data.adminProfile.username)
                put("password_hash", data.adminProfile.passwordHash)
                put("master_recovery_key", data.adminProfile.masterRecoveryKey)
                put("force_password_change", data.adminProfile.forcePasswordChange)
                
                val qArr = JSONArray()
                data.adminProfile.securityQuestions.forEach { q ->
                    qArr.put(JSONObject().apply {
                        put("question", q.question)
                        put("answer_hash", q.answerHash)
                    })
                }
                put("security_questions", qArr)
            })

            val usersArr = JSONArray()
            data.users.forEach { u ->
                val uObj = JSONObject().apply {
                    put("user_id", u.userId)
                    put("username", u.username)
                    put("password_hash", u.passwordHash)
                    put("can_configure_cameras", u.canConfigureCameras)
                    put("features", JSONObject().apply {
                        put("live_view", u.features.liveView)
                        put("playback", u.features.playback)
                        put("hd_stream", u.features.hdStream)
                        put("snapshot_capture", u.features.snapshotCapture)
                        put("clip_download", u.features.clipDownload)
                    })
                    val camArr = JSONArray()
                    u.assignedCameraIds.forEach { camArr.put(it) }
                    put("assigned_camera_ids", camArr)

                    val uqArr = JSONArray()
                    u.securityQuestions.forEach { q ->
                        uqArr.put(JSONObject().apply {
                            put("question", q.question)
                            put("answer_hash", q.answerHash)
                        })
                    }
                    put("security_questions", uqArr)
                }
                usersArr.put(uObj)
            }
            put("users", usersArr)

            val camsArr = JSONArray()
            data.cameras.forEach { c ->
                val cObj = JSONObject().apply {
                    put("id", c.id)
                    put("name", c.name)
                    put("location", c.location)
                    put("localIp", c.localIp)
                    put("remoteHost", c.remoteHost)
                    put("rtspPort", c.rtspPort)
                    put("httpPort", c.httpPort)
                    put("username", c.username)
                    put("password", c.password)
                    put("channel", c.channel)
                    put("nvrBrand", c.nvrBrand)
                    put("streamQuality", c.streamQuality)
                }
                camsArr.put(cObj)
            }
            put("cameras", camsArr)

            val bookmarksArr = JSONArray()
            data.bookmarks.forEach { b ->
                val bObj = JSONObject().apply {
                    put("id", b.id)
                    put("camera_id", b.cameraId)
                    put("camera_name", b.cameraName)
                    put("timestamp", b.timestamp)
                    put("note", b.note)
                    put("snapshot_base64", b.snapshotBase64)
                    put("created_by", b.createdBy)
                    put("created_at", b.createdAt)
                    put("type", b.type)
                    put("status", b.status)
                    put("reviewed_by", b.reviewedBy)
                    put("reviewed_at", b.reviewedAt)
                }
                bookmarksArr.put(bObj)
            }
            put("bookmarks", bookmarksArr)
        }

        try {
            val encryptedBytes = VaultCryptoEngine.encrypt(root.toString(2))
            val candidates = getVaultCandidateFiles()
            candidates.forEach { file ->
                try {
                    val parent = file.parentFile
                    if (parent != null && !parent.exists()) {
                        parent.mkdirs()
                    }
                    file.writeBytes(encryptedBytes)
                } catch (e: Exception) {}
            }
            _vaultData.value = data
        } catch (e: Exception) {}
    }

    fun addBookmark(bookmark: BookmarkIncident) {
        val current = _vaultData.value
        val updated = current.bookmarks.filterNot { it.id == bookmark.id } + bookmark
        saveVault(current.copy(bookmarks = updated))
    }

    fun updateBookmarkStatus(bookmarkId: String, newStatus: String, reviewedBy: String = "admin") {
        val current = _vaultData.value
        val updated = current.bookmarks.map { b ->
            if (b.id == bookmarkId) {
                b.copy(
                    status = newStatus,
                    reviewedBy = reviewedBy,
                    reviewedAt = System.currentTimeMillis()
                )
            } else b
        }
        saveVault(current.copy(bookmarks = updated))
    }

    fun deleteBookmark(bookmarkId: String): Boolean {
        val current = _vaultData.value
        val target = current.bookmarks.find { it.id == bookmarkId }
        // Deletion rule: UNREVIEWED events cannot be deleted! Only REVIEWED events can be deleted!
        if (target != null && target.status != "REVIEWED") {
            return false
        }
        val updated = current.bookmarks.filterNot { it.id == bookmarkId }
        saveVault(current.copy(bookmarks = updated))
        return true
    }

    fun updateAdminPassword(newPasswordHash: String, clearForceFlag: Boolean = true) {
        val current = _vaultData.value
        val updatedAdmin = current.adminProfile.copy(
            passwordHash = newPasswordHash,
            forcePasswordChange = if (clearForceFlag) false else current.adminProfile.forcePasswordChange
        )
        saveVault(current.copy(adminProfile = updatedAdmin))
    }

    fun verifyMasterKey(keyInput: String): Boolean {
        val cleanedInput = keyInput.trim().uppercase()
        val storedKey = _vaultData.value.adminProfile.masterRecoveryKey.trim().uppercase()
        return cleanedInput.isNotBlank() && cleanedInput == storedKey
    }

    fun verifySecurityAnswers(username: String, answers: List<String>): Boolean {
        val vault = _vaultData.value
        val targetQuestions: List<SecurityQuestion> = if (username.equals(vault.adminProfile.username, ignoreCase = true)) {
            vault.adminProfile.securityQuestions
        } else {
            vault.users.find { it.username.equals(username, ignoreCase = true) }?.securityQuestions ?: emptyList()
        }

        if (targetQuestions.isEmpty() || answers.size < targetQuestions.size) return false

        for (i in targetQuestions.indices) {
            val inputAnswerHash = VaultCryptoEngine.hashPassword(answers[i].trim().lowercase())
            if (inputAnswerHash != targetQuestions[i].answerHash) {
                return false
            }
        }
        return true
    }

    fun resetPasswordWithRecovery(username: String, newPasswordHash: String): Boolean {
        val current = _vaultData.value
        if (username.equals(current.adminProfile.username, ignoreCase = true)) {
            val updatedAdmin = current.adminProfile.copy(
                passwordHash = newPasswordHash,
                forcePasswordChange = false
            )
            saveVault(current.copy(adminProfile = updatedAdmin))
            return true
        } else {
            val usersList = current.users.toMutableList()
            val uIndex = usersList.indexOfFirst { it.username.equals(username, ignoreCase = true) }
            if (uIndex >= 0) {
                usersList[uIndex] = usersList[uIndex].copy(passwordHash = newPasswordHash)
                saveVault(current.copy(users = usersList))
                return true
            }
        }
        return false
    }

    fun emergencyResetVault() {
        getVaultCandidateFiles().forEach { file ->
            if (file.exists()) {
                try { file.delete() } catch (e: Exception) {}
            }
        }
        val initial = createInitialVault()
        saveVault(initial)
    }

    fun insertUser(user: UserProfile) {
        val current = _vaultData.value.users.toMutableList()
        val existingIndex = current.indexOfFirst { it.userId == user.userId }
        if (existingIndex >= 0) {
            current[existingIndex] = user
        } else {
            current.add(user)
        }
        saveVault(_vaultData.value.copy(users = current))
    }

    fun deleteUser(userId: String) {
        val current = _vaultData.value.users.filter { it.userId != userId }
        saveVault(_vaultData.value.copy(users = current))
    }

    fun insertCamera(camera: CameraEntity) {
        val current = _vaultData.value.cameras.toMutableList()
        val existingIndex = current.indexOfFirst { it.id == camera.id && camera.id != 0L }
        if (existingIndex >= 0) {
            current[existingIndex] = camera
        } else {
            val newId = (current.maxOfOrNull { it.id } ?: 0L) + 1L
            current.add(camera.copy(id = newId))
        }
        saveVault(_vaultData.value.copy(cameras = current))
    }

    fun deleteCamera(camera: CameraEntity) {
        val current = _vaultData.value.cameras.filter { it.id != camera.id }
        saveVault(_vaultData.value.copy(cameras = current))
    }
}
