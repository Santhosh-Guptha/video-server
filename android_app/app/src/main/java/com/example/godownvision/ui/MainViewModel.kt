package com.example.godownvision.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.godownvision.data.AegisVaultData
import com.example.godownvision.data.BookmarkIncident
import com.example.godownvision.data.CameraEntity
import com.example.godownvision.data.CameraRepository
import com.example.godownvision.data.UserFeatures
import com.example.godownvision.data.UserProfile
import com.example.godownvision.security.VaultCryptoEngine
import kotlinx.coroutines.flow.*

sealed class ActiveSession {
    object Unauthenticated : ActiveSession()
    data class Admin(val username: String, val forcePasswordChange: Boolean, val masterRecoveryKey: String = "") : ActiveSession()
    data class User(val profile: UserProfile, val forcePasswordChange: Boolean = false) : ActiveSession()
}

class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = CameraRepository(application)
    val vaultRepo = repository.vaultRepo

    val vaultData: StateFlow<AegisVaultData> = vaultRepo.vaultData

    private val _sessionState = MutableStateFlow<ActiveSession>(ActiveSession.Unauthenticated)
    val sessionState: StateFlow<ActiveSession> = _sessionState.asStateFlow()

    // Dynamically filtered camera list based on logged in user's assigned cameras
    val filteredCameraList: StateFlow<List<CameraEntity>> = combine(
        vaultRepo.vaultData,
        _sessionState
    ) { vault, session ->
        when (session) {
            is ActiveSession.Admin -> vault.cameras
            is ActiveSession.User -> {
                if (session.profile.assignedCameraIds.isEmpty()) {
                    vault.cameras
                } else {
                    vault.cameras.filter { session.profile.assignedCameraIds.contains(it.id) }
                }
            }
            is ActiveSession.Unauthenticated -> emptyList()
        }
    }.stateIn(viewModelScope, SharingStarted.Eagerly, emptyList())

    // Active User Feature Flags Guard
    val activeUserFeatures: StateFlow<UserFeatures> = _sessionState.map { session ->
        when (session) {
            is ActiveSession.Admin -> UserFeatures(liveView = true, playback = true, hdStream = true, snapshotCapture = true, clipDownload = true)
            is ActiveSession.User -> session.profile.features
            is ActiveSession.Unauthenticated -> UserFeatures(liveView = false, playback = false, hdStream = false, snapshotCapture = false, clipDownload = false)
        }
    }.stateIn(viewModelScope, SharingStarted.Eagerly, UserFeatures())

    val canConfigureCameras: StateFlow<Boolean> = _sessionState.map { session ->
        when (session) {
            is ActiveSession.Admin -> true
            is ActiveSession.User -> session.profile.canConfigureCameras
            is ActiveSession.Unauthenticated -> false
        }
    }.stateIn(viewModelScope, SharingStarted.Eagerly, false)

    fun login(usernameInput: String, passwordInput: String): Boolean {
        val inputHash = VaultCryptoEngine.hashPassword(passwordInput)
        val vault = vaultData.value

        // 1. Check Admin Credentials
        if (usernameInput.equals(vault.adminProfile.username, ignoreCase = true)) {
            if (inputHash == vault.adminProfile.passwordHash) {
                _sessionState.value = ActiveSession.Admin(
                    username = vault.adminProfile.username,
                    forcePasswordChange = vault.adminProfile.forcePasswordChange,
                    masterRecoveryKey = vault.adminProfile.masterRecoveryKey
                )
                return true
            }
        }

        // 2. Check Standard User Profiles
        val matchedUser = vault.users.find { it.username.equals(usernameInput, ignoreCase = true) }
        if (matchedUser != null && matchedUser.passwordHash == inputHash) {
            _sessionState.value = ActiveSession.User(profile = matchedUser)
            return true
        }

        return false
    }

    fun logout() {
        _sessionState.value = ActiveSession.Unauthenticated
    }

    fun updatePassword(newPassword: String) {
        val newHash = VaultCryptoEngine.hashPassword(newPassword)
        when (val session = _sessionState.value) {
            is ActiveSession.Admin -> {
                vaultRepo.updateAdminPassword(newHash, clearForceFlag = true)
                _sessionState.value = ActiveSession.Admin(session.username, forcePasswordChange = false, masterRecoveryKey = session.masterRecoveryKey)
            }
            is ActiveSession.User -> {
                val updated = session.profile.copy(passwordHash = newHash)
                vaultRepo.insertUser(updated)
                _sessionState.value = ActiveSession.User(profile = updated, forcePasswordChange = false)
            }
            is ActiveSession.Unauthenticated -> {}
        }
    }

    fun verifyMasterKey(keyInput: String): Boolean {
        return vaultRepo.verifyMasterKey(keyInput)
    }

    fun verifySecurityAnswers(username: String, answers: List<String>): Boolean {
        return vaultRepo.verifySecurityAnswers(username, answers)
    }

    fun resetPasswordWithRecovery(username: String, newPassword: String): Boolean {
        val newHash = VaultCryptoEngine.hashPassword(newPassword)
        return vaultRepo.resetPasswordWithRecovery(username, newHash)
    }

    fun emergencyResetVault() {
        vaultRepo.emergencyResetVault()
        _sessionState.value = ActiveSession.Unauthenticated
    }

    fun saveUser(userProfile: UserProfile) {
        vaultRepo.insertUser(userProfile)
    }

    fun deleteUser(userId: String) {
        vaultRepo.deleteUser(userId)
    }

    fun insertCamera(camera: CameraEntity) {
        repository.insertCamera(camera)
    }

    fun deleteCamera(camera: CameraEntity) {
        repository.deleteCamera(camera)
    }

    fun addBookmark(bookmark: BookmarkIncident) {
        vaultRepo.addBookmark(bookmark)
    }

    fun deleteBookmark(bookmarkId: String) {
        vaultRepo.deleteBookmark(bookmarkId)
    }
}
