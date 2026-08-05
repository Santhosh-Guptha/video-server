package com.example.godownvision.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.PersonAdd
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.example.godownvision.data.CameraEntity
import com.example.godownvision.data.UserFeatures
import com.example.godownvision.data.UserProfile
import com.example.godownvision.security.VaultCryptoEngine
import java.util.UUID

@Composable
fun UserManagementPanel(
    usersList: List<UserProfile>,
    cameraList: List<CameraEntity>,
    onSaveUser: (UserProfile) -> Unit,
    onDeleteUser: (String) -> Unit
) {
    var showCreateDialog by remember { mutableStateOf(false) }
    var editingUser by remember { mutableStateOf<UserProfile?>(null) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(12.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text(
                    text = "USER MANAGEMENT PANEL",
                    color = Color.White,
                    fontWeight = FontWeight.Bold,
                    fontSize = 15.sp
                )
                Text(
                    text = "Manage operator profiles & granular feature permissions",
                    color = Color(0xFF94A3B8),
                    fontSize = 11.sp
                )
            }

            Button(
                onClick = {
                    editingUser = null
                    showCreateDialog = true
                },
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF10B981)),
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp),
                shape = RoundedCornerShape(10.dp)
            ) {
                Icon(Icons.Default.PersonAdd, contentDescription = "Create User", modifier = Modifier.size(16.dp))
                Spacer(modifier = Modifier.width(4.dp))
                Text("+ New User", fontSize = 11.sp, fontWeight = FontWeight.Bold)
            }
        }

        Spacer(modifier = Modifier.height(14.dp))

        if (usersList.isEmpty()) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .weight(1f),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = "No custom users created. Tap '+ New User' to add operators.",
                    color = Color(0xFF64748B),
                    fontSize = 12.sp
                )
            }
        } else {
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.weight(1f)
            ) {
                items(usersList) { user ->
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(containerColor = Color(0xFF1E293B)),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Column(modifier = Modifier.padding(14.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(
                                        text = user.username,
                                        color = Color.White,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 15.sp
                                    )
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Surface(
                                        color = if (user.canConfigureCameras) Color(0xFF3B82F6).copy(alpha = 0.2f) else Color(0xFF64748B).copy(alpha = 0.2f),
                                        shape = RoundedCornerShape(6.dp)
                                    ) {
                                        Text(
                                            text = if (user.canConfigureCameras) "Admin/Config" else "Operator",
                                            color = if (user.canConfigureCameras) Color(0xFF60A5FA) else Color(0xFF94A3B8),
                                            fontSize = 10.sp,
                                            fontWeight = FontWeight.Bold,
                                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                                        )
                                    }
                                }

                                Row {
                                    IconButton(
                                        onClick = {
                                            editingUser = user
                                            showCreateDialog = true
                                        },
                                        modifier = Modifier.size(32.dp)
                                    ) {
                                        Icon(Icons.Default.Edit, contentDescription = "Edit", tint = Color(0xFF38BDF8), modifier = Modifier.size(16.dp))
                                    }

                                    IconButton(
                                        onClick = { onDeleteUser(user.userId) },
                                        modifier = Modifier.size(32.dp)
                                    ) {
                                        Icon(Icons.Default.Delete, contentDescription = "Delete", tint = Color(0xFFEF4444), modifier = Modifier.size(16.dp))
                                    }
                                }
                            }

                            Spacer(modifier = Modifier.height(6.dp))

                            // Features Badges
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(4.dp),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                FeatureBadge(label = "Live", active = user.features.liveView)
                                FeatureBadge(label = "Playback", active = user.features.playback)
                                FeatureBadge(label = "HD", active = user.features.hdStream)
                                FeatureBadge(label = "Snapshot", active = user.features.snapshotCapture)
                                FeatureBadge(label = "Clip Export", active = user.features.clipDownload)
                                FeatureBadge(label = "Multi-Sync", active = user.features.multiSyncPlayback)
                            }

                            Spacer(modifier = Modifier.height(6.dp))

                            Text(
                                text = "Assigned Feeds: ${user.assignedCameraIds.size} of ${cameraList.size} Cameras",
                                color = Color(0xFF94A3B8),
                                fontSize = 11.sp
                            )
                        }
                    }
                }
            }
        }
    }

    if (showCreateDialog) {
        UserConfigModal(
            existingUser = editingUser,
            allCameras = cameraList,
            onDismiss = { showCreateDialog = false },
            onSave = { updatedUser ->
                onSaveUser(updatedUser)
                showCreateDialog = false
            }
        )
    }
}

@Composable
private fun FeatureBadge(label: String, active: Boolean) {
    Surface(
        color = if (active) Color(0xFF10B981).copy(alpha = 0.15f) else Color(0xFFEF4444).copy(alpha = 0.15f),
        shape = RoundedCornerShape(4.dp)
    ) {
        Text(
            text = "${if (active) "✓" else "✕"} $label",
            color = if (active) Color(0xFF34D399) else Color(0xFFF87171),
            fontSize = 9.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(horizontal = 5.dp, vertical = 2.dp)
        )
    }
}

