package com.example.godownvision.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.widget.Toast
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.QrCode2
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Tv
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.godownvision.services.DlnaCastManager
import com.example.godownvision.services.DlnaDevice
import com.example.godownvision.services.LocalCastServer
import com.example.godownvision.services.QrCodeGenerator
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CastBottomSheetModal(
    activeCameraName: String,
    activeRtspUrl: String,
    onDismiss: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    var isScanningDlna by remember { mutableStateOf(false) }
    var discoveredTvs by remember { mutableStateOf<List<DlnaDevice>>(emptyList()) }
    var activeCastTarget by remember { mutableStateOf<String?>(null) }
    var isServerActive by remember { mutableStateOf(LocalCastServer.isRunning()) }
    var localCastUrl by remember { mutableStateOf(LocalCastServer.getCastUrl(context)) }

    // Automatically start local HTTP server and scan for DLNA TVs on open
    LaunchedEffect(Unit) {
        val serverUrl = LocalCastServer.startServer(context, 8080, activeCameraName, activeRtspUrl)
        localCastUrl = serverUrl
        isServerActive = true

        isScanningDlna = true
        discoveredTvs = DlnaCastManager.discoverDevices(context)
        isScanningDlna = false
    }

    val qrBitmap = remember(localCastUrl) {
        QrCodeGenerator.generateQrCodeBitmap(localCastUrl, 320)
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = Color(0xFF0F172A),
        shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 10.dp)
        ) {
            // Header
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .size(32.dp)
                            .background(Color(0xFF38BDF8).copy(alpha = 0.2f), CircleShape),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(Icons.Default.Tv, contentDescription = "Cast", tint = Color(0xFF38BDF8), modifier = Modifier.size(18.dp))
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Column {
                        Text("Zero-Dependency Local Cast Engine", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                        Text("Project feed to Smart TVs & Browsers on Wi-Fi", color = Color(0xFF94A3B8), fontSize = 10.sp)
                    }
                }

                IconButton(onClick = onDismiss) {
                    Icon(Icons.Default.Close, contentDescription = "Close", tint = Color.White)
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Active Cast Status Banner
            if (activeCastTarget != null || isServerActive) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF1E293B)),
                    shape = RoundedCornerShape(10.dp),
                    border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(Color(0xFF10B981)))
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(10.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(modifier = Modifier.size(8.dp).background(Color(0xFF10B981), CircleShape))
                            Spacer(modifier = Modifier.width(8.dp))
                            Column {
                                Text(
                                    text = if (activeCastTarget != null) "Casting to $activeCastTarget" else "Local Web Server Active",
                                    color = Color.White,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 11.sp
                                )
                                Text(localCastUrl, color = Color(0xFF38BDF8), fontSize = 10.sp)
                            }
                        }

                        Button(
                            onClick = {
                                scope.launch {
                                    LocalCastServer.stopServer()
                                    isServerActive = false
                                    activeCastTarget = null
                                    Toast.makeText(context, "Casting Session Stopped", Toast.LENGTH_SHORT).show()
                                }
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFEF4444)),
                            shape = RoundedCornerShape(8.dp),
                            contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                            modifier = Modifier.height(30.dp)
                        ) {
                            Icon(Icons.Default.Stop, contentDescription = "Stop", tint = Color.White, modifier = Modifier.size(14.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Stop Cast", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color.White)
                        }
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))
            }

            // Section 1: Discovered Smart TVs (DLNA / UPnP)
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = Color(0xFF1E293B)),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text("1. SMART TV CAST (DLNA / UPnP)", color = Color(0xFF38BDF8), fontWeight = FontWeight.Bold, fontSize = 11.sp)

                        IconButton(
                            onClick = {
                                scope.launch {
                                    isScanningDlna = true
                                    discoveredTvs = DlnaCastManager.discoverDevices(context)
                                    isScanningDlna = false
                                }
                            },
                            modifier = Modifier.size(28.dp)
                        ) {
                            if (isScanningDlna) {
                                CircularProgressIndicator(modifier = Modifier.size(16.dp), color = Color(0xFF38BDF8), strokeWidth = 2.dp)
                            } else {
                                Icon(Icons.Default.Refresh, contentDescription = "Scan", tint = Color.White, modifier = Modifier.size(16.dp))
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(6.dp))

                    if (discoveredTvs.isEmpty()) {
                        Text(
                            text = if (isScanningDlna) "Searching Wi-Fi network for Smart TVs..." else "No DLNA Smart TVs auto-detected. Use Method 2 below for any TV/PC browser.",
                            color = Color(0xFF94A3B8),
                            fontSize = 10.sp
                        )
                    } else {
                        LazyColumn(modifier = Modifier.height(120.dp)) {
                            items(discoveredTvs) { tv ->
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(vertical = 4.dp)
                                        .background(Color(0xFF0F172A), RoundedCornerShape(8.dp))
                                        .padding(8.dp),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Icon(Icons.Default.Tv, contentDescription = "TV", tint = Color.White, modifier = Modifier.size(20.dp))
                                        Spacer(modifier = Modifier.width(8.dp))
                                        Column {
                                            Text(tv.friendlyName, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 11.sp)
                                            Text("${tv.manufacturer} • ${tv.ipAddress}", color = Color(0xFF94A3B8), fontSize = 9.sp)
                                        }
                                    }

                                    Button(
                                        onClick = {
                                            scope.launch {
                                                val streamUrl = "$localCastUrl/stream"
                                                val success = DlnaCastManager.playMediaOnTv(tv, streamUrl)
                                                if (success) {
                                                    activeCastTarget = tv.friendlyName
                                                    Toast.makeText(context, "Casting stream to ${tv.friendlyName}", Toast.LENGTH_SHORT).show()
                                                } else {
                                                    Toast.makeText(context, "Failed to cast via DLNA to ${tv.friendlyName}. Try Method 2.", Toast.LENGTH_LONG).show()
                                                }
                                            }
                                        },
                                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF10B981)),
                                        shape = RoundedCornerShape(6.dp),
                                        contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 8.dp, vertical = 2.dp),
                                        modifier = Modifier.height(26.dp)
                                    ) {
                                        Text("Cast to TV", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color(0xFF0F172A))
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Section 2: Browser & Tablet Cast (Embedded Server & QR Code)
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = Color(0xFF1E293B)),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Text("2. BROWSER CAST & QR CODE (ANY DEVICE)", color = Color(0xFFC084FC), fontWeight = FontWeight.Bold, fontSize = 11.sp)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text("Scan QR code or open URL in any TV/PC browser on local Wi-Fi:", color = Color(0xFF94A3B8), fontSize = 10.sp)

                    Spacer(modifier = Modifier.height(8.dp))

                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(Color(0xFF0F172A), RoundedCornerShape(8.dp))
                            .border(1.dp, Color(0xFF334155), RoundedCornerShape(8.dp))
                            .padding(horizontal = 10.dp, vertical = 6.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(localCastUrl, color = Color(0xFF38BDF8), fontWeight = FontWeight.Bold, fontSize = 12.sp)

                        IconButton(
                            onClick = {
                                val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                                val clip = ClipData.newPlainText("Cast URL", localCastUrl)
                                clipboard.setPrimaryClip(clip)
                                Toast.makeText(context, "Copied URL to Clipboard", Toast.LENGTH_SHORT).show()
                            },
                            modifier = Modifier.size(28.dp)
                        ) {
                            Icon(Icons.Default.ContentCopy, contentDescription = "Copy", tint = Color.White, modifier = Modifier.size(16.dp))
                        }
                    }

                    Spacer(modifier = Modifier.height(10.dp))

                    // QR Code Display
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.Center,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Surface(
                            color = Color.White,
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier.padding(4.dp)
                        ) {
                            Image(
                                bitmap = qrBitmap.asImageBitmap(),
                                contentDescription = "Cast QR Code",
                                modifier = Modifier.size(140.dp)
                            )
                        }

                        Spacer(modifier = Modifier.width(12.dp))

                        Column {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.QrCode2, contentDescription = "Scan", tint = Color(0xFF38BDF8), modifier = Modifier.size(18.dp))
                                Spacer(modifier = Modifier.width(4.dp))
                                Text("Scan to Watch", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                            }
                            Spacer(modifier = Modifier.height(4.dp))
                            Text("1. Open phone camera or browser", color = Color(0xFF94A3B8), fontSize = 9.5.sp)
                            Text("2. Scan QR code above", color = Color(0xFF94A3B8), fontSize = 9.5.sp)
                            Text("3. Watch stream live on screen!", color = Color(0xFF10B981), fontWeight = FontWeight.Bold, fontSize = 9.5.sp)
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))
        }
    }
}
