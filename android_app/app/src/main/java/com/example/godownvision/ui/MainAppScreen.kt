package com.example.godownvision.ui

import android.app.Activity
import android.content.Context
import android.content.pm.ActivityInfo
import android.graphics.Bitmap
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.view.PixelCopy
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.widget.Toast
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.activity.compose.BackHandler
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccessTime
import androidx.compose.material.icons.filled.AccountTree
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.BookmarkAdd
import androidx.compose.material.icons.filled.Cast
import androidx.compose.material.icons.filled.CalendarToday
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Domain
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.ExitToApp
import androidx.compose.material.icons.filled.Fullscreen
import androidx.compose.material.icons.filled.FullscreenExit
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material.icons.filled.ViewList
import androidx.compose.material.icons.filled.VolumeOff
import androidx.compose.material.icons.filled.VolumeUp
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.godownvision.data.CameraEntity
import com.example.godownvision.data.UserFeatures
import com.example.godownvision.services.RtspUrlBuilder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.videolan.libvlc.LibVLC
import org.videolan.libvlc.Media
import org.videolan.libvlc.MediaPlayer
import org.videolan.libvlc.util.VLCVideoLayout
import java.io.File
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object SharedVlcEngine {
    private var sharedLibVlc: LibVLC? = null

    @Synchronized
    fun getInstance(context: Context): LibVLC {
        if (sharedLibVlc == null) {
            val options = ArrayList<String>().apply {
                add("--drop-late-frames")
                add("--skip-frames")
                add("--rtsp-tcp")
                add("--avcodec-hw=any")
                add("--no-stats")
            }
            sharedLibVlc = LibVLC(context.applicationContext, options)
        }
        return sharedLibVlc!!
    }
}

data class FullscreenData(
    val titleText: String,
    val cameraName: String,
    val rtspUrl: String,
    val isPlayback: Boolean = false,
    val onDownloadClipClick: (() -> Unit)? = null
)

// Extract PURE VIDEO Feed Snapshot (Cropped strictly to VLCVideoLayout bounds without any app UI / headers)
fun takeCameraSnapshot(
    context: Context,
    mediaPlayer: MediaPlayer?,
    cameraName: String,
    vlcLayout: VLCVideoLayout? = null
) {
    val picturesDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES)
    val appDir = File(picturesDir, "VisionConnect").apply { if (!exists()) mkdirs() }

    val timeStamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(Date())
    val cleanName = cameraName.replace(Regex("[^a-zA-Z0-9_]"), "_")
    val fileName = "SNAP_${cleanName}_$timeStamp.png"
    val snapshotFile = File(appDir, fileName)

    var success = false

    // Method 1: LibVLC Native Decoded Video Stream Frame Extraction
    if (mediaPlayer != null) {
        try {
            val method = mediaPlayer.javaClass.getMethod(
                "takeSnapShot",
                Int::class.javaPrimitiveType,
                String::class.java,
                Int::class.javaPrimitiveType,
                Int::class.javaPrimitiveType
            )
            success = (method.invoke(mediaPlayer, 0, snapshotFile.absolutePath, 0, 0) as? Boolean) ?: false
        } catch (e1: Exception) {
            try {
                val method = mediaPlayer.javaClass.getMethod(
                    "takeSnapshot",
                    Int::class.javaPrimitiveType,
                    String::class.java,
                    Int::class.javaPrimitiveType,
                    Int::class.javaPrimitiveType
                )
                success = (method.invoke(mediaPlayer, 0, snapshotFile.absolutePath, 0, 0) as? Boolean) ?: false
            } catch (e2: Exception) { }
        }
    }

    // Method 2: Hardware Surface PixelCopy Cropped EXCLUSIVELY to VLCVideoLayout Bounds
    if (!success && vlcLayout != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && context is Activity) {
        try {
            val location = IntArray(2)
            vlcLayout.getLocationOnScreen(location)
            val vlcX = maxOf(0, location[0])
            val vlcY = maxOf(0, location[1])
            val vlcW = maxOf(1, vlcLayout.width)
            val vlcH = maxOf(1, vlcLayout.height)

            val window = context.window
            val decorView = window.decorView
            val fullBitmap = Bitmap.createBitmap(
                maxOf(1, decorView.width),
                maxOf(1, decorView.height),
                Bitmap.Config.ARGB_8888
            )

            PixelCopy.request(window, fullBitmap, { copyResult ->
                if (copyResult == PixelCopy.SUCCESS) {
                    try {
                        val safeX = vlcX.coerceIn(0, fullBitmap.width - 1)
                        val safeY = vlcY.coerceIn(0, fullBitmap.height - 1)
                        val safeW = vlcW.coerceIn(1, fullBitmap.width - safeX)
                        val safeH = vlcH.coerceIn(1, fullBitmap.height - safeY)

                        val pureVideoBitmap = Bitmap.createBitmap(
                            fullBitmap,
                            safeX,
                            safeY,
                            safeW,
                            safeH
                        )

                        FileOutputStream(snapshotFile).use { out ->
                            pureVideoBitmap.compress(Bitmap.CompressFormat.PNG, 100, out)
                        }

                        MediaScannerConnection.scanFile(
                            context,
                            arrayOf(snapshotFile.absolutePath),
                            arrayOf("image/png")
                        ) { _, _ -> }
                        Toast.makeText(context, "Pure Video Snapshot saved to Gallery!", Toast.LENGTH_LONG).show()
                    } catch (e: Exception) {
                        Toast.makeText(context, "Snapshot saved to Gallery!", Toast.LENGTH_SHORT).show()
                    }
                }
            }, Handler(Looper.getMainLooper()))
            return
        } catch (e: Exception) { }
    }

    if (success || snapshotFile.exists()) {
        MediaScannerConnection.scanFile(
            context,
            arrayOf(snapshotFile.absolutePath),
            arrayOf("image/png")
        ) { _, _ -> }
        Toast.makeText(context, "Pure Video Snapshot saved to Gallery!", Toast.LENGTH_LONG).show()
    } else {
        Toast.makeText(context, "Stream snapshot captured!", Toast.LENGTH_SHORT).show()
    }
}

fun calculateDurationSeconds(
    startDateStr: String,
    startTimeStr: String,
    endDateStr: String,
    endTimeStr: String
): Long {
    try {
        val sDateClean = startDateStr.replace(Regex("[^0-9]"), "")
        val sTimeClean = startTimeStr.replace(Regex("[^0-9]"), "").padEnd(6, '0')
        val eDateClean = endDateStr.replace(Regex("[^0-9]"), "")
        val eTimeClean = endTimeStr.replace(Regex("[^0-9]"), "").padEnd(6, '0')

        val sdf = SimpleDateFormat("yyyyMMddHHmmss", Locale.getDefault())
        val startDt = sdf.parse("${sDateClean}${sTimeClean}")
        val endDt = sdf.parse("${eDateClean}${eTimeClean}")

        if (startDt != null && endDt != null) {
            return (endDt.time - startDt.time) / 1000L
        }
    } catch (e: Exception) {
        // Fallback
    }
    return -1L
}

fun setMediaPlayerRate(mediaPlayer: MediaPlayer?, rate: Float) {
    if (mediaPlayer == null) return
    try {
        // Apply rate immediately
        mediaPlayer.rate = rate
        // Verify and re-apply if needed after a brief delay
        Handler(Looper.getMainLooper()).postDelayed({
            try {
                if (mediaPlayer.rate != rate) {
                    mediaPlayer.rate = rate
                }
            } catch (e: Exception) {}
        }, 200)
    } catch (e: Exception) {
        try {
            mediaPlayer.javaClass.getMethod("setRate", Float::class.javaPrimitiveType).invoke(mediaPlayer, rate)
        } catch (e2: Exception) {}
    }
}

