package com.example.godownvision.data

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONArray
import org.json.JSONObject

class CameraRepository(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("godown_vision_cams", Context.MODE_PRIVATE)
    private val _cameras = MutableStateFlow<List<CameraEntity>>(emptyList())
    val cameras: StateFlow<List<CameraEntity>> = _cameras

    init {
        loadCameras()
    }

    private fun loadCameras() {
        val jsonStr = prefs.getString("camera_list", null)
        if (jsonStr != null) {
            try {
                val array = JSONArray(jsonStr)
                val list = mutableListOf<CameraEntity>()
                for (i in 0 until array.length()) {
                    val obj = array.getJSONObject(i)
                    list.add(
                        CameraEntity(
                            id = obj.optLong("id", (i + 1).toLong()),
                            name = obj.optString("name", "Camera"),
                            location = obj.optString("location", ""),
                            localIp = obj.optString("localIp", ""),
                            remoteHost = obj.optString("remoteHost", ""),
                            rtspPort = obj.optInt("rtspPort", 554),
                            httpPort = obj.optInt("httpPort", 80),
                            username = obj.optString("username", "admin"),
                            password = obj.optString("password", ""),
                            channel = obj.optInt("channel", 1),
                            nvrBrand = obj.optString("nvrBrand", "HIKVISION")
                        )
                    )
                }
                _cameras.value = list
            } catch (e: Exception) {
                _cameras.value = emptyList()
            }
        }
    }

    private fun saveCameras(list: List<CameraEntity>) {
        val array = JSONArray()
        list.forEach { cam ->
            val obj = JSONObject().apply {
                put("id", cam.id)
                put("name", cam.name)
                put("location", cam.location)
                put("localIp", cam.localIp)
                put("remoteHost", cam.remoteHost)
                put("rtspPort", cam.rtspPort)
                put("httpPort", cam.httpPort)
                put("username", cam.username)
                put("password", cam.password)
                put("channel", cam.channel)
                put("nvrBrand", cam.nvrBrand)
            }
            array.put(obj)
        }
        prefs.edit().putString("camera_list", array.toString()).apply()
        _cameras.value = list
    }

    fun insertCamera(camera: CameraEntity) {
        val current = _cameras.value.toMutableList()
        val existingIndex = current.indexOfFirst { it.id == camera.id && camera.id != 0L }
        if (existingIndex >= 0) {
            current[existingIndex] = camera
        } else {
            val newId = (current.maxOfOrNull { it.id } ?: 0L) + 1L
            current.add(camera.copy(id = newId))
        }
        saveCameras(current)
    }

    fun deleteCamera(camera: CameraEntity) {
        val current = _cameras.value.filter { it.id != camera.id }
        saveCameras(current)
    }
}
