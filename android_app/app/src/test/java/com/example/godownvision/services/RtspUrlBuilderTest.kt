package com.example.godownvision.services

import com.example.godownvision.data.CameraEntity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RtspUrlBuilderTest {

    private val testCamera = CameraEntity(
        id = 1,
        name = "Warehouse Gate",
        location = "Zone A",
        localIp = "192.168.1.100",
        remoteHost = "godown.ddns.net",
        rtspPort = 554,
        httpPort = 80,
        username = "admin",
        password = "pass123",
        channel = 1,
        nvrBrand = "Hikvision"
    )

    @Test
    fun testHikvisionLiveRtspUrl_MainAndSubStream() {
        val mainUrl = RtspUrlBuilder.buildLiveRtspUrl(testCamera, isRemoteMode = false, overrideQuality = "MAIN")
        assertEquals("rtsp://admin:pass123@192.168.1.100:554/Streaming/channels/101", mainUrl)

        val subUrl = RtspUrlBuilder.buildLiveRtspUrl(testCamera, isRemoteMode = false, overrideQuality = "SUB")
        assertEquals("rtsp://admin:pass123@192.168.1.100:554/Streaming/channels/102", subUrl)
    }

    @Test
    fun testHikvisionRemoteModeLiveRtspUrl() {
        val remoteUrl = RtspUrlBuilder.buildLiveRtspUrl(testCamera, isRemoteMode = true, overrideQuality = "MAIN")
        assertEquals("rtsp://admin:pass123@godown.ddns.net:554/Streaming/channels/101", remoteUrl)
    }

    @Test
    fun testDahuaLiveRtspUrl() {
        val dahuaCam = testCamera.copy(nvrBrand = "Dahua")
        val mainUrl = RtspUrlBuilder.buildLiveRtspUrl(dahuaCam, isRemoteMode = false, overrideQuality = "MAIN")
        assertEquals("rtsp://admin:pass123@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0", mainUrl)

        val subUrl = RtspUrlBuilder.buildLiveRtspUrl(dahuaCam, isRemoteMode = false, overrideQuality = "SUB")
        assertEquals("rtsp://admin:pass123@192.168.1.100:554/cam/realmonitor?channel=1&subtype=1", subUrl)
    }

    @Test
    fun testHikvisionPlaybackRtspUrl() {
        val playbackUrl = RtspUrlBuilder.buildPlaybackRtspUrl(
            camera = testCamera,
            isRemoteMode = false,
            startDateStr = "20260804",
            startTimeStr = "090000",
            endDateStr = "20260804",
            endTimeStr = "095959"
        )
        assertEquals("rtsp://admin:pass123@192.168.1.100:554/Streaming/tracks/101?starttime=20260804T090000Z&endtime=20260804T095959Z", playbackUrl)
    }

    @Test
    fun testDahuaPlaybackRtspUrl() {
        val dahuaCam = testCamera.copy(nvrBrand = "Dahua")
        val playbackUrl = RtspUrlBuilder.buildPlaybackRtspUrl(
            camera = dahuaCam,
            isRemoteMode = false,
            startDateStr = "20260804",
            startTimeStr = "090000",
            endDateStr = "20260804",
            endTimeStr = "095959"
        )
        assertEquals("rtsp://admin:pass123@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0&starttime=2026-08-04_09:00:00&endtime=2026-08-04_09:59:59", playbackUrl)
    }

    @Test
    fun testVlcDeepLinkGeneration() {
        val rtspUrl = "rtsp://admin:pass123@192.168.1.100:554/Streaming/channels/101"
        val deepLink = RtspUrlBuilder.getVlcDeepLink(rtspUrl)
        assertEquals("vlc://rtsp://admin:pass123@192.168.1.100:554/Streaming/channels/101", deepLink)
    }
}