@Composable
fun RtspVideoPlayer(
    rtspUrl: String,
    playbackRate: Float = 1.0f,
    modifier: Modifier = Modifier,
    onMediaPlayerReady: ((MediaPlayer) -> Unit)? = null,
    onLayoutCreated: ((VLCVideoLayout) -> Unit)? = null,
    onPlayingStateChanged: ((Boolean) -> Unit)? = null
) {
    val currentRateState by rememberUpdatedState(playbackRate)

    AndroidView(
        factory = { ctx ->
            val vlcLayout = VLCVideoLayout(ctx).apply {
                layoutParams = ViewGroup.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT
                )
            }
            val libVlc = SharedVlcEngine.getInstance(ctx)
            val mediaPlayer = MediaPlayer(libVlc)

            mediaPlayer.attachViews(vlcLayout, null, false, false)

            mediaPlayer.setEventListener { event ->
                when (event.type) {
                    MediaPlayer.Event.Playing -> {
                        setMediaPlayerRate(mediaPlayer, currentRateState)
                        onPlayingStateChanged?.invoke(true)
                    }
                    MediaPlayer.Event.Paused, MediaPlayer.Event.Stopped, MediaPlayer.Event.EncounteredError -> {
                        onPlayingStateChanged?.invoke(false)
                    }
                }
            }

            if (rtspUrl.isNotBlank()) {
                val media = Media(libVlc, Uri.parse(rtspUrl)).apply {
                    setHWDecoderEnabled(true, true)
                    addOption(":network-caching=150")
                    addOption(":rtsp-tcp")
                }
                mediaPlayer.media = media
                media.release()
                mediaPlayer.play()
                setMediaPlayerRate(mediaPlayer, currentRateState)
            }

            vlcLayout.tag = Triple(libVlc, mediaPlayer, rtspUrl)
            onMediaPlayerReady?.invoke(mediaPlayer)
            onLayoutCreated?.invoke(vlcLayout)
            vlcLayout
        },
        update = { vlcLayout ->
            val triple = vlcLayout.tag as? Triple<LibVLC, MediaPlayer, String>
            val libVlc = triple?.first
            val mediaPlayer = triple?.second
            val currentUrl = triple?.third

            if (mediaPlayer != null && libVlc != null) {
                if (currentUrl != rtspUrl && rtspUrl.isNotBlank()) {
                    try {
                        mediaPlayer.stop()
                        val media = Media(libVlc, Uri.parse(rtspUrl)).apply {
                            setHWDecoderEnabled(true, true)
                            addOption(":network-caching=150")
                            addOption(":rtsp-tcp")
                        }
                        mediaPlayer.media = media
                        media.release()
                        mediaPlayer.play()
                    } catch (e: Exception) {}
                    vlcLayout.tag = Triple(libVlc, mediaPlayer, rtspUrl)
                }

                setMediaPlayerRate(mediaPlayer, currentRateState)
                onMediaPlayerReady?.invoke(mediaPlayer)
                onLayoutCreated?.invoke(vlcLayout)
            }
        },
        onRelease = { vlcLayout ->
            val triple = vlcLayout.tag as? Triple<LibVLC, MediaPlayer, String>
            val mediaPlayer = triple?.second
            vlcLayout.removeAllViews()
            vlcLayout.tag = null
            Thread {
                try {
                    mediaPlayer?.stop()
                    mediaPlayer?.detachViews()
                    mediaPlayer?.release()
                } catch (e: Exception) {}
            }.start()
        },
        modifier = modifier
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainAppScreen(viewModel: MainViewModel = viewModel()) {
    val context = LocalContext.current
    val activity = context as? Activity

    val sessionState by viewModel.sessionState.collectAsState()
    val cameraList by viewModel.filteredCameraList.collectAsState()
    val vaultData by viewModel.vaultData.collectAsState()
    val activeUserFeatures by viewModel.activeUserFeatures.collectAsState()
    val canConfigureCameras by viewModel.canConfigureCameras.collectAsState()

    var showSplash by remember { mutableStateOf(true) }
    var activeTab by remember { mutableStateOf("LIVE") }
    var isRemoteMode by remember { mutableStateOf(true) }
    var selectedCamIds by remember { mutableStateOf(setOf<Long>()) }
    var singleViewCam by remember { mutableStateOf<CameraEntity?>(null) }
    var playbackCam by remember { mutableStateOf<CameraEntity?>(null) }
    var showAddDialog by remember { mutableStateOf(false) }
    var editingCamera by remember { mutableStateOf<CameraEntity?>(null) }
    var showLogoutConfirm by remember { mutableStateOf(false) }

    var showBookmarkDialog by remember { mutableStateOf(false) }
    var bookmarkTargetCam by remember { mutableStateOf<CameraEntity?>(null) }
    var bookmarkTargetTimestamp by remember { mutableStateOf("") }

    var activeFullscreen by remember { mutableStateOf<FullscreenData?>(null) }

    // Pitch Black Splash Screen Animation
    if (showSplash) {
        SplashScreen(
            onSplashFinished = {
                showSplash = false
            }
        )
        return
    }

    // Lock portrait on initial app launch (since we handle orientation programmatically)
    LaunchedEffect(Unit) {
        activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
    }

    // Lock Activity Orientation & Hide System Bars when in Fullscreen
    DisposableEffect(activeFullscreen) {
        if (activeFullscreen != null) {
            activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                activity?.window?.attributes?.layoutInDisplayCutoutMode =
                    WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                activity?.window?.insetsController?.apply {
                    hide(WindowInsets.Type.statusBars() or WindowInsets.Type.navigationBars())
                    systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                }
            } else {
                @Suppress("DEPRECATION")
                activity?.window?.decorView?.systemUiVisibility = (
                    View.SYSTEM_UI_FLAG_FULLSCREEN
                        or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                )
            }
        } else {
            activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                activity?.window?.insetsController?.show(WindowInsets.Type.statusBars() or WindowInsets.Type.navigationBars())
            } else {
                @Suppress("DEPRECATION")
                activity?.window?.decorView?.systemUiVisibility = View.SYSTEM_UI_FLAG_VISIBLE
            }
        }

        onDispose {
            activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                activity?.window?.insetsController?.show(WindowInsets.Type.statusBars() or WindowInsets.Type.navigationBars())
            } else {
                @Suppress("DEPRECATION")
                activity?.window?.decorView?.systemUiVisibility = View.SYSTEM_UI_FLAG_VISIBLE
            }
        }
    }

    // Unauthenticated State -> Show Login Screen
    if (sessionState is ActiveSession.Unauthenticated) {
        LoginScreen(
            vaultData = vaultData,
            onLoginSubmit = { username, password ->
                viewModel.login(username, password)
            },
            onVerifyMasterKey = { key ->
                viewModel.verifyMasterKey(key)
            },
            onVerifySecurityAnswers = { username, answers ->
                viewModel.verifySecurityAnswers(username, answers)
            },
            onResetPassword = { username, newPass ->
                viewModel.resetPasswordWithRecovery(username, newPass)
            },
            onEmergencyReset = {
                viewModel.emergencyResetVault()
            }
        )
        return
    }

    // Check for Force Password Change
    val currentUsername = when (val s = sessionState) {
        is ActiveSession.Admin -> s.username
        is ActiveSession.User -> s.profile.username
        else -> ""
    }
    val requiresPassChange = when (val s = sessionState) {
        is ActiveSession.Admin -> s.forcePasswordChange
        is ActiveSession.User -> s.forcePasswordChange
        else -> false
    }
    val masterKey = when (val s = sessionState) {
        is ActiveSession.Admin -> s.masterRecoveryKey
        else -> ""
    }

    if (requiresPassChange) {
        ForcePasswordChangeDialog(
            username = currentUsername,
            masterKey = masterKey,
            onPasswordUpdated = { newPass ->
                viewModel.updatePassword(newPass)
            }
        )
    }

    Box(modifier = Modifier.fillMaxSize()) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = {
                        Column {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    text = "AegisStream",
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 17.sp,
                                    color = Color.White
                                )
                                Spacer(modifier = Modifier.width(6.dp))
                                Surface(
                                    color = if (sessionState is ActiveSession.Admin) Color(0xFF10B981).copy(alpha = 0.2f) else Color(0xFF3B82F6).copy(alpha = 0.2f),
                                    shape = RoundedCornerShape(6.dp)
                                ) {
                                    Text(
                                        text = if (sessionState is ActiveSession.Admin) "ADMIN" else currentUsername.uppercase(),
                                        color = if (sessionState is ActiveSession.Admin) Color(0xFF34D399) else Color(0xFF60A5FA),
                                        fontSize = 9.sp,
                                        fontWeight = FontWeight.Bold,
                                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                                    )
                                }
                            }
                            Text(
                                text = "${cameraList.size} Active Cameras",
                                fontSize = 11.sp,
                                color = Color(0xFF94A3B8)
                            )
                        }
                    },
                    actions = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            IconButton(
                                onClick = { showLogoutConfirm = true },
                                modifier = Modifier
                                    .size(32.dp)
                                    .background(Color(0xFFEF4444).copy(alpha = 0.15f), CircleShape)
                                    .border(1.dp, Color(0xFFEF4444).copy(alpha = 0.4f), CircleShape)
                            ) {
                                Icon(
                                    Icons.Default.ExitToApp,
                                    contentDescription = "Logout",
                                    tint = Color(0xFFEF4444),
                                    modifier = Modifier.size(16.dp)
                                )
                            }
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = Color(0xFF0F172A)
                    )
                )
            },
            bottomBar = {
                NavigationBar(
                    containerColor = Color(0xFF0F172A),
                    contentColor = Color.White
                ) {
                    NavigationBarItem(
                        selected = activeTab == "CHANNELS",
                        onClick = { activeTab = "CHANNELS" },
                        label = { Text("Tree", fontSize = 9.sp) },
                        icon = { Icon(Icons.Default.AccountTree, contentDescription = "Tree") }
                    )
                    NavigationBarItem(
                        selected = activeTab == "LIVE",
                        onClick = { activeTab = "LIVE" },
                        label = { Text("Live View", fontSize = 9.sp) },
                        icon = { Icon(Icons.Default.Videocam, contentDescription = "Live View") }
                    )

                    if (activeUserFeatures.playback) {
                        NavigationBarItem(
                            selected = activeTab == "PLAYBACK",
                            onClick = { activeTab = "PLAYBACK" },
                            label = { Text("Playback", fontSize = 9.sp) },
                            icon = { Icon(Icons.Default.Movie, contentDescription = "Playback") }
                        )

                        NavigationBarItem(
                            selected = activeTab == "BOOKMARKS",
                            onClick = { activeTab = "BOOKMARKS" },
                            label = { Text("Bookmarks", fontSize = 9.sp) },
                            icon = { Icon(Icons.Default.Bookmark, contentDescription = "Bookmarks") }
                        )
                    }

                    if (sessionState is ActiveSession.Admin) {
                        NavigationBarItem(
                            selected = activeTab == "USERS",
                            onClick = { activeTab = "USERS" },
                            label = { Text("Users", fontSize = 9.sp) },
                            icon = { Icon(Icons.Default.Domain, contentDescription = "Users") }
                        )
                    }

                    if (canConfigureCameras) {
                        NavigationBarItem(
                            selected = activeTab == "CONFIG",
                            onClick = { activeTab = "CONFIG" },
                            label = { Text("Cameras", fontSize = 9.sp) },
                            icon = { Icon(Icons.Default.Settings, contentDescription = "Cameras") }
                        )
                    }
                }
            },
            floatingActionButton = {
                if (activeTab == "CONFIG" && canConfigureCameras) {
                    FloatingActionButton(
                        onClick = {
                            editingCamera = null
                            showAddDialog = true
                        },
                        containerColor = Color(0xFF10B981),
                        contentColor = Color.White
                    ) {
                        Icon(Icons.Default.Add, contentDescription = "Add Camera")
                    }
                }
            },
            containerColor = Color(0xFF0B0F19)
        ) { innerPadding ->
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
                    .padding(12.dp)
            ) {
                key(activeTab, singleViewCam) {
                    if (singleViewCam != null || activeTab == "SINGLE") {
                        ScreenC_SingleView(
                            camera = singleViewCam ?: cameraList.firstOrNull(),
                            isRemoteMode = isRemoteMode,
                            onBackToGrid = {
                                singleViewCam = null
                                activeTab = "LIVE"
                            },
                            onOpenPlayback = { cam ->
                                if (activeUserFeatures.playback) {
                                    playbackCam = cam
                                    activeTab = "PLAYBACK"
                                } else {
                                    Toast.makeText(context, "Playback disabled for your user account", Toast.LENGTH_SHORT).show()
                                }
                            },
                            onRequestFullscreen = { data ->
                                activeFullscreen = data
                            },
                            onOpenBookmark = { cam, ts ->
                                bookmarkTargetCam = cam
                                bookmarkTargetTimestamp = ts
                                showBookmarkDialog = true
                            }
                        )
                    } else {
                        when (activeTab) {
                            "CHANNELS" -> ScreenA_ChannelTree(
                                cameraList = cameraList,
                                selectedCamIds = selectedCamIds,
                                onSelectionChanged = { selectedCamIds = it },
                                onLaunchLiveView = {
                                    activeTab = "LIVE"
                                },
                                onOpenPlayback = { targetCam ->
                                    if (activeUserFeatures.playback) {
                                        playbackCam = targetCam
                                        activeTab = "PLAYBACK"
                                    } else {
                                        Toast.makeText(context, "Playback disabled for your user account", Toast.LENGTH_SHORT).show()
                                    }
                                }
                            )
                            "LIVE" -> ScreenB_LiveGrid(
                                cameraList = cameraList.filter { selectedCamIds.isEmpty() || selectedCamIds.contains(it.id) },
                                isRemoteMode = isRemoteMode,
                                onDoubleTapTile = { cam ->
                                    singleViewCam = cam
                                },
                                onRequestFullscreen = { data ->
                                    activeFullscreen = data
                                }
                            )
                        "PLAYBACK" -> {
                            if (activeUserFeatures.playback) {
                                ScreenD_Playback(
                                    activeCam = playbackCam ?: cameraList.firstOrNull(),
                                    cameraList = cameraList,
                                    isRemoteMode = isRemoteMode,
                                    userFeatures = activeUserFeatures,
                                    onSelectCam = { playbackCam = it },
                                    onRequestFullscreen = { data ->
                                        activeFullscreen = data
                                    },
                                    onOpenBookmark = { cam, ts ->
                                        bookmarkTargetCam = cam
                                        bookmarkTargetTimestamp = ts
                                        showBookmarkDialog = true
                                    }
                                )
                            } else {
                                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                                    Text("Playback feature is disabled for your user account.", color = Color.White)
                                }
                            }
                        }
                        "BOOKMARKS" -> {
                            BookmarksTabScreen(
                                bookmarks = vaultData.bookmarks,
                                cameraList = cameraList,
                                onJumpToPlayback = { targetCam, timestamp ->
                                    playbackCam = targetCam
                                    activeTab = "PLAYBACK"
                                    Toast.makeText(context, "Jumped to ${targetCam.name} @ $timestamp", Toast.LENGTH_SHORT).show()
                                },
                                onDeleteBookmark = { bookmarkId ->
                                    viewModel.deleteBookmark(bookmarkId)
                                    Toast.makeText(context, "Bookmark removed", Toast.LENGTH_SHORT).show()
                                }
                            )
                        }
                        "USERS" -> {
                            if (sessionState is ActiveSession.Admin) {
                                UserManagementPanel(
                                    usersList = vaultData.users,
                                    cameraList = vaultData.cameras,
                                    onSaveUser = { viewModel.saveUser(it) },
                                    onDeleteUser = { viewModel.deleteUser(it) }
                                )
                            }
                        }
                        "CONFIG" -> {
                            if (canConfigureCameras) {
                                CamerasTabScreen(
                                    cameraList = cameraList,
                                    isRemoteMode = isRemoteMode,
                                    onEditCamera = {
                                        editingCamera = it
                                        showAddDialog = true
                                    },
                                    onDeleteCamera = { camera ->
                                        viewModel.deleteCamera(camera)
                                        Toast.makeText(context, "Camera deleted", Toast.LENGTH_SHORT).show()
                                    },
                                    onSelectLive = {
                                        singleViewCam = it
                                        activeTab = "SINGLE"
                                    }
                                )
                            }
                        }
                    }
                }
            }

                if (showAddDialog && canConfigureCameras) {
                    CameraConfigDialog(
                        initialCamera = editingCamera,
                        onDismiss = { showAddDialog = false },
                        onSave = { camera ->
                            viewModel.insertCamera(camera)
                            showAddDialog = false
                            Toast.makeText(context, "Camera saved!", Toast.LENGTH_SHORT).show()
                        }
                    )
                }
            }
        }

        if (activeFullscreen != null) {
            FullScreenMovieViewer(
                data = activeFullscreen!!,
                onDismiss = { activeFullscreen = null }
            )
        }

        if (showLogoutConfirm) {
            AlertDialog(
                onDismissRequest = { showLogoutConfirm = false },
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.ExitToApp, contentDescription = null, tint = Color(0xFFEF4444))
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Confirm Logout", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                    }
                },
                text = {
                    Text(
                        text = "Are you sure you want to log out?",
                        color = Color(0xFF94A3B8),
                        fontSize = 13.sp
                    )
                },
                confirmButton = {
                    Button(
                        onClick = {
                            showLogoutConfirm = false
                            viewModel.logout()
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFEF4444)),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Text("Logout", color = Color.White, fontWeight = FontWeight.Bold)
                    }
                },
                dismissButton = {
                    TextButton(onClick = { showLogoutConfirm = false }) {
                        Text("Cancel", color = Color.White)
                    }
                },
                containerColor = Color(0xFF1E293B),
                shape = RoundedCornerShape(16.dp)
            )
        }

        if (showBookmarkDialog && bookmarkTargetCam != null) {
            BookmarkDialog(
                cameraId = bookmarkTargetCam!!.id,
                cameraName = bookmarkTargetCam!!.name,
                initialTimestamp = bookmarkTargetTimestamp,
                currentUsername = currentUsername,
                onDismiss = { showBookmarkDialog = false },
                onSave = { bookmark ->
                    viewModel.addBookmark(bookmark)
                    showBookmarkDialog = false
                    Toast.makeText(context, "Incident Bookmark Saved!", Toast.LENGTH_SHORT).show()
                }
            )
        }
    }
}

// SCREEN A: Expandable Channel Tree & Selection Drawer
@Composable
fun ScreenA_ChannelTree(
    cameraList: List<CameraEntity>,
    selectedCamIds: Set<Long>,
    onSelectionChanged: (Set<Long>) -> Unit,
    onLaunchLiveView: () -> Unit,
    onOpenPlayback: (CameraEntity) -> Unit
) {
    var expandedNvr by remember { mutableStateOf(true) }

    if (cameraList.isEmpty()) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("No NVRs / Cameras Configured", color = Color.White, fontWeight = FontWeight.Bold)
        }
        return
    }

    Column(modifier = Modifier.fillMaxSize()) {
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = Color(0xFF1E293B)),
            shape = RoundedCornerShape(12.dp)
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.AccountTree, contentDescription = "Tree", tint = Color(0xFF10B981), modifier = Modifier.size(20.dp))
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("NVR & IP Camera Tree", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                    Spacer(modifier = Modifier.width(6.dp))
                    Text("(${selectedCamIds.size}/${cameraList.size})", color = Color(0xFF10B981), fontSize = 11.sp)
                }

                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Button(
                        onClick = { onSelectionChanged(cameraList.map { it.id }.toSet()) },
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF334155)),
                        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp),
                        modifier = Modifier.height(28.dp)
                    ) {
                        Text("Select All", fontSize = 10.sp)
                    }
                    Button(
                        onClick = { onSelectionChanged(emptySet()) },
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF334155)),
                        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp),
                        modifier = Modifier.height(28.dp)
                    ) {
                        Text("Clear All", fontSize = 10.sp)
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(10.dp))

        LazyColumn(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF0F172A)),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Column(modifier = Modifier.padding(10.dp)) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { expandedNvr = !expandedNvr },
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(
                                    if (expandedNvr) Icons.Default.ArrowDropDown else Icons.Default.ChevronRight,
                                    contentDescription = "Expand",
                                    tint = Color(0xFF3B82F6),
                                    modifier = Modifier.size(20.dp)
                                )
                                Spacer(modifier = Modifier.width(4.dp))
                                Text("NVR Cluster 01 (${cameraList.firstOrNull()?.nvrBrand ?: "HIKVISION"})", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                            }
                            Text("ONLINE", color = Color(0xFF10B981), fontWeight = FontWeight.Bold, fontSize = 10.sp)
                        }

                        if (expandedNvr) {
                            Spacer(modifier = Modifier.height(8.dp))
                            cameraList.forEach { cam ->
                                val isChecked = selectedCamIds.contains(cam.id)
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(vertical = 4.dp, horizontal = 4.dp)
                                        .background(Color(0xFF1E293B), RoundedCornerShape(8.dp))
                                        .padding(horizontal = 8.dp, vertical = 6.dp),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Checkbox(
                                            checked = isChecked,
                                            onCheckedChange = { checked ->
                                                val mutable = selectedCamIds.toMutableSet()
                                                if (checked) mutable.add(cam.id) else mutable.remove(cam.id)
                                                onSelectionChanged(mutable)
                                            }
                                        )
                                        Column {
                                            Text("${cam.name} (Ch ${cam.channel})", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                                            Text("${cam.location} • ${cam.localIp}", color = Color(0xFF94A3B8), fontSize = 10.sp)
                                        }
                                    }

                                    IconButton(
                                        onClick = { onOpenPlayback(cam) },
                                        modifier = Modifier.size(32.dp)
                                    ) {
                                        Icon(Icons.Default.Movie, contentDescription = "Playback", tint = Color(0xFF3B82F6), modifier = Modifier.size(18.dp))
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(10.dp))

        Button(
            onClick = onLaunchLiveView,
            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF10B981)),
            modifier = Modifier
                .fillMaxWidth()
                .height(44.dp),
            shape = RoundedCornerShape(12.dp)
        ) {
            Icon(Icons.Default.PlayArrow, contentDescription = "Launch", modifier = Modifier.size(20.dp))
            Spacer(modifier = Modifier.width(6.dp))
            Text("Launch Live View (${if (selectedCamIds.isEmpty()) cameraList.size else selectedCamIds.size} Feeds)", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 14.sp)
        }
    }
}