@Composable
fun UserConfigModal(
    existingUser: UserProfile?,
    allCameras: List<CameraEntity>,
    onDismiss: () -> Unit,
    onSave: (UserProfile) -> Unit
) {
    var username by remember { mutableStateOf(existingUser?.username ?: "") }
    var rawPassword by remember { mutableStateOf("") }
    var canConfigureCameras by remember { mutableStateOf(existingUser?.canConfigureCameras ?: false) }

    var featLiveView by remember { mutableStateOf(existingUser?.features?.liveView ?: true) }
    var featPlayback by remember { mutableStateOf(existingUser?.features?.playback ?: true) }
    var featHdStream by remember { mutableStateOf(existingUser?.features?.hdStream ?: true) }
    var featSnapshot by remember { mutableStateOf(existingUser?.features?.snapshotCapture ?: true) }
    var featClipDownload by remember { mutableStateOf(existingUser?.features?.clipDownload ?: false) }
    var featMultiSync by remember { mutableStateOf(existingUser?.features?.multiSyncPlayback ?: true) }

    val existingQ1 = existingUser?.securityQuestions?.getOrNull(0)?.question ?: "First Pet's Name?"
    val existingQ2 = existingUser?.securityQuestions?.getOrNull(1)?.question ?: "City of Birth?"

    var question1 by remember { mutableStateOf(existingQ1) }
    var answer1 by remember { mutableStateOf("") }
    var question2 by remember { mutableStateOf(existingQ2) }
    var answer2 by remember { mutableStateOf("") }

    val selectedCamIds = remember { mutableStateListOf<Long>().apply { addAll(existingUser?.assignedCameraIds ?: allCameras.map { it.id }) } }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    Dialog(onDismissRequest = onDismiss) {
        Card(
            modifier = Modifier
                .fillMaxWidth(0.95f)
                .fillMaxHeight(0.88f),
            colors = CardDefaults.cardColors(containerColor = Color(0xFF0F172A)),
            shape = RoundedCornerShape(16.dp)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(16.dp)
            ) {
                Text(
                    text = if (existingUser == null) "CREATE USER & PERMISSIONS" else "EDIT USER PERMISSIONS",
                    color = Color.White,
                    fontWeight = FontWeight.Bold,
                    fontSize = 15.sp
                )

                Spacer(modifier = Modifier.height(12.dp))

                Column(
                    modifier = Modifier
                        .weight(1f)
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    OutlinedTextField(
                        value = username,
                        onValueChange = { username = it; errorMessage = null },
                        label = { Text("Username", color = Color(0xFF94A3B8)) },
                        singleLine = true,
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = Color.White,
                            unfocusedBorderColor = Color(0xFF334155),
                            focusedTextColor = Color.White,
                            unfocusedTextColor = Color.White
                        ),
                        modifier = Modifier.fillMaxWidth()
                    )

                    OutlinedTextField(
                        value = rawPassword,
                        onValueChange = { rawPassword = it; errorMessage = null },
                        label = { Text(if (existingUser == null) "Password *" else "New Password (Leave blank to keep)", color = Color(0xFF94A3B8)) },
                        visualTransformation = PasswordVisualTransformation(),
                        singleLine = true,
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = Color.White,
                            unfocusedBorderColor = Color(0xFF334155),
                            focusedTextColor = Color.White,
                            unfocusedTextColor = Color.White
                        ),
                        modifier = Modifier.fillMaxWidth()
                    )

                    HorizontalDivider(color = Color(0xFF1E293B))

                    Text("PERSONAL RECOVERY QUESTIONS", color = Color(0xFFA855F7), fontWeight = FontWeight.Bold, fontSize = 11.sp)

                    OutlinedTextField(
                        value = question1,
                        onValueChange = { question1 = it },
                        label = { Text("Security Question 1", color = Color(0xFF94A3B8)) },
                        singleLine = true,
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = Color.White,
                            unfocusedBorderColor = Color(0xFF334155),
                            focusedTextColor = Color.White,
                            unfocusedTextColor = Color.White
                        ),
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = answer1,
                        onValueChange = { answer1 = it },
                        label = { Text(if (existingUser == null) "Answer 1 *" else "Answer 1 (Leave blank to keep)", color = Color(0xFF94A3B8)) },
                        singleLine = true,
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = Color.White,
                            unfocusedBorderColor = Color(0xFF334155),
                            focusedTextColor = Color.White,
                            unfocusedTextColor = Color.White
                        ),
                        modifier = Modifier.fillMaxWidth()
                    )

                    OutlinedTextField(
                        value = question2,
                        onValueChange = { question2 = it },
                        label = { Text("Security Question 2", color = Color(0xFF94A3B8)) },
                        singleLine = true,
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = Color.White,
                            unfocusedBorderColor = Color(0xFF334155),
                            focusedTextColor = Color.White,
                            unfocusedTextColor = Color.White
                        ),
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = answer2,
                        onValueChange = { answer2 = it },
                        label = { Text(if (existingUser == null) "Answer 2 *" else "Answer 2 (Leave blank to keep)", color = Color(0xFF94A3B8)) },
                        singleLine = true,
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = Color.White,
                            unfocusedBorderColor = Color(0xFF334155),
                            focusedTextColor = Color.White,
                            unfocusedTextColor = Color.White
                        ),
                        modifier = Modifier.fillMaxWidth()
                    )

                    HorizontalDivider(color = Color(0xFF1E293B))

                    Text("ASSIGNED PERMISSIONS & FEATURE TOGGLES", color = Color(0xFF38BDF8), fontWeight = FontWeight.Bold, fontSize = 11.sp)

                    ToggleRow("Live Stream Access", featLiveView) { featLiveView = it }
                    ToggleRow("NVR Playback Screen", featPlayback) { featPlayback = it }
                    ToggleRow("HD Main-Stream Toggle", featHdStream) { featHdStream = it }
                    ToggleRow("Snapshot / Frame Capture", featSnapshot) { featSnapshot = it }
                    ToggleRow("5-Min Clip Download Feature", featClipDownload) { featClipDownload = it }
                    ToggleRow("Multi-Camera Synchronized Playback", featMultiSync) { featMultiSync = it }

                    HorizontalDivider(color = Color(0xFF1E293B))

                    Text("CAMERA CONFIGURATION PRIVILEGE", color = Color(0xFFF59E0B), fontWeight = FontWeight.Bold, fontSize = 11.sp)
                    ToggleRow("Allow User to Add / Edit / Delete Cameras", canConfigureCameras) { canConfigureCameras = it }

                    HorizontalDivider(color = Color(0xFF1E293B))

                    Text("ASSIGNED CAMERA FEEDS", color = Color(0xFF10B981), fontWeight = FontWeight.Bold, fontSize = 11.sp)
                    allCameras.forEach { cam ->
                        val isChecked = selectedCamIds.contains(cam.id)
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    if (isChecked) selectedCamIds.remove(cam.id) else selectedCamIds.add(cam.id)
                                }
                                .padding(vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Checkbox(
                                checked = isChecked,
                                onCheckedChange = { check ->
                                    if (check) selectedCamIds.add(cam.id) else selectedCamIds.remove(cam.id)
                                },
                                colors = CheckboxDefaults.colors(checkedColor = Color(0xFF10B981))
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Text("${cam.name} (Ch ${cam.channel})", color = Color.White, fontSize = 12.sp)
                        }
                    }
                }

                if (errorMessage != null) {
                    Text(errorMessage!!, color = Color(0xFFEF4444), fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    Spacer(modifier = Modifier.height(6.dp))
                }

                Spacer(modifier = Modifier.height(10.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Button(
                        onClick = onDismiss,
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF334155)),
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("Cancel", color = Color.White)
                    }

                    Button(
                        onClick = {
                            if (username.isBlank()) {
                                errorMessage = "Username cannot be empty"
                            } else if (existingUser == null && rawPassword.isBlank()) {
                                errorMessage = "Password is required for new user"
                            } else {
                                val passwordHashToUse = if (rawPassword.isNotBlank()) {
                                    VaultCryptoEngine.hashPassword(rawPassword)
                                } else {
                                    existingUser?.passwordHash ?: ""
                                }

                                val qList = mutableListOf<com.example.godownvision.data.SecurityQuestion>()
                                if (answer1.isNotBlank()) {
                                    qList.add(com.example.godownvision.data.SecurityQuestion(question1, VaultCryptoEngine.hashPassword(answer1.trim().lowercase())))
                                } else {
                                    existingUser?.securityQuestions?.getOrNull(0)?.let { qList.add(it) }
                                }
                                if (answer2.isNotBlank()) {
                                    qList.add(com.example.godownvision.data.SecurityQuestion(question2, VaultCryptoEngine.hashPassword(answer2.trim().lowercase())))
                                } else {
                                    existingUser?.securityQuestions?.getOrNull(1)?.let { qList.add(it) }
                                }

                                val newUser = UserProfile(
                                    userId = existingUser?.userId ?: "usr_${UUID.randomUUID().toString().take(8)}",
                                    username = username.trim(),
                                    passwordHash = passwordHashToUse,
                                    canConfigureCameras = canConfigureCameras,
                                    features = UserFeatures(
                                        liveView = featLiveView,
                                        playback = featPlayback,
                                        hdStream = featHdStream,
                                        snapshotCapture = featSnapshot,
                                        clipDownload = featClipDownload,
                                        multiSyncPlayback = featMultiSync
                                    ),
                                    assignedCameraIds = selectedCamIds.toList(),
                                    securityQuestions = qList
                                )
                                onSave(newUser)
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF10B981)),
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("Save Permissions", color = Color.White, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

@Composable
private fun ToggleRow(label: String, value: Boolean, onValueChange: (Boolean) -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(label, color = Color.White, fontSize = 12.sp)
        Switch(
            checked = value,
            onCheckedChange = onValueChange,
            colors = SwitchDefaults.colors(checkedThumbColor = Color.White, checkedTrackColor = Color(0xFF10B981))
        )
    }
}
