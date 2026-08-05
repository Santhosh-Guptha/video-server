package com.example.godownvision.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import com.example.godownvision.data.CameraEntity
import com.example.godownvision.data.CameraRepository
import kotlinx.coroutines.flow.StateFlow

class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = CameraRepository(application)

    val cameraList: StateFlow<List<CameraEntity>> = repository.cameras

    fun insertCamera(camera: CameraEntity) {
        repository.insertCamera(camera)
    }

    fun deleteCamera(camera: CameraEntity) {
        repository.deleteCamera(camera)
    }
}