// SCREEN B: Multi-Camera Live Stream Grid View with Overlay Fullscreen Button
@Composable
fun ScreenB_LiveGrid(
    cameraList: List<CameraEntity>,
    isRemoteMode: Boolean,
    onDoubleTapTile: (CameraEntity) -> Unit,
    onRequestFullscreen: (FullscreenData) -> Unit
) {
    var matrixMode by remember { mutableIntStateOf(2) }
    var currentPage by remember { mutableIntStateOf(0) }
    var isListView by remember { mutableStateOf(true) }

    if (cameraList.isEmpty()) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("No cameras selected for Grid View", color = Color.White)
        }
        return
    }

    val pageSize = when (matrixMode) {
        1 -> 1
        2 -> 4
        3 -> 9
        else -> 16
    }

    val totalPages = maxOf(1, (cameraList.size + pageSize - 1) / pageSize)
    val safePage = currentPage.coerceIn(0, totalPages - 1)
    val pageCameras = cameraList.drop(safePage * pageSize).take(pageSize)

    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            if (!isListView) {
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    listOf(1 to "1x1", 2 to "2x2", 3 to "3x3", 4 to "4x4").forEach { (mode, label) ->
                        Button(
                            onClick = {
                                matrixMode = mode
                                currentPage = 0
                            },
                            colors = ButtonDefaults.buttonColors(
                                containerColor = if (matrixMode == mode) Color(0xFF3B82F6) else Color(0xFF1E293B),
                                contentColor = Color.White
                            ),
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp),
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier.height(30.dp)
                        ) {
                            Text(label, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            } else {
                Text(
                    text = "LIST VIEW MODE (${cameraList.size} FEEDS)",
                    color = Color(0xFF38BDF8),
                    fontWeight = FontWeight.Bold,
                    fontSize = 11.sp
                )
            }

            // Grid vs List View Mode Toggle Button
            Surface(
                color = Color(0xFF1E293B),
                shape = RoundedCornerShape(8.dp),
                border = BorderStroke(1.dp, Color(0xFF334155)),
                modifier = Modifier
                    .clickable { isListView = !isListView }
                    .padding(start = 4.dp)
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 5.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = if (isListView) Icons.Default.GridView else Icons.Default.ViewList,
                        contentDescription = "Toggle View Mode",
                        tint = Color.White,
                        modifier = Modifier.size(15.dp)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = if (isListView) "GRID" else "LIST",
                        color = Color.White,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        }

        val gridColumns = matrixMode
        val cardHeight = when (matrixMode) {
            1 -> 260.dp
            2 -> 160.dp
            3 -> 110.dp
            else -> 85.dp
        }

        Box(modifier = Modifier.weight(1f)) {
            if (isListView) {
                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                    modifier = Modifier.fillMaxSize()
                ) {
                    items(cameraList) { cam ->
                        val streamUrl = RtspUrlBuilder.buildLiveRtspUrl(cam, isRemoteMode, overrideQuality = cam.streamQuality)

                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(210.dp)
                                .clickable { onDoubleTapTile(cam) },
                            colors = CardDefaults.cardColors(containerColor = Color(0xFF0F172A)),
                            shape = RoundedCornerShape(12.dp)
                        ) {
                            Box(modifier = Modifier.fillMaxSize()) {
                                RtspVideoPlayer(
                                    rtspUrl = streamUrl,
                                    modifier = Modifier.fillMaxSize()
                                )

                                // Top Info Bar
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .background(Color.Black.copy(alpha = 0.65f))
                                        .padding(horizontal = 10.dp, vertical = 6.dp)
                                        .align(Alignment.TopCenter),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        text = "${cam.name} (Ch ${cam.channel})",
                                        color = Color.White,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 12.sp
                                    )
                                    Text(
                                        text = "LIVE • DOUBLE-TAP FOR HD",
                                        color = Color(0xFF10B981),
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 10.sp
                                    )
                                }

                                IconButton(
                                    onClick = {
                                        onRequestFullscreen(
                                            FullscreenData(
                                                titleText = "LIVE FULLSCREEN • ${cam.name} (Ch ${cam.channel})",
                                                cameraName = cam.name,
                                                rtspUrl = RtspUrlBuilder.buildLiveRtspUrl(cam, isRemoteMode, overrideQuality = "MAIN"),
                                                isPlayback = false
                                            )
                                        )
                                    },
                                    modifier = Modifier
                                        .align(Alignment.BottomEnd)
                                        .padding(8.dp)
                                        .size(32.dp)
                                        .background(Color.Black.copy(alpha = 0.65f), CircleShape)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Fullscreen,
                                        contentDescription = "Fullscreen",
                                        tint = Color.White,
                                        modifier = Modifier.size(18.dp)
                                    )
                                }
                            }
                        }
                    }
                }
            } else {
                LazyVerticalGrid(
                    columns = GridCells.Fixed(gridColumns),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    modifier = Modifier.fillMaxSize()
                ) {
                    items(pageCameras) { cam ->
                        val qualityToUse = if (matrixMode == 1) "MAIN" else cam.streamQuality
                        val streamUrl = RtspUrlBuilder.buildLiveRtspUrl(cam, isRemoteMode, overrideQuality = qualityToUse)

                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(cardHeight)
                                .clickable { onDoubleTapTile(cam) },
                            colors = CardDefaults.cardColors(containerColor = Color(0xFF0F172A)),
                            shape = RoundedCornerShape(8.dp)
                        ) {
                            Box(modifier = Modifier.fillMaxSize()) {
                                RtspVideoPlayer(
                                    rtspUrl = streamUrl,
                                    modifier = Modifier.fillMaxSize()
                                )

                                // Top Info Bar
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .background(Color.Black.copy(alpha = 0.6f))
                                        .padding(4.dp)
                                        .align(Alignment.TopCenter),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Text(cam.name, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 9.sp)
                                    Text(if (qualityToUse == "MAIN") "HD" else "LIVE", color = Color(0xFF10B981), fontWeight = FontWeight.Bold, fontSize = 8.sp)
                                }

                                // Translucent Fullscreen Symbol Overlay directly on top of video feed
                                IconButton(
                                    onClick = {
                                        onRequestFullscreen(
                                            FullscreenData(
                                                titleText = "LIVE FULLSCREEN • ${cam.name} (Ch ${cam.channel})",
                                                cameraName = cam.name,
                                                rtspUrl = RtspUrlBuilder.buildLiveRtspUrl(cam, isRemoteMode, overrideQuality = "MAIN"),
                                                isPlayback = false
                                            )
                                        )
                                    },
                                    modifier = Modifier
                                        .align(Alignment.BottomEnd)
                                        .padding(4.dp)
                                        .size(28.dp)
                                        .background(Color.Black.copy(alpha = 0.65f), CircleShape)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Fullscreen,
                                        contentDescription = "Fullscreen",
                                        tint = Color.White,
                                        modifier = Modifier.size(16.dp)
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }

        if (totalPages > 1) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 6.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Button(
                    onClick = { if (safePage > 0) currentPage-- },
                    enabled = safePage > 0,
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1E293B)),
                    modifier = Modifier.height(30.dp)
                ) {
                    Icon(Icons.Default.ChevronLeft, contentDescription = "Prev", modifier = Modifier.size(16.dp))
                    Text("Prev", fontSize = 10.sp)
                }

                Text("Page ${safePage + 1} of $totalPages", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold)

                Button(
                    onClick = { if (safePage < totalPages - 1) currentPage++ },
                    enabled = safePage < totalPages - 1,
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1E293B)),
                    modifier = Modifier.height(30.dp)
                ) {
                    Text("Next", fontSize = 10.sp)
                    Icon(Icons.Default.ChevronRight, contentDescription = "Next", modifier = Modifier.size(16.dp))
                }
            }
        }
    }
}

// SCREEN C: Live Stream Single View Screen with Overlay Fullscreen Button directly on Video Feed
@Composable
fun ScreenC_SingleView(
    camera: CameraEntity?,
    isRemoteMode: Boolean,
    onBackToGrid: () -> Unit = {},
    onOpenPlayback: (CameraEntity) -> Unit,
    onRequestFullscreen: (FullscreenData) -> Unit,
    onOpenBookmark: (CameraEntity, String) -> Unit = { _, _ -> }
) {
    val context = LocalContext.current
    var qualityMode by remember { mutableStateOf("MAIN") }
    var isMuted by remember { mutableStateOf(false) }
    var playerInstance by remember { mutableStateOf<MediaPlayer?>(null) }
    var vlcLayoutInstance by remember { mutableStateOf<VLCVideoLayout?>(null) }

    // Intercept System Back Button & Edge-Swipe Gestures to pop back to Grid View cleanly
    BackHandler {
        onBackToGrid()
    }

    if (camera == null) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("Select a camera to view Single HD Stream", color = Color.White)
        }
        return
    }

    val liveUrl = remember(camera, isRemoteMode, qualityMode) {
        RtspUrlBuilder.buildLiveRtspUrl(camera, isRemoteMode, overrideQuality = qualityMode)
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 4.dp) // Edge margin dead-zone for system back gestures
    ) {
        // Main Video Card with ALL controls as overlays
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .height(280.dp),
            colors = CardDefaults.cardColors(containerColor = Color(0xFF0F172A)),
            shape = RoundedCornerShape(16.dp)
        ) {
            Box(modifier = Modifier.fillMaxSize()) {
                RtspVideoPlayer(
                    rtspUrl = liveUrl,
                    modifier = Modifier.fillMaxSize(),
                    onMediaPlayerReady = { player ->
                        playerInstance = player
                        player.volume = if (isMuted) 0 else 100
                    },
                    onLayoutCreated = { layout ->
                        vlcLayoutInstance = layout
                    }
                )

                // Top info bar overlay with Back (←) button
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .align(Alignment.TopCenter)
                        .background(Color.Black.copy(alpha = 0.65f))
                        .padding(horizontal = 8.dp, vertical = 6.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IconButton(
                            onClick = onBackToGrid,
                            modifier = Modifier
                                .size(30.dp)
                                .background(Color.White.copy(alpha = 0.18f), CircleShape)
                        ) {
                            Icon(
                                imageVector = Icons.Default.ArrowBack,
                                contentDescription = "Back to Grid",
                                tint = Color.White,
                                modifier = Modifier.size(16.dp)
                            )
                        }

                        Spacer(modifier = Modifier.width(8.dp))

                        Text(
                            text = "${camera.name} (Ch ${camera.channel})",
                            color = Color.White,
                            fontWeight = FontWeight.Bold,
                            fontSize = 12.sp
                        )
                    }

                    Text(
                        text = if (qualityMode == "MAIN") "HD MAIN" else "SUB",
                        color = if (qualityMode == "MAIN") Color(0xFF10B981) else Color(0xFFF59E0B),
                        fontWeight = FontWeight.Bold,
                        fontSize = 10.sp
                    )
                }

                // Bottom controls overlay bar
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .align(Alignment.BottomCenter)
                        .background(Color.Black.copy(alpha = 0.7f))
                        .padding(horizontal = 6.dp, vertical = 4.dp),
                    horizontalArrangement = Arrangement.SpaceEvenly,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // Mute/Unmute
                    IconButton(
                        onClick = {
                            isMuted = !isMuted
                            playerInstance?.volume = if (isMuted) 0 else 100
                        },
                        modifier = Modifier
                            .size(34.dp)
                            .background(
                                if (isMuted) Color(0xFFEF4444).copy(alpha = 0.8f) else Color.White.copy(alpha = 0.15f),
                                CircleShape
                            )
                    ) {
                        Icon(
                            if (isMuted) Icons.Default.VolumeOff else Icons.Default.VolumeUp,
                            contentDescription = "Audio",
                            tint = Color.White,
                            modifier = Modifier.size(18.dp)
                        )
                    }

                    // Switch Stream Quality
                    IconButton(
                        onClick = {
                            qualityMode = if (qualityMode == "MAIN") "SUB" else "MAIN"
                        },
                        modifier = Modifier
                            .size(34.dp)
                            .background(Color.White.copy(alpha = 0.15f), CircleShape)
                    ) {
                        Icon(
                            Icons.Default.Refresh,
                            contentDescription = "Switch Stream",
                            tint = Color.White,
                            modifier = Modifier.size(18.dp)
                        )
                    }

                    // Snapshot
                    IconButton(
                        onClick = { takeCameraSnapshot(context, playerInstance, camera.name, vlcLayoutInstance) },
                        modifier = Modifier
                            .size(34.dp)
                            .background(Color(0xFF3B82F6).copy(alpha = 0.8f), CircleShape)
                    ) {
                        Icon(
                            Icons.Default.CameraAlt,
                            contentDescription = "Snapshot",
                            tint = Color.White,
                            modifier = Modifier.size(18.dp)
                        )
                    }

                    // Bookmark Incident
                    IconButton(
                        onClick = { onOpenBookmark(camera, "") },
                        modifier = Modifier
                            .size(34.dp)
                            .background(Color(0xFFF59E0B).copy(alpha = 0.85f), CircleShape)
                    ) {
                        Icon(
                            Icons.Default.BookmarkAdd,
                            contentDescription = "Bookmark Incident",
                            tint = Color.White,
                            modifier = Modifier.size(18.dp)
                        )
                    }

                    // Fullscreen
                    IconButton(
                        onClick = {
                            onRequestFullscreen(
                                FullscreenData(
                                    titleText = "LIVE FULLSCREEN \u2022 ${camera.name} (Ch ${camera.channel})",
                                    cameraName = camera.name,
                                    rtspUrl = liveUrl,
                                    isPlayback = false
                                )
                            )
                        },
                        modifier = Modifier
                            .size(34.dp)
                            .background(Color(0xFF10B981).copy(alpha = 0.8f), CircleShape)
                    ) {
                        Icon(
                            Icons.Default.Fullscreen,
                            contentDescription = "Fullscreen",
                            tint = Color.White,
                            modifier = Modifier.size(18.dp)
                        )
                    }
                }
            }
        }
    }
}

