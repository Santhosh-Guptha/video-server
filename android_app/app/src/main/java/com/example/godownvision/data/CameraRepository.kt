package com.example.godownvision.data

import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn

class CameraRepository(context: Context) {
    val vaultRepo = VaultRepository(context)

    val cameras: StateFlow<List<CameraEntity>> = vaultRepo.vaultData
        .map { it.cameras }
        .stateIn(
            scope = CoroutineScope(Dispatchers.IO),
            started = SharingStarted.Eagerly,
            initialValue = vaultRepo.vaultData.value.cameras
        )

    fun insertCamera(camera: CameraEntity) {
        vaultRepo.insertCamera(camera)
    }

    fun deleteCamera(camera: CameraEntity) {
        vaultRepo.deleteCamera(camera)
    }
}
