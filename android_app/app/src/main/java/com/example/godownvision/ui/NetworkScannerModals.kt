package com.example.godownvision.ui

import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.example.godownvision.services.CameraNetworkScanner
import com.example.godownvision.services.DeviceAuthStatus
import com.example.godownvision.services.DiscoveredDevice
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

@Composable
fun RadarAnimation(isScanning: Boolean, modifier: Modifier = Modifier) {
    val infiniteTransition = rememberInfiniteTransition(label = "radar")
    val angle by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(1500, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "radar_rotation"
    )

    Box(
        modifier = modifier
            .size(72.dp)
            .border(2.dp, Color(0xFF10B981).copy(alpha = 0.5f), CircleShape)
            .padding(4.dp),
        contentAlignment = Alignment.Center
    ) {
        Box(
            modifier = Modifier
                .size(48.dp)
                .border(1.dp, Color(0xFF38BDF8).copy(alpha = 0.3f), CircleShape)
        )
        Icon(
            imageVector = Icons.Default.Search,
            contentDescription = "Radar",
            tint = if (isScanning) Color(0xFF10B981) else Color(0xFF64748B),
            modifier = Modifier
                .size(36.dp)
                .rotate(if (isScanning) angle else 0f)
        )
    }
}

@Composable
fun SubnetScannerDialog(
    initialBaseIp: String = "",
    onDismiss: () -> Unit,
    onDeviceSelected: (DiscoveredDevice) -> Unit
) {
    val context = LocalContext.current
    val detectedIp = remember { initialBaseIp.ifBlank { CameraNetworkScanner.getLocalWifiIpAddress(context) } }
    var baseIpInput by remember { mutableStateOf(detectedIp) }
    var isScanning by remember { mutableStateOf(false) }
    var progressCurrent by remember { mutableIntStateOf(0) }
    var progressTotal by remember { mutableIntStateOf(254) }
    var discoveredDevices by remember { mutableStateOf(listOf<DiscoveredDevice>()) }
    var scanJob by remember { mutableStateOf<Job?>(null) }
    val coroutineScope = rememberCoroutineScope()

    Dialog(onDismissRequest = {
        scanJob?.cancel()
        onDismiss()
    }) {
        Card(
            modifier = Modifier
                .fillMaxWidth(0.95f)
                .fillMaxHeight(0.85f),
            colors = CardDefaults.cardColors(containerColor = Color(0xFF0F172A)),
            shape = RoundedCornerShape(16.dp)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(16.dp)
            ) {
                // Header
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text(
                            text = "TARGETED SUBNET SCANNER",
                            color = Color.White,
                            fontWeight = FontWeight.Bold,
                            fontSize = 15.sp
                        )
                        Text(
                            text = "Sweeps /24 IP subnet for CCTV ports (554, 8000, 80)",
                            color = Color(0xFF94A3B8),
                            fontSize = 11.sp
                        )
                    }
                    IconButton(onClick = {
                        scanJob?.cancel()
                        onDismiss()
                    }) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = Color.White)
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Input Bar & Action
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedTextField(
                        value = baseIpInput,
                        onValueChange = { baseIpInput = it },
                        label = { Text("Base Subnet IP", color = Color(0xFF94A3B8)) },
                        singleLine = true,
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = Color(0xFF10B981),
                            unfocusedBorderColor = Color(0xFF334155),
                            focusedTextColor = Color.White,
                            unfocusedTextColor = Color.White
                        ),
                        modifier = Modifier.weight(1f)
                    )

                    if (!isScanning) {
                        Button(
                            onClick = {
                                isScanning = true
                                progressCurrent = 0
                                discoveredDevices = emptyList()
                                scanJob = coroutineScope.launch {
                                    val results = CameraNetworkScanner.sweepSubnetRange(baseIpInput) { cur, tot ->
                                        progressCurrent = cur
                                        progressTotal = tot
                                    }
                                    discoveredDevices = results
                                    isScanning = false
                                }
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF10B981)),
                            shape = RoundedCornerShape(10.dp)
                        ) {
                            Icon(Icons.Default.Search, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Scan Range", fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        }
                    } else {
                        Button(
                            onClick = {
                                scanJob?.cancel()
                                isScanning = false
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFEF4444)),
                            shape = RoundedCornerShape(10.dp)
                        ) {
                            Icon(Icons.Default.Stop, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Stop Scan", fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Radar & Progress State
                if (isScanning) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(containerColor = Color(0xFF1E293B)),
                        shape = RoundedCornerShape(10.dp)
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            RadarAnimation(isScanning = true)
                            Spacer(modifier = Modifier.width(12.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    text = "Sweeping Subnet Range...",
                                    color = Color.White,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 12.sp
                                )
                                Text(
                                    text = "IP $progressCurrent / $progressTotal tested",
                                    color = Color(0xFF38BDF8),
                                    fontSize = 11.sp
                                )
                                Spacer(modifier = Modifier.height(6.dp))
                                LinearProgressIndicator(
                                    progress = { if (progressTotal > 0) progressCurrent.toFloat() / progressTotal else 0f },
                                    modifier = Modifier.fillMaxWidth(),
                                    color = Color(0xFF10B981),
                                    trackColor = Color(0xFF334155)
                                )
                            }
                        }
                    }
                    Spacer(modifier = Modifier.height(12.dp))
                }

                // Results Count Header
                Text(
                    text = "DISCOVERED CCTV DEVICES (${discoveredDevices.size})",
                    color = Color(0xFF10B981),
                    fontWeight = FontWeight.Bold,
                    fontSize = 11.sp
                )

                Spacer(modifier = Modifier.height(6.dp))

                if (discoveredDevices.isEmpty() && !isScanning) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .weight(1f),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = "No cameras or NVRs found on this IP range. Tap 'Scan Range' to search.",
                            color = Color(0xFF64748B),
                            fontSize = 12.sp
                        )
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier.weight(1f),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        items(discoveredDevices) { dev ->
                            Card(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable {
                                        onDeviceSelected(dev)
                                        onDismiss()
                                    },
                                colors = CardDefaults.cardColors(containerColor = Color(0xFF1E293B)),
                                shape = RoundedCornerShape(8.dp)
                            ) {
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(12.dp),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Column {
                                        Row(verticalAlignment = Alignment.CenterVertically) {
                                            Icon(Icons.Default.Videocam, contentDescription = null, tint = Color(0xFF10B981), modifier = Modifier.size(16.dp))
                                            Spacer(modifier = Modifier.width(6.dp))
                                            Text(dev.ip, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                                            Spacer(modifier = Modifier.width(6.dp))
                                            Surface(
                                                color = Color(0xFF3B82F6).copy(alpha = 0.2f),
                                                shape = RoundedCornerShape(4.dp)
                                            ) {
                                                Text(
                                                    text = "Port ${dev.primaryPort}",
                                                    color = Color(0xFF60A5FA),
                                                    fontSize = 9.sp,
                                                    fontWeight = FontWeight.Bold,
                                                    modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                                                )
                                            }
                                        }
                                        Spacer(modifier = Modifier.height(4.dp))
                                        Text(
                                            text = "${dev.brand} • Open Ports: ${dev.openPorts.joinToString()}",
                                            color = Color(0xFF94A3B8),
                                            fontSize = 10.sp
                                        )
                                    }

                                    Button(
                                        onClick = {
                                            onDeviceSelected(dev)
                                            onDismiss()
                                        },
                                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF3B82F6)),
                                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                                        shape = RoundedCornerShape(6.dp)
                                    ) {
                                        Text("Use IP", fontSize = 10.sp, fontWeight = FontWeight.Bold)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun WifiAutoScanDialog(
    onDismiss: () -> Unit,
    onDeviceSelected: (DiscoveredDevice) -> Unit
) {
    val context = LocalContext.current
    var isScanning by remember { mutableStateOf(true) }
    var statusText by remember { mutableStateOf("Initializing ONVIF Multicast Discovery...") }
    var discoveredDevices by remember { mutableStateOf(listOf<DiscoveredDevice>()) }
    var scanJob by remember { mutableStateOf<Job?>(null) }
    val coroutineScope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        scanJob = coroutineScope.launch {
            val results = CameraNetworkScanner.scanWifiOnvifMulticast(context) { progress ->
                statusText = progress
            }
            discoveredDevices = results
            isScanning = false
        }
    }

    Dialog(onDismissRequest = {
        scanJob?.cancel()
        onDismiss()
    }) {
        Card(
            modifier = Modifier
                .fillMaxWidth(0.95f)
                .fillMaxHeight(0.85f),
            colors = CardDefaults.cardColors(containerColor = Color(0xFF0F172A)),
            shape = RoundedCornerShape(16.dp)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(16.dp)
            ) {
                // Header
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text(
                            text = "WI-FI SMART AUTO-DISCOVERY",
                            color = Color.White,
                            fontWeight = FontWeight.Bold,
                            fontSize = 15.sp
                        )
                        Text(
                            text = "WS-Discovery ONVIF Broadcast & RTSP Auth Validation",
                            color = Color(0xFF94A3B8),
                            fontSize = 11.sp
                        )
                    }
                    IconButton(onClick = {
                        scanJob?.cancel()
                        onDismiss()
                    }) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = Color.White)
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Radar & Status Card
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF1E293B)),
                    shape = RoundedCornerShape(10.dp)
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        RadarAnimation(isScanning = isScanning)
                        Spacer(modifier = Modifier.width(12.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = if (isScanning) "Scanning Connected Wi-Fi Network..." else "Wi-Fi Scan Complete",
                                color = Color.White,
                                fontWeight = FontWeight.Bold,
                                fontSize = 12.sp
                            )
                            Text(
                                text = statusText,
                                color = Color(0xFF38BDF8),
                                fontSize = 10.sp
                            )
                        }

                        if (isScanning) {
                            Button(
                                onClick = {
                                    scanJob?.cancel()
                                    isScanning = false
                                },
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFEF4444)),
                                contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp),
                                shape = RoundedCornerShape(6.dp)
                            ) {
                                Text("Stop", fontSize = 10.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))

                // Categorized Results List
                val publicDevices = remember(discoveredDevices) { discoveredDevices.filter { it.authStatus == DeviceAuthStatus.PUBLIC } }
                val restrictedDevices = remember(discoveredDevices) { discoveredDevices.filter { it.authStatus != DeviceAuthStatus.PUBLIC } }

                LazyColumn(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    if (publicDevices.isNotEmpty()) {
                        item {
                            Text(
                                text = "🔓 UNSECURED / PUBLIC FEEDS (${publicDevices.size})",
                                color = Color(0xFFF59E0B),
                                fontWeight = FontWeight.Bold,
                                fontSize = 11.sp
                            )
                        }
                        items(publicDevices) { dev ->
                            DiscoveredDeviceCard(dev = dev, onSelect = {
                                onDeviceSelected(dev)
                                onDismiss()
                            })
                        }
                    }

                    if (restrictedDevices.isNotEmpty()) {
                        item {
                            Text(
                                text = "🔒 SECURED / NETWORK RESTRICTED (${restrictedDevices.size})",
                                color = Color(0xFF10B981),
                                fontWeight = FontWeight.Bold,
                                fontSize = 11.sp
                            )
                        }
                        items(restrictedDevices) { dev ->
                            DiscoveredDeviceCard(dev = dev, onSelect = {
                                onDeviceSelected(dev)
                                onDismiss()
                            })
                        }
                    }

                    if (discoveredDevices.isEmpty() && !isScanning) {
                        item {
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(120.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(
                                    text = "No Wi-Fi CCTV devices responded to multicast probe.",
                                    color = Color(0xFF64748B),
                                    fontSize = 12.sp
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun DiscoveredDeviceCard(
    dev: DiscoveredDevice,
    onSelect: () -> Unit
) {
    val isPublic = dev.authStatus == DeviceAuthStatus.PUBLIC

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onSelect() },
        colors = CardDefaults.cardColors(containerColor = Color(0xFF1E293B)),
        shape = RoundedCornerShape(8.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = if (isPublic) Icons.Default.LockOpen else Icons.Default.Lock,
                        contentDescription = null,
                        tint = if (isPublic) Color(0xFFF59E0B) else Color(0xFF10B981),
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(dev.ip, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                    Spacer(modifier = Modifier.width(6.dp))
                    Surface(
                        color = if (isPublic) Color(0xFFF59E0B).copy(alpha = 0.2f) else Color(0xFF10B981).copy(alpha = 0.2f),
                        shape = RoundedCornerShape(4.dp)
                    ) {
                        Text(
                            text = if (isPublic) "🔓 PUBLIC / UNSECURED" else "🔒 RESTRICTED",
                            color = if (isPublic) Color(0xFFFBBF24) else Color(0xFF34D399),
                            fontSize = 8.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                        )
                    }
                }
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "${dev.brand} • Port ${dev.primaryPort}",
                    color = Color(0xFF94A3B8),
                    fontSize = 10.sp
                )
            }

            Button(
                onClick = onSelect,
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (isPublic) Color(0xFFF59E0B) else Color(0xFF10B981)
                ),
                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                shape = RoundedCornerShape(6.dp)
            ) {
                Text("Add", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color.Black)
            }
        }
    }
}