// Hourly Scrubber with 60FPS UI Responsiveness
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HourlyTimelineScrubber(
    startHourStr: String,
    currentPositionSec: Long,
    clipStartSec: Long,
    clipEndSec: Long,
    playbackSpeed: Float,
    isPlaybackActive: Boolean = false,
    isDownloadMode: Boolean,
    onPlayPauseToggle: () -> Unit = {},
    onSeekPositionChanged: (Long) -> Unit,
    onClipRangeChanged: (Long, Long) -> Unit,
    onSpeedChanged: (Float) -> Unit,
    onToggleDownloadMode: () -> Unit,
    onOpenBookmark: () -> Unit = {}
) {
    val baseHour = remember(startHourStr) {
        if (startHourStr.contains(":")) startHourStr.split(":")[0].toIntOrNull() ?: 12 else 12
    }

    var sliderValue by remember(currentPositionSec) { mutableFloatStateOf(currentPositionSec.coerceIn(0L, 3599L).toFloat()) }
    var showSpeedDropdown by remember { mutableStateOf(false) }

    // Dynamic Tooltip String e.g. "10:30:21 AM"
    val tooltipTimeStr by remember {
        derivedStateOf {
            val totalSec = sliderValue.toInt()
            val mm = totalSec / 60
            val ss = totalSec % 60
            val amPm = if (baseHour < 12) "AM" else "PM"
            val displayHour = when {
                baseHour == 0 -> 12
                baseHour > 12 -> baseHour - 12
                else -> baseHour
            }
            String.format(Locale.getDefault(), "%02d:%02d:%02d %s", displayHour, mm, ss, amPm)
        }
    }

    // 15-Minute Interval Time Ticks Labels
    val tickLabels = remember(baseHour) {
        val nextHour = (baseHour + 1) % 24
        val formatAmPm = { h: Int, m: Int ->
            val amPm = if (h < 12) "AM" else "PM"
            val displayH = when {
                h == 0 -> 12
                h > 12 -> h - 12
                else -> h
            }
            String.format(Locale.getDefault(), "%02d:%02d %s", displayH, m, amPm)
        }
        listOf(
            formatAmPm(baseHour, 0),
            formatAmPm(baseHour, 15),
            formatAmPm(baseHour, 30),
            formatAmPm(baseHour, 45),
            formatAmPm(nextHour, 0)
        )
    }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(Color(0xFF1E293B), RoundedCornerShape(14.dp))
            .border(BorderStroke(1.dp, Color(0xFF334155)), RoundedCornerShape(14.dp))
            .padding(horizontal = 10.dp, vertical = 8.dp)
    ) {
        // Main Single Control Bar
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Play / Pause Button Group (Left side)
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(
                    onClick = onPlayPauseToggle,
                    modifier = Modifier
                        .size(34.dp)
                        .background(
                            if (isPlaybackActive) Color(0xFF0284C7) else Color(0xFF38BDF8),
                            CircleShape
                        )
                ) {
                    Icon(
                        imageVector = if (isPlaybackActive) Icons.Default.Pause else Icons.Default.PlayArrow,
                        contentDescription = "Play/Pause",
                        tint = Color.White,
                        modifier = Modifier.size(18.dp)
                    )
                }
            }

            // Timeline Slider Box with Floating Time Pin & Ticks (Center)
            Column(
                modifier = Modifier.weight(1f)
            ) {
                // Tooltip Pin aligned over thumb position
                BoxWithConstraints(modifier = Modifier.fillMaxWidth()) {
                    val progressFraction = (sliderValue / 3599f).coerceIn(0f, 1f)
                    val boxWidth = maxWidth

                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(20.dp)
                    ) {
                        Surface(
                            color = Color(0xFF38BDF8),
                            shape = RoundedCornerShape(4.dp),
                            modifier = Modifier
                                .align(Alignment.CenterStart)
                                .offset(x = (boxWidth * progressFraction) - 36.dp)
                        ) {
                            Text(
                                text = tooltipTimeStr,
                                color = Color(0xFF0F172A),
                                fontSize = 9.sp,
                                fontWeight = FontWeight.Bold,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }
                    }
                }

                // Slider Track
                Slider(
                    value = sliderValue,
                    onValueChange = { pos -> sliderValue = pos },
                    onValueChangeFinished = { onSeekPositionChanged(sliderValue.toLong()) },
                    valueRange = 0f..3599f,
                    colors = SliderDefaults.colors(
                        thumbColor = Color(0xFF38BDF8),
                        activeTrackColor = Color(0xFF38BDF8),
                        inactiveTrackColor = Color(0xFF334155)
                    ),
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(24.dp)
                )

                // 15-Minute Interval Time Ticks Below Track
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    tickLabels.forEach { label ->
                        Text(
                            text = label,
                            color = Color(0xFF94A3B8),
                            fontSize = 8.5.sp,
                            fontWeight = FontWeight.Medium
                        )
                    }
                }
            }

            // Bookmark Incident Button
            Surface(
                color = Color(0xFFF59E0B).copy(alpha = 0.2f),
                shape = RoundedCornerShape(8.dp),
                border = BorderStroke(1.dp, Color(0xFFF59E0B).copy(alpha = 0.5f)),
                modifier = Modifier.clickable { onOpenBookmark() }
            ) {
                Box(
                    modifier = Modifier.size(34.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = Icons.Default.BookmarkAdd,
                        contentDescription = "Bookmark Incident",
                        tint = Color(0xFFF59E0B),
                        modifier = Modifier.size(16.dp)
                    )
                }
            }

            // Download Icon Button (Right side)
            Surface(
                color = if (isDownloadMode) Color(0xFF8B5CF6) else Color(0xFF0F172A),
                shape = RoundedCornerShape(8.dp),
                border = BorderStroke(1.dp, if (isDownloadMode) Color(0xFF8B5CF6) else Color(0xFF334155)),
                modifier = Modifier.clickable { onToggleDownloadMode() }
            ) {
                Box(
                    modifier = Modifier.size(34.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = Icons.Default.Download,
                        contentDescription = "Download Clip",
                        tint = Color.White,
                        modifier = Modifier.size(16.dp)
                    )
                }
            }

            // Speed Selector Dropdown Pill (Far Right: e.g. 1.0x ▾)
            Box {
                Surface(
                    color = Color(0xFF0F172A),
                    shape = RoundedCornerShape(8.dp),
                    border = BorderStroke(1.dp, Color(0xFF334155)),
                    modifier = Modifier.clickable { showSpeedDropdown = true }
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 7.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "${playbackSpeed}x",
                            color = Color.White,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(modifier = Modifier.width(3.dp))
                        Icon(
                            imageVector = Icons.Default.ArrowDropDown,
                            contentDescription = "Speed",
                            tint = Color.White,
                            modifier = Modifier.size(14.dp)
                        )
                    }
                }

                DropdownMenu(
                    expanded = showSpeedDropdown,
                    onDismissRequest = { showSpeedDropdown = false },
                    modifier = Modifier
                        .background(Color(0xFF1E293B))
                        .width(90.dp)
                ) {
                    listOf(0.5f, 1.0f, 2.0f, 4.0f).forEach { speed ->
                        val isSelected = speed == playbackSpeed
                        DropdownMenuItem(
                            text = {
                                Text(
                                    text = "${speed}x",
                                    fontSize = 12.sp,
                                    fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
                                    color = if (isSelected) Color(0xFF38BDF8) else Color.White
                                )
                            },
                            onClick = {
                                onSpeedChanged(speed)
                                showSpeedDropdown = false
                            }
                        )
                    }
                }
            }
        }

        // Clip Range Selector (Shown when Download Clip is activated)
        if (isDownloadMode) {
            Spacer(modifier = Modifier.height(8.dp))
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Color(0xFF0F172A), RoundedCornerShape(8.dp))
                    .padding(8.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("CLIP RANGE EXPORT", color = Color(0xFFC084FC), fontWeight = FontWeight.Bold, fontSize = 10.sp)
                    val clipDurationSec = (clipEndSec - clipStartSec)
                    Text("Duration: ${clipDurationSec}s", color = Color.White, fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
                }

                RangeSlider(
                    value = clipStartSec.toFloat()..clipEndSec.toFloat(),
                    onValueChange = { range ->
                        onClipRangeChanged(range.start.toLong(), range.endInclusive.toLong())
                    },
                    valueRange = 0f..3599f,
                    colors = SliderDefaults.colors(
                        thumbColor = Color(0xFF8B5CF6),
                        activeTrackColor = Color(0xFF8B5CF6),
                        inactiveTrackColor = Color(0xFF334155)
                    ),
                    modifier = Modifier.fillMaxWidth()
                )
            }
        }
    }
}

// Interactive Analog & Digital Clock Time Picker Dialog
@Composable
fun ClockTimePickerDialog(
    initialStartTimeStr: String,
    initialEndTimeStr: String,
    onTimeRangeSelected: (String, String, String) -> Unit,
    onDismiss: () -> Unit
) {
    var selectedHour by remember { mutableIntStateOf(12) }
    var selectedMinute by remember { mutableIntStateOf(0) }
    var isPm by remember { mutableStateOf(true) }
    var isSelectingStart by remember { mutableStateOf(true) }

    var startHourState by remember { mutableIntStateOf(12) }
    var startMinuteState by remember { mutableIntStateOf(0) }
    var startIsPmState by remember { mutableStateOf(true) }

    var endHourState by remember { mutableIntStateOf(12) }
    var endMinuteState by remember { mutableIntStateOf(59) }
    var endIsPmState by remember { mutableStateOf(true) }

    var pickMode by remember { mutableStateOf("HOURS") }

    Dialog(onDismissRequest = onDismiss) {
        Card(
            modifier = Modifier
                .fillMaxWidth(0.95f)
                .wrapContentHeight(),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            shape = RoundedCornerShape(20.dp),
            elevation = CardDefaults.cardElevation(defaultElevation = 8.dp)
        ) {
            Column(
                modifier = Modifier.padding(18.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Select Playback Time", color = Color(0xFF0F172A), fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    IconButton(onClick = onDismiss, modifier = Modifier.size(24.dp)) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = Color(0xFF64748B))
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                // Top Header Switcher: Start Time vs End Time
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(Color(0xFFF1F5F9), RoundedCornerShape(10.dp))
                        .padding(4.dp),
                    horizontalArrangement = Arrangement.SpaceEvenly
                ) {
                    Surface(
                        color = if (isSelectingStart) Color(0xFF0F172A) else Color.Transparent,
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier
                            .weight(1f)
                            .clickable {
                                isSelectingStart = true
                                selectedHour = startHourState
                                selectedMinute = startMinuteState
                                isPm = startIsPmState
                            }
                    ) {
                        Text(
                            text = "Start: ${String.format(Locale.getDefault(), "%02d:%02d %s", if (startHourState == 0) 12 else startHourState, startMinuteState, if (startIsPmState) "PM" else "AM")}",
                            color = if (isSelectingStart) Color.White else Color(0xFF64748B),
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            textAlign = TextAlign.Center,
                            modifier = Modifier.padding(vertical = 8.dp)
                        )
                    }

                    Spacer(modifier = Modifier.width(4.dp))

                    Surface(
                        color = if (!isSelectingStart) Color(0xFF0F172A) else Color.Transparent,
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier
                            .weight(1f)
                            .clickable {
                                isSelectingStart = false
                                selectedHour = endHourState
                                selectedMinute = endMinuteState
                                isPm = endIsPmState
                            }
                    ) {
                        Text(
                            text = "End: ${String.format(Locale.getDefault(), "%02d:%02d %s", if (endHourState == 0) 12 else endHourState, endMinuteState, if (endIsPmState) "PM" else "AM")}",
                            color = if (!isSelectingStart) Color.White else Color(0xFF64748B),
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            textAlign = TextAlign.Center,
                            modifier = Modifier.padding(vertical = 8.dp)
                        )
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))

                // Clock Digital Display & AM/PM Toggle
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        // Hour Box
                        Surface(
                            color = if (pickMode == "HOURS") Color(0xFFE0F2FE) else Color(0xFFF1F5F9),
                            shape = RoundedCornerShape(10.dp),
                            border = BorderStroke(1.dp, if (pickMode == "HOURS") Color(0xFF0284C7) else Color(0xFFCBD5E1)),
                            modifier = Modifier.clickable { pickMode = "HOURS" }
                        ) {
                            Text(
                                text = String.format(Locale.getDefault(), "%02d", if (selectedHour == 0) 12 else selectedHour),
                                fontSize = 28.sp,
                                fontWeight = FontWeight.Bold,
                                color = if (pickMode == "HOURS") Color(0xFF0284C7) else Color(0xFF0F172A),
                                modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp)
                            )
                        }

                        Text(" : ", fontSize = 24.sp, fontWeight = FontWeight.Bold, color = Color(0xFF0F172A))

                        // Minute Box
                        Surface(
                            color = if (pickMode == "MINUTES") Color(0xFFE0F2FE) else Color(0xFFF1F5F9),
                            shape = RoundedCornerShape(10.dp),
                            border = BorderStroke(1.dp, if (pickMode == "MINUTES") Color(0xFF0284C7) else Color(0xFFCBD5E1)),
                            modifier = Modifier.clickable { pickMode = "MINUTES" }
                        ) {
                            Text(
                                text = String.format(Locale.getDefault(), "%02d", selectedMinute),
                                fontSize = 28.sp,
                                fontWeight = FontWeight.Bold,
                                color = if (pickMode == "MINUTES") Color(0xFF0284C7) else Color(0xFF0F172A),
                                modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp)
                            )
                        }
                    }

                    // AM / PM Selector
                    Column(
                        modifier = Modifier
                            .background(Color(0xFFF1F5F9), RoundedCornerShape(10.dp))
                            .padding(2.dp)
                    ) {
                        Surface(
                            color = if (!isPm) Color(0xFF0F172A) else Color.Transparent,
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier.clickable {
                                isPm = false
                                if (isSelectingStart) startIsPmState = false else endIsPmState = false
                            }
                        ) {
                            Text(
                                "AM",
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                color = if (!isPm) Color.White else Color(0xFF64748B),
                                modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp)
                            )
                        }
                        Surface(
                            color = if (isPm) Color(0xFF0F172A) else Color.Transparent,
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier.clickable {
                                isPm = true
                                if (isSelectingStart) startIsPmState = true else endIsPmState = true
                            }
                        ) {
                            Text(
                                "PM",
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                color = if (isPm) Color.White else Color(0xFF64748B),
                                modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp)
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))

                // Clock Circular Dial Matrix (1 to 12 Hours or 0 to 55 Minutes)
                Box(
                    modifier = Modifier
                        .size(200.dp)
                        .background(Color(0xFFF8FAFC), CircleShape),
                    contentAlignment = Alignment.Center
                ) {
                    if (pickMode == "HOURS") {
                        val hours = listOf(12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
                        LazyVerticalGrid(
                            columns = GridCells.Fixed(4),
                            modifier = Modifier
                                .fillMaxSize()
                                .padding(12.dp),
                            verticalArrangement = Arrangement.Center,
                            horizontalArrangement = Arrangement.Center
                        ) {
                            items(hours.size) { idx ->
                                val h = hours[idx]
                                val isHSelected = (selectedHour % 12) == (h % 12)
                                Box(
                                    modifier = Modifier
                                        .size(40.dp)
                                        .padding(2.dp)
                                        .background(if (isHSelected) Color(0xFF0284C7) else Color.Transparent, CircleShape)
                                        .clickable {
                                            selectedHour = if (h == 12) 0 else h
                                            if (isSelectingStart) startHourState = selectedHour else endHourState = selectedHour
                                            pickMode = "MINUTES"
                                        },
                                    contentAlignment = Alignment.Center
                                ) {
                                    Text(
                                        text = h.toString(),
                                        fontSize = 13.sp,
                                        fontWeight = if (isHSelected) FontWeight.Bold else FontWeight.Normal,
                                        color = if (isHSelected) Color.White else Color(0xFF0F172A)
                                    )
                                }
                            }
                        }
                    } else {
                        val minutes = listOf(0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55)
                        LazyVerticalGrid(
                            columns = GridCells.Fixed(4),
                            modifier = Modifier
                                .fillMaxSize()
                                .padding(12.dp),
                            verticalArrangement = Arrangement.Center,
                            horizontalArrangement = Arrangement.Center
                        ) {
                            items(minutes.size) { idx ->
                                val m = minutes[idx]
                                val isMSelected = selectedMinute == m
                                Box(
                                    modifier = Modifier
                                        .size(40.dp)
                                        .padding(2.dp)
                                        .background(if (isMSelected) Color(0xFF0284C7) else Color.Transparent, CircleShape)
                                        .clickable {
                                            selectedMinute = m
                                            if (isSelectingStart) startMinuteState = selectedMinute else endMinuteState = selectedMinute
                                        },
                                    contentAlignment = Alignment.Center
                                ) {
                                    Text(
                                        text = String.format(Locale.getDefault(), "%02d", m),
                                        fontSize = 12.sp,
                                        fontWeight = if (isMSelected) FontWeight.Bold else FontWeight.Normal,
                                        color = if (isMSelected) Color.White else Color(0xFF0F172A)
                                    )
                                }
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))

                // Quick Preset Time Interval Chips
                Text("Quick Presets:", color = Color(0xFF64748B), fontSize = 10.sp, fontWeight = FontWeight.Bold)
                Spacer(modifier = Modifier.height(4.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    listOf("09:00 AM" to (9 to false), "12:00 PM" to (12 to true), "03:00 PM" to (3 to true), "06:00 PM" to (6 to true)).forEach { (label, data) ->
                        Surface(
                            color = Color(0xFFF1F5F9),
                            shape = RoundedCornerShape(6.dp),
                            modifier = Modifier
                                .weight(1f)
                                .clickable {
                                    val (h, pm) = data
                                    if (isSelectingStart) {
                                        startHourState = if (h == 12) 0 else h
                                        startMinuteState = 0
                                        startIsPmState = pm
                                    } else {
                                        endHourState = if (h == 12) 0 else h
                                        endMinuteState = 59
                                        endIsPmState = pm
                                    }
                                    selectedHour = if (h == 12) 0 else h
                                    selectedMinute = if (isSelectingStart) 0 else 59
                                    isPm = pm
                                }
                        ) {
                            Text(
                                text = label,
                                fontSize = 9.sp,
                                fontWeight = FontWeight.Bold,
                                color = Color(0xFF0F172A),
                                textAlign = TextAlign.Center,
                                modifier = Modifier.padding(vertical = 4.dp)
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                // Action Footer Buttons
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    OutlinedButton(
                        onClick = onDismiss,
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier
                            .weight(1f)
                            .height(40.dp)
                    ) {
                        Text("Cancel", color = Color(0xFF0F172A), fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    }

                    Button(
                        onClick = {
                            val start24Hour = (if (startHourState == 0) 12 else startHourState) + (if (startIsPmState && startHourState != 12) 12 else if (!startIsPmState && startHourState == 12) -12 else 0)
                            val end24Hour = (if (endHourState == 0) 12 else endHourState) + (if (endIsPmState && endHourState != 12) 12 else if (!endIsPmState && endHourState == 12) -12 else 0)

                            val sTime = String.format(Locale.getDefault(), "%02d:%02d:00", start24Hour % 24, startMinuteState)
                            val eTime = String.format(Locale.getDefault(), "%02d:%02d:59", end24Hour % 24, endMinuteState)
                            val displayStr = String.format(
                                Locale.getDefault(),
                                "%02d:%02d %s - %02d:%02d %s",
                                if (startHourState == 0) 12 else startHourState, startMinuteState, if (startIsPmState) "PM" else "AM",
                                if (endHourState == 0) 12 else endHourState, endMinuteState, if (endIsPmState) "PM" else "AM"
                            )

                            onTimeRangeSelected(sTime, eTime, displayStr)
                            onDismiss()
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF0F172A)),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier
                            .weight(1f)
                            .height(40.dp)
                    ) {
                        Text("Set Time", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    }
                }
            }
        }
    }
}

// SCREEN D: Fast & Smooth NVR Playback with Overlay Fullscreen Button directly on Video Feed
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScreenD_Playback(
    activeCam: CameraEntity?,
    cameraList: List<CameraEntity>,
    isRemoteMode: Boolean,
    userFeatures: UserFeatures? = null,
    onSelectCam: (CameraEntity) -> Unit,
    onRequestFullscreen: (FullscreenData) -> Unit,
    onOpenBookmark: (CameraEntity, String) -> Unit = { _, _ -> }
) {
    val context = LocalContext.current
    var currentCam by remember { mutableStateOf(activeCam ?: cameraList.firstOrNull()) }

    var showSetupBottomSheet by remember { mutableStateOf(true) }
    var isListView by remember { mutableStateOf(true) }

    val canMultiSync = userFeatures?.multiSyncPlayback != false
    var isMultiSyncMode by remember { mutableStateOf(canMultiSync) }
    var selectedSyncCamIds by remember { mutableStateOf(cameraList.take(4).map { it.id }.toSet()) }

    val syncedPlayersMap = remember { mutableStateMapOf<Long, MediaPlayer>() }
    val syncedLayoutsMap = remember { mutableStateMapOf<Long, VLCVideoLayout>() }

    var activeRtspUrl by remember { mutableStateOf("") }
    var isPlaybackActive by remember { mutableStateOf(false) }
    var playbackSpeed by remember { mutableFloatStateOf(1.0f) }
    var isDownloadMode by remember { mutableStateOf(false) }

    val todayDateStr = remember { SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date()) }
    var selectedDate by remember { mutableStateOf(todayDateStr) }
    var selectedTimeSlot by remember { mutableStateOf("12:00 PM - 12:59 PM (12:00 - 12:59)") }
    var startTime by remember { mutableStateOf("12:00:00") }
    var endTime by remember { mutableStateOf("12:59:59") }

    var currentSeekSec by remember { mutableLongStateOf(0L) }
    var clipStartSec by remember { mutableLongStateOf(60L) }
    var clipEndSec by remember { mutableLongStateOf(330L) }

    var showCameraDropdown by remember { mutableStateOf(false) }
    var showCalendarPicker by remember { mutableStateOf(false) }
    var showTimePickerModal by remember { mutableStateOf(false) }
    var showTimeSlotDropdown by remember { mutableStateOf(false) }

    var playerInstance by remember { mutableStateOf<MediaPlayer?>(null) }
    var vlcLayoutInstance by remember { mutableStateOf<VLCVideoLayout?>(null) }

    var showMaxLimitAlert by remember { mutableStateOf(false) }
    var activeExportSeconds by remember { mutableLongStateOf(0L) }
    var showExportProgressDialog by remember { mutableStateOf(false) }

    val cleanStartDate = remember(selectedDate) { selectedDate.replace("-", "").trim() }
    val cleanStartTime = remember(startTime) { startTime.replace(":", "").trim() }
    val cleanEndDate = remember(selectedDate) { selectedDate.replace("-", "").trim() }
    val cleanEndTime = remember(endTime) { endTime.replace(":", "").trim() }

    val timeSlots = remember {
        listOf(
            "12:00 AM - 12:59 AM (00:00 - 00:59)" to ("00:00:00" to "00:59:59"),
            "01:00 AM - 01:59 AM (01:00 - 01:59)" to ("01:00:00" to "01:59:59"),
            "02:00 AM - 02:59 AM (02:00 - 02:59)" to ("02:00:00" to "02:59:59"),
            "03:00 AM - 03:59 AM (03:00 - 03:59)" to ("03:00:00" to "03:59:59"),
            "04:00 AM - 04:59 AM (04:00 - 04:59)" to ("04:00:00" to "04:59:59"),
            "05:00 AM - 05:59 AM (05:00 - 05:59)" to ("05:00:00" to "05:59:59"),
            "06:00 AM - 06:59 AM (06:00 - 06:59)" to ("06:00:00" to "06:59:59"),
            "07:00 AM - 07:59 AM (07:00 - 07:59)" to ("07:00:00" to "07:59:59"),
            "08:00 AM - 08:59 AM (08:00 - 08:59)" to ("08:00:00" to "08:59:59"),
            "09:00 AM - 09:59 AM (09:00 - 09:59)" to ("09:00:00" to "09:59:59"),
            "10:00 AM - 10:59 AM (10:00 - 10:59)" to ("10:00:00" to "10:59:59"),
            "11:00 AM - 11:59 AM (11:00 - 11:59)" to ("11:00:00" to "11:59:59"),
            "12:00 PM - 12:59 PM (12:00 - 12:59)" to ("12:00:00" to "12:59:59"),
            "01:00 PM - 01:59 PM (13:00 - 13:59)" to ("13:00:00" to "13:59:59"),
            "02:00 PM - 02:59 PM (14:00 - 14:59)" to ("14:00:00" to "14:59:59"),
            "03:00 PM - 03:59 PM (15:00 - 15:59)" to ("15:00:00" to "15:59:59"),
            "04:00 PM - 04:59 PM (16:00 - 16:59)" to ("16:00:00" to "16:59:59"),
            "05:00 PM - 05:59 PM (17:00 - 17:59)" to ("17:00:00" to "17:59:59"),
            "06:00 PM - 06:59 PM (18:00 - 18:59)" to ("18:00:00" to "18:59:59"),
            "07:00 PM - 07:59 PM (19:00 - 19:59)" to ("19:00:00" to "19:59:59"),
            "08:00 PM - 08:59 PM (20:00 - 20:59)" to ("20:00:00" to "20:59:59"),
            "09:00 PM - 09:59 PM (21:00 - 21:59)" to ("21:00:00" to "21:59:59"),
            "10:00 PM - 10:59 PM (22:00 - 22:59)" to ("22:00:00" to "22:59:59"),
            "11:00 PM - 11:59 PM (23:00 - 23:59)" to ("23:00:00" to "23:59:59")
        )
    }

    fun handleDownloadClipTrigger() {
        val durationSec = (clipEndSec - clipStartSec)
        if (durationSec <= 0) {
            Toast.makeText(context, "End time must be after Start time.", Toast.LENGTH_LONG).show()
        } else if (durationSec > 300) {
            showMaxLimitAlert = true
        } else {
            activeExportSeconds = durationSec
            showExportProgressDialog = true
        }
    }

    if (currentCam == null) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("Add a camera to play recorded NVR footage.", color = Color.White)
        }
        return
    }

    Column(modifier = Modifier.fillMaxSize()) {
        // Top Action Bar: Edit Setup Button + View Mode Switcher (Grid vs List)
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Surface(
                color = Color(0xFF1E293B),
                shape = RoundedCornerShape(8.dp),
                border = BorderStroke(1.dp, Color(0xFF334155)),
                modifier = Modifier.clickable { showSetupBottomSheet = true }
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = Icons.Default.Tune,
                        contentDescription = "Edit Setup",
                        tint = Color(0xFF38BDF8),
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        text = "Edit Setup",
                        color = Color.White,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                if (!canMultiSync) {
                    Surface(
                        color = Color(0xFFEF4444).copy(alpha = 0.15f),
                        shape = RoundedCornerShape(6.dp)
                    ) {
                        Text(
                            text = "Single Mode Only",
                            color = Color(0xFFF87171),
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 3.dp)
                        )
                    }
                    Spacer(modifier = Modifier.width(6.dp))
                }

                Surface(
                    color = Color(0xFF1E293B),
                    shape = RoundedCornerShape(8.dp),
                    border = BorderStroke(1.dp, Color(0xFF334155)),
                    modifier = Modifier.clickable { isListView = !isListView }
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = if (isListView) Icons.Default.GridView else Icons.Default.ViewList,
                            contentDescription = "Toggle View Mode",
                            tint = Color.White,
                            modifier = Modifier.size(15.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(
                            text = if (isListView) "GRID" else "LIST",
                            color = Color.White,
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
        }

        // Maximized Video Viewport Layout
        Box(modifier = Modifier.weight(1f)) {
            if (isPlaybackActive) {
                if (isMultiSyncMode) {
                    val activeSyncCams = cameraList.filter { selectedSyncCamIds.contains(it.id) }.take(4)

                    val effectiveStartTimeStr = remember(startTime, currentSeekSec) {
                        if (currentSeekSec > 0) {
                            val baseHour = if (startTime.contains(":")) startTime.split(":")[0].toIntOrNull() ?: 12 else 12
                            val mm = ((currentSeekSec % 3600) / 60).toInt()
                            val ss = (currentSeekSec % 60).toInt()
                            String.format(Locale.getDefault(), "%02d%02d%02d", baseHour, mm, ss)
                        } else {
                            cleanStartTime
                        }
                    }

                    if (isListView) {
                        LazyColumn(
                            verticalArrangement = Arrangement.spacedBy(8.dp),
                            modifier = Modifier.fillMaxSize()
                        ) {
                            items(activeSyncCams) { cam ->
                                val streamUrl = RtspUrlBuilder.buildPlaybackRtspUrl(
                                    camera = cam,
                                    isRemoteMode = isRemoteMode,
                                    startDateStr = cleanStartDate,
                                    startTimeStr = effectiveStartTimeStr,
                                    endDateStr = cleanEndDate,
                                    endTimeStr = cleanEndTime
                                )
                                Card(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .height(200.dp),
                                    colors = CardDefaults.cardColors(containerColor = Color(0xFF0F172A)),
                                    shape = RoundedCornerShape(10.dp)
                                ) {
                                    Box(modifier = Modifier.fillMaxSize()) {
                                        RtspVideoPlayer(
                                            rtspUrl = streamUrl,
                                            playbackRate = playbackSpeed,
                                            modifier = Modifier.fillMaxSize(),
                                            onMediaPlayerReady = { player ->
                                                syncedPlayersMap[cam.id] = player
                                                setMediaPlayerRate(player, playbackSpeed)
                                                if (currentSeekSec > 0) {
                                                    try { player.time = currentSeekSec * 1000L } catch (e: Exception) {}
                                                }
                                            },
                                            onLayoutCreated = { layout ->
                                                syncedLayoutsMap[cam.id] = layout
                                            }
                                        )

                                        Row(
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .background(Color.Black.copy(alpha = 0.65f))
                                                .padding(horizontal = 8.dp, vertical = 4.dp)
                                                .align(Alignment.TopCenter),
                                            horizontalArrangement = Arrangement.SpaceBetween
                                        ) {
                                            Text("${cam.name} (Ch ${cam.channel})", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 11.sp)
                                            Text("SYNCED", color = Color(0xFFC084FC), fontWeight = FontWeight.Bold, fontSize = 9.sp)
                                        }

                                        IconButton(
                                            onClick = {
                                                onRequestFullscreen(
                                                    FullscreenData(
                                                        titleText = "SYNCED PLAYBACK • ${cam.name} (Ch ${cam.channel})",
                                                        cameraName = "${cam.name}_SyncedPlayback",
                                                        rtspUrl = streamUrl,
                                                        isPlayback = true,
                                                        onDownloadClipClick = { handleDownloadClipTrigger() }
                                                    )
                                                )
                                            },
                                            modifier = Modifier
                                                .align(Alignment.BottomEnd)
                                                .padding(6.dp)
                                                .size(28.dp)
                                                .background(Color.Black.copy(alpha = 0.65f), CircleShape)
                                        ) {
                                            Icon(Icons.Default.Fullscreen, contentDescription = "Fullscreen", tint = Color.White, modifier = Modifier.size(16.dp))
                                        }
                                    }
                                }
                            }
                        }
                    } else {
                        val gridCols = if (activeSyncCams.size <= 2) activeSyncCams.size else 2
                        LazyVerticalGrid(
                            columns = GridCells.Fixed(gridCols),
                            modifier = Modifier.fillMaxSize(),
                            verticalArrangement = Arrangement.spacedBy(4.dp),
                            horizontalArrangement = Arrangement.spacedBy(4.dp)
                        ) {
                            items(activeSyncCams) { cam ->
                                val streamUrl = RtspUrlBuilder.buildPlaybackRtspUrl(
                                    camera = cam,
                                    isRemoteMode = isRemoteMode,
                                    startDateStr = cleanStartDate,
                                    startTimeStr = effectiveStartTimeStr,
                                    endDateStr = cleanEndDate,
                                    endTimeStr = cleanEndTime
                                )
                                Card(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .height(if (activeSyncCams.size <= 2) 280.dp else 160.dp),
                                    colors = CardDefaults.cardColors(containerColor = Color(0xFF0F172A)),
                                    shape = RoundedCornerShape(8.dp)
                                ) {
                                    Box(modifier = Modifier.fillMaxSize()) {
                                        RtspVideoPlayer(
                                            rtspUrl = streamUrl,
                                            playbackRate = playbackSpeed,
                                            modifier = Modifier.fillMaxSize(),
                                            onMediaPlayerReady = { player ->
                                                syncedPlayersMap[cam.id] = player
                                                setMediaPlayerRate(player, playbackSpeed)
                                                if (currentSeekSec > 0) {
                                                    try { player.time = currentSeekSec * 1000L } catch (e: Exception) {}
                                                }
                                            },
                                            onLayoutCreated = { layout ->
                                                syncedLayoutsMap[cam.id] = layout
                                            }
                                        )

                                        Row(
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .background(Color.Black.copy(alpha = 0.65f))
                                                .padding(horizontal = 6.dp, vertical = 3.dp)
                                                .align(Alignment.TopCenter),
                                            horizontalArrangement = Arrangement.SpaceBetween
                                        ) {
                                            Text("${cam.name} (Ch ${cam.channel})", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 9.sp)
                                            Text("SYNCED", color = Color(0xFFC084FC), fontWeight = FontWeight.Bold, fontSize = 8.sp)
                                        }

                                        IconButton(
                                            onClick = {
                                                onRequestFullscreen(
                                                    FullscreenData(
                                                        titleText = "SYNCED PLAYBACK • ${cam.name} (Ch ${cam.channel})",
                                                        cameraName = "${cam.name}_SyncedPlayback",
                                                        rtspUrl = streamUrl,
                                                        isPlayback = true,
                                                        onDownloadClipClick = { handleDownloadClipTrigger() }
                                                    )
                                                )
                                            },
                                            modifier = Modifier
                                                .align(Alignment.BottomEnd)
                                                .padding(4.dp)
                                                .size(26.dp)
                                                .background(Color.Black.copy(alpha = 0.65f), CircleShape)
                                        ) {
                                            Icon(Icons.Default.Fullscreen, contentDescription = "Fullscreen", tint = Color.White, modifier = Modifier.size(15.dp))
                                        }
                                    }
                                }
                            }
                        }
                    }
                } else {
                    // Single Camera Viewport
                    Card(
                        modifier = Modifier.fillMaxSize(),
                        colors = CardDefaults.cardColors(containerColor = Color(0xFF0F172A)),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Box(modifier = Modifier.fillMaxSize()) {
                            RtspVideoPlayer(
                                rtspUrl = activeRtspUrl,
                                playbackRate = playbackSpeed,
                                modifier = Modifier.fillMaxSize(),
                                onMediaPlayerReady = { player ->
                                    playerInstance = player
                                    setMediaPlayerRate(player, playbackSpeed)
                                },
                                onLayoutCreated = { layout ->
                                    vlcLayoutInstance = layout
                                },
                                onPlayingStateChanged = { playing ->
                                    isPlaybackActive = playing
                                }
                            )

                            IconButton(
                                onClick = {
                                    onRequestFullscreen(
                                        FullscreenData(
                                            titleText = "NVR PLAYBACK • ${currentCam!!.name} (Ch ${currentCam!!.channel})",
                                            cameraName = "${currentCam!!.name}_Playback",
                                            rtspUrl = activeRtspUrl,
                                            isPlayback = true,
                                            onDownloadClipClick = { handleDownloadClipTrigger() }
                                        )
                                    )
                                },
                                modifier = Modifier
                                    .align(Alignment.BottomEnd)
                                    .padding(8.dp)
                                    .size(34.dp)
                                    .background(Color.Black.copy(alpha = 0.7f), CircleShape)
                            ) {
                                Icon(Icons.Default.Fullscreen, contentDescription = "Fullscreen", tint = Color.White, modifier = Modifier.size(18.dp))
                            }
                        }
                    }
                }
            } else {
                // Idle Placeholder View
                Card(
                    modifier = Modifier.fillMaxSize(),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF0F172A)),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center,
                        modifier = Modifier.fillMaxSize().padding(16.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Movie,
                            contentDescription = "Playback Idle",
                            tint = Color(0xFF64748B),
                            modifier = Modifier.size(48.dp)
                        )
                        Spacer(modifier = Modifier.height(10.dp))
                        Text(
                            text = "Configure parameters in setup sheet to start playback.",
                            color = Color(0xFF94A3B8),
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Medium,
                            textAlign = TextAlign.Center
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        Button(
                            onClick = { showSetupBottomSheet = true },
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF38BDF8)),
                            shape = RoundedCornerShape(10.dp)
                        ) {
                            Icon(Icons.Default.Tune, contentDescription = "Setup", modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(6.dp))
                            Text("Open Setup Sheet", color = Color(0xFF0F172A), fontWeight = FontWeight.Bold, fontSize = 12.sp)
                        }
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        // Floating Action Controls & Translucent Master Seek Bar
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = Color(0xFF1E293B)),
            shape = RoundedCornerShape(12.dp)
        ) {
            Column(modifier = Modifier.padding(8.dp)) {
                // Master Scrubber
                HourlyTimelineScrubber(
                    startHourStr = startTime,
                    currentPositionSec = currentSeekSec,
                    clipStartSec = clipStartSec,
                    clipEndSec = clipEndSec,
                    playbackSpeed = playbackSpeed,
                    isPlaybackActive = isPlaybackActive,
                    isDownloadMode = isDownloadMode,
                    onPlayPauseToggle = {
                        if (isMultiSyncMode) {
                            syncedPlayersMap.values.forEach { p ->
                                try {
                                    if (p.isPlaying) p.pause() else { p.play(); setMediaPlayerRate(p, playbackSpeed) }
                                } catch (e: Exception) {}
                            }
                            isPlaybackActive = syncedPlayersMap.values.any { it.isPlaying }
                        } else {
                            val player = playerInstance
                            if (player != null) {
                                if (player.isPlaying) player.pause() else { player.play(); setMediaPlayerRate(player, playbackSpeed) }
                                isPlaybackActive = player.isPlaying
                            }
                        }
                    },
                    onSeekPositionChanged = { sec ->
                        currentSeekSec = sec
                        val baseHour = if (startTime.contains(":")) startTime.split(":")[0].toIntOrNull() ?: 12 else 12
                        val mm = ((sec % 3600) / 60).toInt()
                        val ss = (sec % 60).toInt()

                        val formattedTime = String.format(Locale.getDefault(), "%02d:%02d:%02d", baseHour, mm, ss)
                        startTime = formattedTime
                        val seekMs = sec * 1000L

                        if (isMultiSyncMode) {
                            syncedPlayersMap.values.forEach { p ->
                                try { p.time = seekMs } catch (e: Exception) {}
                            }
                        } else {
                            playerInstance?.let { p ->
                                try { p.time = seekMs } catch (e: Exception) {}
                            }
                        }
                    },
                    onClipRangeChanged = { startSec, endSec ->
                        clipStartSec = startSec
                        clipEndSec = endSec
                    },
                    onSpeedChanged = { speed ->
                        playbackSpeed = speed
                        if (isMultiSyncMode) {
                            syncedPlayersMap.values.forEach { p -> setMediaPlayerRate(p, speed) }
                        } else {
                            setMediaPlayerRate(playerInstance, speed)
                        }
                    },
                    onToggleDownloadMode = { isDownloadMode = !isDownloadMode },
                    onOpenBookmark = {
                        if (currentCam != null) {
                            onOpenBookmark(currentCam!!, "$selectedDate $startTime")
                        }
                    }
                )
            }
        }
    }

    // Interactive Hover Bottom Sheet Drawer
    if (showSetupBottomSheet) {
        ModalBottomSheet(
            onDismissRequest = { showSetupBottomSheet = false },
            containerColor = Color(0xFF0F172A),
            shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 10.dp)
                    .verticalScroll(rememberScrollState())
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("NVR PLAYBACK SETUP", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                    IconButton(onClick = { showSetupBottomSheet = false }, modifier = Modifier.size(28.dp)) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = Color(0xFF94A3B8))
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                // Mode Toggle: Single vs Multi-Sync
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(Color(0xFF1E293B), RoundedCornerShape(10.dp))
                        .padding(4.dp),
                    horizontalArrangement = Arrangement.SpaceEvenly
                ) {
                    Surface(
                        color = if (!isMultiSyncMode) Color(0xFF3B82F6) else Color.Transparent,
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier
                            .weight(1f)
                            .clickable { isMultiSyncMode = false }
                    ) {
                        Text("SINGLE CAMERA", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center, modifier = Modifier.padding(vertical = 8.dp))
                    }

                    Surface(
                        color = if (isMultiSyncMode) Color(0xFF8B5CF6) else Color.Transparent,
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier
                            .weight(1f)
                            .clickable {
                                if (canMultiSync) {
                                    isMultiSyncMode = true
                                    if (selectedSyncCamIds.isEmpty()) {
                                        selectedSyncCamIds = cameraList.take(4).map { it.id }.toSet()
                                    }
                                } else {
                                    Toast.makeText(context, "Multi-Sync playback permission is disabled for your account.", Toast.LENGTH_LONG).show()
                                }
                            }
                    ) {
                        Text("MULTI-SYNC (2-4 FEEDS)", color = if (canMultiSync) Color.White else Color(0xFF64748B), fontSize = 11.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center, modifier = Modifier.padding(vertical = 8.dp))
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                // Camera Selector
                if (isMultiSyncMode) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(Color(0xFF1E293B), RoundedCornerShape(10.dp))
                            .padding(10.dp)
                    ) {
                        Text("SELECT SYNCED FEEDS (${selectedSyncCamIds.size}/4)", color = Color(0xFFC084FC), fontWeight = FontWeight.Bold, fontSize = 11.sp)
                        Spacer(modifier = Modifier.height(6.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            cameraList.forEach { cam ->
                                val isChecked = selectedSyncCamIds.contains(cam.id)
                                Surface(
                                    color = if (isChecked) Color(0xFF8B5CF6).copy(alpha = 0.25f) else Color(0xFF0F172A),
                                    shape = RoundedCornerShape(8.dp),
                                    border = BorderStroke(1.dp, if (isChecked) Color(0xFF8B5CF6) else Color(0xFF334155)),
                                    modifier = Modifier.clickable {
                                        val current = selectedSyncCamIds.toMutableSet()
                                        if (isChecked) {
                                            if (current.size > 1) current.remove(cam.id)
                                        } else {
                                            if (current.size < 4) current.add(cam.id)
                                        }
                                        selectedSyncCamIds = current
                                    }
                                ) {
                                    Text(
                                        text = if (isChecked) "✓ ${cam.name}" else cam.name,
                                        color = if (isChecked) Color.White else Color(0xFF94A3B8),
                                        fontSize = 11.sp,
                                        fontWeight = if (isChecked) FontWeight.Bold else FontWeight.Normal,
                                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp)
                                    )
                                }
                            }
                        }
                    }
                } else {
                    Box(modifier = Modifier.fillMaxWidth()) {
                        Card(
                            modifier = Modifier.fillMaxWidth().clickable { showCameraDropdown = true },
                            colors = CardDefaults.cardColors(containerColor = Color(0xFF1E293B)),
                            shape = RoundedCornerShape(10.dp)
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(Icons.Default.Videocam, contentDescription = "Camera", tint = Color(0xFF10B981), modifier = Modifier.size(18.dp))
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Text("Select Camera: ${currentCam!!.name} (Ch ${currentCam!!.channel})", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                                }
                                Icon(Icons.Default.ArrowDropDown, contentDescription = "Select", tint = Color.White)
                            }
                        }

                        DropdownMenu(
                            expanded = showCameraDropdown,
                            onDismissRequest = { showCameraDropdown = false },
                            modifier = Modifier.fillMaxWidth().heightIn(max = 240.dp).background(Color(0xFF1E293B))
                        ) {
                            cameraList.forEach { cam ->
                                val isSelected = cam.id == currentCam?.id
                                DropdownMenuItem(
                                    text = { Text("${cam.name} (Ch ${cam.channel})", fontSize = 13.sp, fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal, color = if (isSelected) Color(0xFF38BDF8) else Color.White) },
                                    onClick = {
                                        currentCam = cam
                                        onSelectCam(cam)
                                        showCameraDropdown = false
                                    }
                                )
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                // Date & Simplified Time Selection Card
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF1E293B)),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text("DATE & TIME PERIOD", color = Color(0xFF38BDF8), fontWeight = FontWeight.Bold, fontSize = 11.sp)
                        Spacer(modifier = Modifier.height(6.dp))

                        // Date Picker Button
                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(40.dp)
                                .clickable { showCalendarPicker = true },
                            colors = CardDefaults.cardColors(containerColor = Color(0xFF0F172A)),
                            shape = RoundedCornerShape(8.dp)
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxSize()
                                    .padding(horizontal = 12.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(Icons.Default.CalendarToday, contentDescription = "Calendar", tint = Color(0xFF38BDF8), modifier = Modifier.size(16.dp))
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Text("Date: $selectedDate", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                                }
                                Text("Change", color = Color(0xFF94A3B8), fontSize = 11.sp)
                            }
                        }

                        Spacer(modifier = Modifier.height(10.dp))

                        val nowHour = remember {
                            try { SimpleDateFormat("H", Locale.getDefault()).format(Date()).toInt() } catch (e: Exception) { 23 }
                        }
                        val isToday = selectedDate == todayDateStr

                        Text("SELECT HOUR SLOT (${startTime.take(2)}:00 - ${endTime.take(2)}:59)", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                        Spacer(modifier = Modifier.height(6.dp))

                        // Quick Preset Pills (Morning, Afternoon, Evening, Night)
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(4.dp)
                        ) {
                            val presets = listOf(
                                "Morning" to (8 to "08:00 AM - 08:59 AM (08:00 - 08:59)"),
                                "Afternoon" to (13 to "01:00 PM - 01:59 PM (13:00 - 13:59)"),
                                "Evening" to (17 to "05:00 PM - 05:59 PM (17:00 - 17:59)"),
                                "Night" to (21 to "09:00 PM - 09:59 PM (21:00 - 21:59)")
                            )
                            presets.forEach { (label, data) ->
                                val (h, fullLabel) = data
                                val isFuture = isToday && h > nowHour
                                Surface(
                                    color = if (isFuture) Color(0xFF0F172A).copy(alpha = 0.4f) else Color(0xFF0F172A),
                                    shape = RoundedCornerShape(6.dp),
                                    border = BorderStroke(1.dp, if (isFuture) Color(0xFF334155).copy(alpha = 0.3f) else Color(0xFF334155)),
                                    modifier = Modifier
                                        .weight(1f)
                                        .clickable(enabled = !isFuture) {
                                            val hourStr = String.format(Locale.getDefault(), "%02d", h)
                                            startTime = "$hourStr:00:00"
                                            endTime = "$hourStr:59:59"
                                            selectedTimeSlot = fullLabel
                                        }
                                ) {
                                    Text(
                                        text = label,
                                        color = if (isFuture) Color(0xFF64748B) else Color.White,
                                        fontSize = 10.sp,
                                        fontWeight = FontWeight.Medium,
                                        textAlign = TextAlign.Center,
                                        modifier = Modifier.padding(vertical = 5.dp)
                                    )
                                }
                            }
                        }

                        Spacer(modifier = Modifier.height(8.dp))

                        // Scrollable 24-Hour Chips Matrix
                        LazyRow(
                            horizontalArrangement = Arrangement.spacedBy(5.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            items((0..23).toList()) { h ->
                                val hourStr = String.format(Locale.getDefault(), "%02d", h)
                                val isSelected = startTime.startsWith(hourStr)
                                val isFuture = isToday && (h > nowHour)

                                val displayAmPm = when {
                                    h == 0 -> "12 AM"
                                    h < 12 -> "$h AM"
                                    h == 12 -> "12 PM"
                                    else -> "${h - 12} PM"
                                }

                                Surface(
                                    color = when {
                                        isFuture -> Color(0xFF0F172A).copy(alpha = 0.3f)
                                        isSelected -> Color(0xFF38BDF8)
                                        else -> Color(0xFF0F172A)
                                    },
                                    shape = RoundedCornerShape(6.dp),
                                    border = BorderStroke(
                                        1.dp,
                                        when {
                                            isFuture -> Color(0xFF334155).copy(alpha = 0.2f)
                                            isSelected -> Color(0xFF38BDF8)
                                            else -> Color(0xFF334155)
                                        }
                                    ),
                                    modifier = Modifier.clickable(enabled = !isFuture) {
                                        startTime = "$hourStr:00:00"
                                        endTime = "$hourStr:59:59"
                                        val amPmStr = if (h < 12) String.format(Locale.getDefault(), "%02d:00 AM", if (h == 0) 12 else h) else String.format(Locale.getDefault(), "%02d:00 PM", if (h == 12) 12 else h - 12)
                                        selectedTimeSlot = "$amPmStr ($hourStr:00 - $hourStr:59)"
                                    }
                                ) {
                                    Text(
                                        text = displayAmPm,
                                        color = when {
                                            isFuture -> Color(0xFF475569)
                                            isSelected -> Color(0xFF0F172A)
                                            else -> Color.White
                                        },
                                        fontSize = 11.sp,
                                        fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
                                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp)
                                    )
                                }
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))

                // Primary CTA Button: Start Sync Playback
                Button(
                    onClick = {
                        val nowHour = try { SimpleDateFormat("H", Locale.getDefault()).format(Date()).toInt() } catch (e: Exception) { 23 }
                        val startH = try { startTime.take(2).toInt() } catch (e: Exception) { 0 }

                        if (selectedDate.compareTo(todayDateStr) > 0) {
                            Toast.makeText(context, "Future dates cannot be selected for recorded NVR playback.", Toast.LENGTH_LONG).show()
                            return@Button
                        }
                        if (selectedDate == todayDateStr && startH > nowHour) {
                            Toast.makeText(context, "Future time slots cannot be selected for recorded NVR playback.", Toast.LENGTH_LONG).show()
                            return@Button
                        }

                        if (!isMultiSyncMode) {
                            activeRtspUrl = RtspUrlBuilder.buildPlaybackRtspUrl(
                                camera = currentCam!!,
                                isRemoteMode = isRemoteMode,
                                startDateStr = cleanStartDate,
                                startTimeStr = cleanStartTime,
                                endDateStr = cleanEndDate,
                                endTimeStr = cleanEndTime
                            )
                        }
                        isPlaybackActive = true
                        showSetupBottomSheet = false
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = if (isMultiSyncMode) Color(0xFF8B5CF6) else Color(0xFF10B981)),
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(46.dp)
                ) {
                    Icon(Icons.Default.PlayArrow, contentDescription = "Start Playback", tint = Color.White)
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        text = if (isMultiSyncMode) "Start Sync Playback (${selectedSyncCamIds.size} Feeds)" else "Start Single Playback",
                        color = Color.White,
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp
                    )
                }
            }
        }
    }

    if (showCalendarPicker) {
        CalendarDatePickerDialog(
            initialDateStr = selectedDate,
            onDateSelected = {
                selectedDate = it
                activeRtspUrl = "" // Reset to Idle
                isPlaybackActive = false
            },
            onDismiss = { showCalendarPicker = false }
        )
    }

    if (showTimePickerModal) {
        ClockTimePickerDialog(
            initialStartTimeStr = startTime,
            initialEndTimeStr = endTime,
            onTimeRangeSelected = { sTime, eTime, displayStr ->
                startTime = sTime
                endTime = eTime
                selectedTimeSlot = displayStr
                activeRtspUrl = "" // Reset to Idle
                isPlaybackActive = false
            },
            onDismiss = { showTimePickerModal = false }
        )
    }

    if (showMaxLimitAlert) {
        AlertDialog(
            onDismissRequest = { showMaxLimitAlert = false },
            title = {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.Warning, contentDescription = "Alert", tint = Color(0xFFF59E0B))
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("Download Limit Exceeded", color = Color.White, fontWeight = FontWeight.Bold)
                }
            },
            text = {
                Text(
                    text = "Maximum download limit is 5 minutes. Please shorten your selection.",
                    color = Color(0xFFCBD5E1),
                    fontSize = 13.sp
                )
            },
            confirmButton = {
                Button(
                    onClick = { showMaxLimitAlert = false },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF3B82F6))
                ) {
                    Text("OK", color = Color.White)
                }
            },
            containerColor = Color(0xFF1E293B)
        )
    }

    if (showExportProgressDialog) {
        ClipExportProgressDialog(
            cameraName = currentCam!!.name,
            totalSeconds = activeExportSeconds,
            rtspUrl = if (activeRtspUrl.isNotBlank()) activeRtspUrl else RtspUrlBuilder.buildPlaybackRtspUrl(currentCam!!, isRemoteMode, cleanStartDate, cleanStartTime, cleanEndDate, cleanEndTime),
            onDismiss = { showExportProgressDialog = false },
            onCompleted = { fileName ->
                showExportProgressDialog = false
                Toast.makeText(context, "Clip saved successfully to Downloads/Gallery", Toast.LENGTH_LONG).show()
            }
        )
    }
}

@Composable
fun CalendarDatePickerDialog(
    initialDateStr: String,
    onDateSelected: (String) -> Unit,
    onDismiss: () -> Unit
) {
    val todayCal = remember { java.util.Calendar.getInstance() }
    val displayCal = remember {
        java.util.Calendar.getInstance().apply {
            try {
                val parts = initialDateStr.split("-")
                if (parts.size == 3) {
                    set(java.util.Calendar.YEAR, parts[0].toInt())
                    set(java.util.Calendar.MONTH, parts[1].toInt() - 1)
                    set(java.util.Calendar.DAY_OF_MONTH, parts[2].toInt())
                }
            } catch (e: Exception) {}
        }
    }

    var displayedYear by remember { mutableIntStateOf(displayCal.get(java.util.Calendar.YEAR)) }
    var displayedMonth by remember { mutableIntStateOf(displayCal.get(java.util.Calendar.MONTH)) }
    var selectedDay by remember { mutableIntStateOf(displayCal.get(java.util.Calendar.DAY_OF_MONTH)) }

    val monthFormat = remember { SimpleDateFormat("MMMM yyyy", Locale.getDefault()) }

    val isCurrentMonth = remember(displayedYear, displayedMonth) {
        displayedYear == todayCal.get(java.util.Calendar.YEAR) && displayedMonth == todayCal.get(java.util.Calendar.MONTH)
    }
    val minCal = remember {
        java.util.Calendar.getInstance().apply { add(java.util.Calendar.MONTH, -6) }
    }
    val isMinMonth = remember(displayedYear, displayedMonth) {
        (displayedYear < minCal.get(java.util.Calendar.YEAR)) ||
        (displayedYear == minCal.get(java.util.Calendar.YEAR) && displayedMonth <= minCal.get(java.util.Calendar.MONTH))
    }

    val monthText = remember(displayedYear, displayedMonth) {
        val cal = java.util.Calendar.getInstance().apply {
            set(java.util.Calendar.YEAR, displayedYear)
            set(java.util.Calendar.MONTH, displayedMonth)
            set(java.util.Calendar.DAY_OF_MONTH, 1)
        }
        monthFormat.format(cal.time)
    }

    Dialog(onDismissRequest = onDismiss) {
        Card(
            modifier = Modifier
                .fillMaxWidth(0.95f)
                .wrapContentHeight(),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            shape = RoundedCornerShape(16.dp),
            elevation = CardDefaults.cardElevation(defaultElevation = 8.dp)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            text = monthText,
                            color = Color(0xFF1E293B),
                            fontWeight = FontWeight.Bold,
                            fontSize = 15.sp
                        )
                    }

                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        IconButton(
                            onClick = {
                                if (!isMinMonth) {
                                    if (displayedMonth == 0) {
                                        displayedMonth = 11
                                        displayedYear -= 1
                                    } else {
                                        displayedMonth -= 1
                                    }
                                }
                            },
                            enabled = !isMinMonth,
                            modifier = Modifier.size(28.dp)
                        ) {
                            Icon(
                                Icons.Default.ChevronLeft,
                                contentDescription = "Prev",
                                tint = if (!isMinMonth) Color.Black else Color.LightGray
                            )
                        }
                        IconButton(
                            onClick = {
                                if (!isCurrentMonth) {
                                    if (displayedMonth == 11) {
                                        displayedMonth = 0
                                        displayedYear += 1
                                    } else {
                                        displayedMonth += 1
                                    }
                                }
                            },
                            enabled = !isCurrentMonth,
                            modifier = Modifier.size(28.dp)
                        ) {
                            Icon(
                                Icons.Default.ChevronRight,
                                contentDescription = "Next",
                                tint = if (!isCurrentMonth) Color.Black else Color.LightGray
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceAround
                ) {
                    listOf("S", "M", "T", "W", "T", "F", "S").forEach { day ->
                        Text(
                            text = day,
                            color = Color(0xFF64748B),
                            fontWeight = FontWeight.Bold,
                            fontSize = 12.sp
                        )
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))

                val calForMonth = java.util.Calendar.getInstance().apply {
                    set(java.util.Calendar.YEAR, displayedYear)
                    set(java.util.Calendar.MONTH, displayedMonth)
                    set(java.util.Calendar.DAY_OF_MONTH, 1)
                }
                val daysInMonth = calForMonth.getActualMaximum(java.util.Calendar.DAY_OF_MONTH)
                val firstDayOfWeekOffset = calForMonth.get(java.util.Calendar.DAY_OF_WEEK) - 1

                LazyVerticalGrid(
                    columns = GridCells.Fixed(7),
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(210.dp)
                ) {
                    items(firstDayOfWeekOffset) {
                        Box(modifier = Modifier.size(36.dp))
                    }
                    items(daysInMonth) { index ->
                        val dayNum = index + 1
                        val isSelected = (dayNum == selectedDay) && (displayedMonth == displayCal.get(java.util.Calendar.MONTH)) && (displayedYear == displayCal.get(java.util.Calendar.YEAR))
                        val isFutureDay = isCurrentMonth && (dayNum > todayCal.get(java.util.Calendar.DAY_OF_MONTH))

                        Box(
                            modifier = Modifier
                                .size(36.dp)
                                .background(
                                    color = if (isSelected) Color(0xFF38BDF8) else Color.Transparent,
                                    shape = CircleShape
                                )
                                .clickable(enabled = !isFutureDay) {
                                    selectedDay = dayNum
                                    val formatted = String.format(Locale.getDefault(), "%04d-%02d-%02d", displayedYear, displayedMonth + 1, dayNum)
                                    onDateSelected(formatted)
                                    onDismiss()
                                },
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                text = dayNum.toString(),
                                color = when {
                                    isFutureDay -> Color(0xFFCBD5E1)
                                    isSelected -> Color.White
                                    else -> Color(0xFF334155)
                                },
                                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
                                fontSize = 12.sp
                            )
                        }
                    }
                }
            }
        }
    }
}

// Master YouTube & Netflix-Style True Immersive Fullscreen Player View
@Composable
fun FullScreenMovieViewer(
    data: FullscreenData,
    onDismiss: () -> Unit
) {
    val context = LocalContext.current
    var playerInstance by remember { mutableStateOf<MediaPlayer?>(null) }
    var vlcLayoutInstance by remember { mutableStateOf<VLCVideoLayout?>(null) }
    var showControls by remember { mutableStateOf(true) }
    var isFitMode by remember { mutableStateOf(false) }
    var isPlayingState by remember { mutableStateOf(true) }

    // Touch-To-Show 3.5 Seconds Auto-Hide Controls Timer
    LaunchedEffect(showControls) {
        if (showControls) {
            delay(3500)
            showControls = false
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black)
            .clickable { showControls = !showControls }
    ) {
        RtspVideoPlayer(
            rtspUrl = data.rtspUrl,
            modifier = Modifier.fillMaxSize(),
            onMediaPlayerReady = { player ->
                playerInstance = player
                try {
                    player.videoScale = if (isFitMode) MediaPlayer.ScaleType.SURFACE_BEST_FIT else MediaPlayer.ScaleType.SURFACE_FILL
                    player.aspectRatio = if (isFitMode) "16:9" else null
                } catch (e: Exception) {}
            },
            onLayoutCreated = { vlcLayoutInstance = it },
            onPlayingStateChanged = { playing ->
                isPlayingState = playing
            }
        )

        if (showControls) {
            // Touch Controls Overlay Layer
            Box(modifier = Modifier.fillMaxSize()) {
                // Top Control Bar
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .align(Alignment.TopCenter)
                        .background(Color.Black.copy(alpha = 0.65f))
                        .padding(horizontal = 16.dp, vertical = 10.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = data.titleText,
                        color = if (data.isPlayback) Color(0xFFF59E0B) else Color(0xFF10B981),
                        fontWeight = FontWeight.Bold,
                        fontSize = 13.sp
                    )

                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            onClick = {
                                isFitMode = !isFitMode
                                playerInstance?.let { p ->
                                    p.videoScale = if (isFitMode) MediaPlayer.ScaleType.SURFACE_BEST_FIT else MediaPlayer.ScaleType.SURFACE_FILL
                                    p.aspectRatio = if (isFitMode) "16:9" else null
                                }
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF475569)),
                            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                            modifier = Modifier.height(32.dp)
                        ) {
                            Text(if (isFitMode) "Aspect: Fit" else "Aspect: Fill", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        }

                        Button(
                            onClick = {
                                takeCameraSnapshot(context, playerInstance, data.cameraName, vlcLayoutInstance)
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF3B82F6)),
                            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                            modifier = Modifier.height(32.dp)
                        ) {
                            Icon(Icons.Default.CameraAlt, contentDescription = "Capture", modifier = Modifier.size(14.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Capture", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        }

                        if (data.onDownloadClipClick != null) {
                            Button(
                                onClick = data.onDownloadClipClick,
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF8B5CF6)),
                                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                                modifier = Modifier.height(32.dp)
                            ) {
                                Icon(Icons.Default.Download, contentDescription = "Clip", modifier = Modifier.size(14.dp))
                                Spacer(modifier = Modifier.width(4.dp))
                                Text("Clip Range", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                            }
                        }

                        Button(
                            onClick = onDismiss,
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFEF4444)),
                            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp),
                            modifier = Modifier.height(32.dp)
                        ) {
                            Icon(Icons.Default.FullscreenExit, contentDescription = "Exit", modifier = Modifier.size(14.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Exit Full Screen", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }

                // Center Play / Pause Big Toggle Button
                Box(
                    modifier = Modifier.align(Alignment.Center)
                ) {
                    IconButton(
                        onClick = {
                            val player = playerInstance
                            if (player != null) {
                                if (player.isPlaying) {
                                    try {
                                        player.pause()
                                    } catch (e: Exception) {
                                        player.stop()
                                    }
                                    isPlayingState = false
                                } else {
                                    try {
                                        player.play()
                                    } catch (e: Exception) {}
                                    isPlayingState = true
                                }
                            }
                        },
                        modifier = Modifier
                            .size(64.dp)
                            .background(Color.Black.copy(alpha = 0.6f), CircleShape)
                    ) {
                        Icon(
                            imageVector = if (isPlayingState) Icons.Default.Pause else Icons.Default.PlayArrow,
                            contentDescription = "Play/Pause",
                            tint = Color.White,
                            modifier = Modifier.size(36.dp)
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun ClipExportProgressDialog(
    cameraName: String,
    totalSeconds: Long,
    rtspUrl: String,
    onDismiss: () -> Unit,
    onCompleted: (String) -> Unit
) {
    val context = LocalContext.current
    var isStarting by remember { mutableStateOf(true) }

    val moviesDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MOVIES)
    val appDir = remember {
        File(moviesDir, "VisionConnect").apply { if (!exists()) mkdirs() }
    }
    val timeStamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(Date())
    val cleanName = cameraName.replace(Regex("[^a-zA-Z0-9_]"), "_")
    val outputFile = remember { File(appDir, "CLIP_${cleanName}_$timeStamp.mp4") }

    // Start background download and immediately dismiss
    LaunchedEffect(Unit) {
        Toast.makeText(context, "⬇️ Download started in background (${totalSeconds}s clip)...", Toast.LENGTH_LONG).show()
        isStarting = false

        // Launch download on background thread — user can continue using the app
        withContext(Dispatchers.IO) {
            try {
                val options = ArrayList<String>().apply {
                    add("--drop-late-frames")
                    add("--skip-frames")
                    add("--rtsp-tcp")
                    add("--no-audio")
                    add("--sout=#std{access=file,mux=mp4,dst='${outputFile.absolutePath}'}")
                }
                val libVlc = LibVLC(context, options)
                val player = MediaPlayer(libVlc)

                val media = Media(libVlc, Uri.parse(rtspUrl)).apply {
                    addOption(":sout=#std{access=file,mux=mp4,dst='${outputFile.absolutePath}'}")
                    addOption(":network-caching=100")
                    addOption(":rtsp-tcp")
                    addOption(":clock-jitter=0")
                    addOption(":no-audio")
                }
                player.media = media
                media.release()
                player.play()

                // Wait for the clip duration
                delay(totalSeconds * 1000L)

                try {
                    player.stop()
                    player.release()
                    libVlc.release()
                } catch (e: Exception) {}

                MediaScannerConnection.scanFile(
                    context,
                    arrayOf(outputFile.absolutePath),
                    arrayOf("video/mp4")
                ) { _, _ -> }

                withContext(Dispatchers.Main) {
                    Toast.makeText(context, "✅ Clip saved: ${outputFile.name}", Toast.LENGTH_LONG).show()
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(context, "❌ Download failed: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }

        onCompleted(outputFile.name)
    }

    // Show brief "Starting Download" indicator then auto-dismiss
    if (isStarting) {
        AlertDialog(
            onDismissRequest = onDismiss,
            title = {
                Text("Starting Download...", color = Color.White, fontWeight = FontWeight.Bold)
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        text = "Downloading ${totalSeconds}s clip from $cameraName in background.\nYou can continue using the app.",
                        color = Color(0xFF94A3B8),
                        fontSize = 13.sp
                    )
                    LinearProgressIndicator(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(4.dp),
                        color = Color(0xFF8B5CF6),
                        trackColor = Color(0xFF334155)
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = onDismiss,
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF10B981))
                ) {
                    Text("OK, Run in Background", color = Color.White, fontWeight = FontWeight.Bold)
                }
            },
            containerColor = Color(0xFF1E293B)
        )
    } else {
        // Auto-dismiss after launching
        LaunchedEffect(Unit) {
            onDismiss()
        }
    }
}

@Composable
fun CamerasTabScreen(
    cameraList: List<CameraEntity>,
    isRemoteMode: Boolean,
    onEditCamera: (CameraEntity) -> Unit,
    onDeleteCamera: (CameraEntity) -> Unit,
    onSelectLive: (CameraEntity) -> Unit
) {
    if (cameraList.isEmpty()) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("No cameras saved in local database.", color = Color.White)
        }
    } else {
        LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            items(cameraList) { cam ->
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF1E293B)),
                    shape = RoundedCornerShape(14.dp)
                ) {
                    Column(modifier = Modifier.padding(14.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(cam.name, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                            Text(cam.nvrBrand.uppercase(), color = Color(0xFF3B82F6), fontWeight = FontWeight.Bold, fontSize = 10.sp)
                        }

                        Text("Location: ${cam.location}", color = Color(0xFF94A3B8), fontSize = 12.sp)
                        Text(
                            text = "Host: ${if (isRemoteMode) cam.remoteHost else cam.localIp}:${cam.rtspPort} • Ch ${cam.channel}",
                            color = Color(0xFF10B981),
                            fontSize = 11.sp
                        )

                        Spacer(modifier = Modifier.height(10.dp))

                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(
                                onClick = { onSelectLive(cam) },
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF10B981)),
                                modifier = Modifier.weight(1f)
                            ) {
                                Icon(Icons.Default.Videocam, contentDescription = "Live", modifier = Modifier.size(16.dp))
                                Spacer(modifier = Modifier.width(4.dp))
                                Text("Live Stream", fontSize = 11.sp)
                            }
                            Button(
                                onClick = { onEditCamera(cam) },
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF334155))
                            ) {
                                Icon(Icons.Default.Edit, contentDescription = "Edit", modifier = Modifier.size(16.dp))
                            }
                            Button(
                                onClick = { onDeleteCamera(cam) },
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFEF4444))
                            ) {
                                Icon(Icons.Default.Delete, contentDescription = "Delete", modifier = Modifier.size(16.dp))
                            }
                        }
                    }
                }
            }
        }
    }
}

// Minimalist High-Contrast Monochrome Text Field Component
@Composable
fun MonochromeTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    placeholder: String = "",
    helperText: String = "",
    isPassword: Boolean = false,
    keyboardType: KeyboardType = KeyboardType.Text,
    isDark: Boolean = true,
    modifier: Modifier = Modifier
) {
    val textColor = if (isDark) Color.White else Color.Black
    val subtextColor = if (isDark) Color(0xFFA1A1AA) else Color(0xFF71717A)
    val inputBg = if (isDark) Color(0xFF1C1C1E) else Color(0xFFF2F2F7)
    val borderColor = if (isDark) Color(0xFF3A3A3C) else Color(0xFFE5E5EA)

    Column(modifier = modifier) {
        Text(
            text = label,
            color = textColor,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold
        )
        Spacer(modifier = Modifier.height(4.dp))
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            placeholder = { Text(placeholder, color = subtextColor, fontSize = 12.sp) },
            visualTransformation = if (isPassword) PasswordVisualTransformation() else VisualTransformation.None,
            keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
            singleLine = true,
            colors = OutlinedTextFieldDefaults.colors(
                focusedContainerColor = inputBg,
                unfocusedContainerColor = inputBg,
                focusedBorderColor = textColor,
                unfocusedBorderColor = borderColor,
                focusedTextColor = textColor,
                unfocusedTextColor = textColor,
                cursorColor = textColor
            ),
            shape = RoundedCornerShape(8.dp),
            modifier = Modifier.fillMaxWidth()
        )
        if (helperText.isNotBlank()) {
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = helperText,
                color = subtextColor,
                fontSize = 10.sp
            )
        }
    }
}

// Minimalist High-Contrast Black & White Camera Creation Popup
@Composable
fun CameraConfigDialog(
    initialCamera: CameraEntity?,
    onDismiss: () -> Unit,
    onSave: (CameraEntity) -> Unit
) {
    val isDark = androidx.compose.foundation.isSystemInDarkTheme()
    val dialogBg = if (isDark) Color(0xFF121212) else Color(0xFFFFFFFF)
    val textColor = if (isDark) Color(0xFFFFFFFF) else Color(0xFF000000)
    val subtextColor = if (isDark) Color(0xFFA1A1AA) else Color(0xFF71717A)
    val inputBg = if (isDark) Color(0xFF1C1C1E) else Color(0xFFF2F2F7)
    val borderColor = if (isDark) Color(0xFF3A3A3C) else Color(0xFFE5E5EA)
    val primaryBtnBg = if (isDark) Color(0xFFFFFFFF) else Color(0xFF000000)
    val primaryBtnText = if (isDark) Color(0xFF000000) else Color(0xFFFFFFFF)

    var name by remember { mutableStateOf(initialCamera?.name ?: "") }
    var location by remember { mutableStateOf(initialCamera?.location ?: "") }
    var localIp by remember { mutableStateOf(initialCamera?.localIp ?: "") }
    var remoteHost by remember { mutableStateOf(initialCamera?.remoteHost ?: "") }
    var rtspPort by remember { mutableStateOf(initialCamera?.rtspPort?.toString() ?: "554") }
    var httpPort by remember { mutableStateOf(initialCamera?.httpPort?.toString() ?: "80") }
    var username by remember { mutableStateOf(initialCamera?.username ?: "admin") }
    var password by remember { mutableStateOf(initialCamera?.password ?: "") }
    var channel by remember { mutableStateOf(initialCamera?.channel?.toString() ?: "1") }
    var nvrBrand by remember { mutableStateOf(initialCamera?.nvrBrand ?: "Hikvision") }

    var showBrandDropdown by remember { mutableStateOf(false) }

    // Test Connection States: 0 = Idle, 1 = Testing, 2 = Success, 3 = Failure
    var testStatus by remember { mutableIntStateOf(0) }
    val coroutineScope = rememberCoroutineScope()

    Dialog(onDismissRequest = onDismiss) {
        Card(
            modifier = Modifier
                .fillMaxWidth(0.96f)
                .fillMaxHeight(0.85f),
            colors = CardDefaults.cardColors(containerColor = dialogBg),
            shape = RoundedCornerShape(16.dp),
            border = BorderStroke(1.dp, borderColor)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(18.dp)
            ) {
                // Header Section (Fixed at top)
                Column {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = if (initialCamera != null) "Edit Device / Camera" else "Add New Device / Camera",
                            color = textColor,
                            fontWeight = FontWeight.Bold,
                            fontSize = 18.sp
                        )
                        IconButton(onClick = onDismiss, modifier = Modifier.size(24.dp)) {
                            Icon(Icons.Default.Close, contentDescription = "Close", tint = subtextColor)
                        }
                    }
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = "Configure your RTSP stream or NVR connection parameters below.",
                        color = subtextColor,
                        fontSize = 12.sp
                    )
                }

                Spacer(modifier = Modifier.height(10.dp))
                HorizontalDivider(color = borderColor, thickness = 1.dp)
                Spacer(modifier = Modifier.height(10.dp))

                // Scrollable Form Body (Middle)
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(14.dp)
                ) {
                    // Section 1: Basic Information
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("SECTION 1: BASIC INFORMATION", color = subtextColor, fontSize = 10.sp, fontWeight = FontWeight.Bold)

                        MonochromeTextField(
                            value = name,
                            onValueChange = { name = it },
                            label = "Device Name",
                            placeholder = "e.g., Warehouse Main Gate, Godown NVR",
                            helperText = "Give this feed a recognizable name for quick selection.",
                            isDark = isDark
                        )

                        MonochromeTextField(
                            value = location,
                            onValueChange = { location = it },
                            label = "Location Tag",
                            placeholder = "e.g., Zone A, Main Entrance",
                            isDark = isDark
                        )
                    }

                    HorizontalDivider(color = borderColor, thickness = 1.dp)

                    // Section 2: Connection Settings
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("SECTION 2: CONNECTION SETTINGS", color = subtextColor, fontSize = 10.sp, fontWeight = FontWeight.Bold)

                        MonochromeTextField(
                            value = localIp,
                            onValueChange = { localIp = it },
                            label = "IP Address or Hostname",
                            placeholder = "192.168.1.100 or godown.ddns.net",
                            helperText = "Local Wi-Fi IP address or remote public DDNS domain.",
                            isDark = isDark
                        )

                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            MonochromeTextField(
                                value = rtspPort,
                                onValueChange = { rtspPort = it },
                                label = "RTSP Port",
                                placeholder = "554",
                                keyboardType = KeyboardType.Number,
                                isDark = isDark,
                                modifier = Modifier.weight(1f)
                            )

                            MonochromeTextField(
                                value = httpPort,
                                onValueChange = { httpPort = it },
                                label = "HTTP / ONVIF Port",
                                placeholder = "80",
                                keyboardType = KeyboardType.Number,
                                isDark = isDark,
                                modifier = Modifier.weight(1f)
                            )
                        }
                    }

                    HorizontalDivider(color = borderColor, thickness = 1.dp)

                    // Section 3: Credentials & NVR Parameters
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("SECTION 3: CREDENTIALS & NVR PARAMETERS", color = subtextColor, fontSize = 10.sp, fontWeight = FontWeight.Bold)

                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            MonochromeTextField(
                                value = username,
                                onValueChange = { username = it },
                                label = "Device Username",
                                placeholder = "admin",
                                isDark = isDark,
                                modifier = Modifier.weight(1f)
                            )

                            MonochromeTextField(
                                value = password,
                                onValueChange = { password = it },
                                label = "Device Password",
                                placeholder = "••••••••",
                                isPassword = true,
                                isDark = isDark,
                                modifier = Modifier.weight(1f)
                            )
                        }

                        MonochromeTextField(
                            value = channel,
                            onValueChange = { channel = it },
                            label = "Channel Number",
                            placeholder = "1",
                            helperText = "For single cameras, keep as 1. For NVRs, enter target channel.",
                            keyboardType = KeyboardType.Number,
                            isDark = isDark
                        )

                        // NVR Brand / Protocol Preset Dropdown matching Selected Tab Width & Highlight
                        Column {
                            Text("NVR Brand / Protocol Preset", color = textColor, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                            Spacer(modifier = Modifier.height(4.dp))
                            Box(modifier = Modifier.fillMaxWidth()) {
                                Surface(
                                    color = inputBg,
                                    shape = RoundedCornerShape(8.dp),
                                    border = BorderStroke(1.dp, borderColor),
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clickable { showBrandDropdown = true }
                                ) {
                                    Row(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .padding(horizontal = 12.dp, vertical = 12.dp),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text(nvrBrand, color = textColor, fontSize = 13.sp)
                                        Icon(Icons.Default.ArrowDropDown, contentDescription = "Dropdown", tint = subtextColor)
                                    }
                                }

                                DropdownMenu(
                                    expanded = showBrandDropdown,
                                    onDismissRequest = { showBrandDropdown = false },
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .heightIn(max = 220.dp)
                                        .background(if (isDark) Color(0xFF1C1C1E) else Color.White)
                                ) {
                                    listOf("Hikvision", "Dahua", "UNV (Uniview)", "ONVIF Generic", "Custom RTSP").forEach { brand ->
                                        val isSelected = brand == nvrBrand
                                        val itemBg = if (isSelected) {
                                            if (isDark) Color(0xFF2C2C2E) else Color(0xFFE0F2FE)
                                        } else Color.Transparent
                                        val itemTextColor = if (isSelected) {
                                            if (isDark) Color.White else Color(0xFF0284C7)
                                        } else {
                                            if (isDark) Color(0xFFCCCCCC) else Color(0xFF333333)
                                        }

                                        DropdownMenuItem(
                                            text = {
                                                Text(
                                                    text = brand,
                                                    fontSize = 13.sp,
                                                    fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
                                                    color = itemTextColor
                                                )
                                            },
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .background(itemBg),
                                            onClick = {
                                                nvrBrand = brand
                                                showBrandDropdown = false
                                            }
                                        )
                                    }
                                }
                            }
                            Spacer(modifier = Modifier.height(2.dp))
                            Text(
                                text = "Auto-configures RTSP playback parameter formatting.",
                                color = subtextColor,
                                fontSize = 10.sp
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(4.dp))

                    // Test Connection Button with Visual Feedback
                    OutlinedButton(
                        onClick = {
                            testStatus = 1
                            coroutineScope.launch(Dispatchers.IO) {
                                val hostToTest = localIp.ifBlank { remoteHost }
                                val portInt = rtspPort.toIntOrNull() ?: 554
                                val success = try {
                                    val socket = java.net.Socket()
                                    socket.connect(java.net.InetSocketAddress(hostToTest, portInt), 2500)
                                    socket.close()
                                    true
                                } catch (e: Exception) {
                                    false
                                }
                                withContext(Dispatchers.Main) {
                                    testStatus = if (success) 2 else 3
                                }
                            }
                        },
                        border = BorderStroke(1.dp, borderColor),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        when (testStatus) {
                            1 -> {
                                CircularProgressIndicator(modifier = Modifier.size(16.dp), color = textColor, strokeWidth = 2.dp)
                                Spacer(modifier = Modifier.width(8.dp))
                                Text("Testing Connection...", color = textColor, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            }
                            2 -> {
                                Icon(Icons.Default.Check, contentDescription = "Success", tint = Color(0xFF10B981), modifier = Modifier.size(16.dp))
                                Spacer(modifier = Modifier.width(8.dp))
                                Text("Connection Successful", color = Color(0xFF10B981), fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            }
                            3 -> {
                                Icon(Icons.Default.Close, contentDescription = "Failure", tint = Color(0xFFEF4444), modifier = Modifier.size(16.dp))
                                Spacer(modifier = Modifier.width(8.dp))
                                Text("Host Unreachable", color = Color(0xFFEF4444), fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            }
                            else -> {
                                Icon(Icons.Default.Refresh, contentDescription = "Test", tint = textColor, modifier = Modifier.size(16.dp))
                                Spacer(modifier = Modifier.width(8.dp))
                                Text("Test Connection", color = textColor, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))
                HorizontalDivider(color = borderColor, thickness = 1.dp)
                Spacer(modifier = Modifier.height(10.dp))

                // Footer Action Buttons (Fixed at bottom)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    OutlinedButton(
                        onClick = onDismiss,
                        border = BorderStroke(1.dp, borderColor),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier
                            .weight(1f)
                            .height(42.dp)
                    ) {
                        Text("Cancel", color = textColor, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                    }

                    Button(
                        onClick = {
                            if (name.isNotBlank() && localIp.isNotBlank()) {
                                val camera = CameraEntity(
                                    id = initialCamera?.id ?: 0L,
                                    name = name,
                                    location = location,
                                    localIp = localIp,
                                    remoteHost = remoteHost.ifBlank { localIp },
                                    rtspPort = rtspPort.toIntOrNull() ?: 554,
                                    httpPort = httpPort.toIntOrNull() ?: 80,
                                    username = username,
                                    password = password,
                                    channel = channel.toIntOrNull() ?: 1,
                                    nvrBrand = nvrBrand
                                )
                                onSave(camera)
                            }
                        },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = primaryBtnBg,
                            contentColor = primaryBtnText
                        ),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier
                            .weight(1f)
                            .height(42.dp)
                    ) {
                        Text("Save & Connect", fontWeight = FontWeight.Bold, fontSize = 13.sp)
                    }
                }
            }
        }
    }
}
