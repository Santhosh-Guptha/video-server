package com.example.godownvision.ui

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.Verified
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.godownvision.data.BookmarkIncident
import com.example.godownvision.data.CameraEntity

@Composable
fun BookmarksTabScreen(
    bookmarks: List<BookmarkIncident>,
    cameraList: List<CameraEntity>,
    onJumpToPlayback: (CameraEntity, String) -> Unit,
    onUpdateBookmarkStatus: (String, String) -> Unit,
    onDeleteBookmark: (String) -> Unit
) {
    val context = LocalContext.current

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(8.dp)
    ) {
        // Header Banner
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(Color(0xFF0F172A), RoundedCornerShape(12.dp))
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Default.Bookmark,
                    contentDescription = null,
                    tint = Color(0xFFF59E0B),
                    modifier = Modifier.size(20.dp)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "Incident Bookmarks & Markers",
                    color = Color.White,
                    fontWeight = FontWeight.Bold,
                    fontSize = 15.sp
                )
            }
            Surface(
                color = Color(0xFFF59E0B).copy(alpha = 0.2f),
                shape = RoundedCornerShape(12.dp)
            ) {
                Text(
                    text = "${bookmarks.size} SAVED",
                    color = Color(0xFFF59E0B),
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                )
            }
        }

        Spacer(modifier = Modifier.height(10.dp))

        if (bookmarks.isEmpty()) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .weight(1f),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(
                        imageVector = Icons.Default.Bookmark,
                        contentDescription = null,
                        tint = Color(0xFF475569),
                        modifier = Modifier.size(48.dp)
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "No Incident Bookmarks Saved",
                        color = Color(0xFF94A3B8),
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Tap the Bookmark icon during live or playback view to save an incident.",
                        color = Color(0xFF64748B),
                        fontSize = 11.sp
                    )
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(bookmarks.sortedByDescending { it.createdAt }) { bookmark ->
                    val matchedCam = cameraList.find { it.id == bookmark.cameraId }
                    val isOfflineIncident = bookmark.type == "CAMERA_OFFLINE_INCIDENT"
                    val isReviewed = bookmark.status == "REVIEWED"

                    Card(
                        colors = CardDefaults.cardColors(containerColor = Color(0xFF1E293B)),
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(modifier = Modifier.padding(12.dp)) {
                            // Top Badges Row: Type & Status
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                // Incident Type Pill
                                Surface(
                                    color = if (isOfflineIncident) Color(0xFFEF4444).copy(alpha = 0.2f) else Color(0xFFF59E0B).copy(alpha = 0.2f),
                                    shape = RoundedCornerShape(6.dp)
                                ) {
                                    Row(
                                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Icon(
                                            imageVector = if (isOfflineIncident) Icons.Default.Warning else Icons.Default.Bookmark,
                                            contentDescription = null,
                                            tint = if (isOfflineIncident) Color(0xFFEF4444) else Color(0xFFF59E0B),
                                            modifier = Modifier.size(12.dp)
                                        )
                                        Spacer(modifier = Modifier.width(4.dp))
                                        Text(
                                            text = if (isOfflineIncident) "🚨 OFFLINE INCIDENT" else "📌 MANUAL BOOKMARK",
                                            color = if (isOfflineIncident) Color(0xFFEF4444) else Color(0xFFF59E0B),
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 9.sp
                                        )
                                    }
                                }

                                // Status Pill
                                Surface(
                                    color = if (isReviewed) Color(0xFF10B981).copy(alpha = 0.2f) else Color(0xFFF59E0B).copy(alpha = 0.2f),
                                    shape = RoundedCornerShape(6.dp)
                                ) {
                                    Row(
                                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Icon(
                                            imageVector = if (isReviewed) Icons.Default.CheckCircle else Icons.Default.Warning,
                                            contentDescription = null,
                                            tint = if (isReviewed) Color(0xFF10B981) else Color(0xFFF59E0B),
                                            modifier = Modifier.size(12.dp)
                                        )
                                        Spacer(modifier = Modifier.width(4.dp))
                                        Text(
                                            text = if (isReviewed) "✓ REVIEWED & VERIFIED" else "⚠️ UNREVIEWED",
                                            color = if (isReviewed) Color(0xFF10B981) else Color(0xFFF59E0B),
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 9.sp
                                        )
                                    }
                                }
                            }

                            Spacer(modifier = Modifier.height(8.dp))

                            // Camera Name & Timestamp
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(
                                        imageVector = Icons.Default.Videocam,
                                        contentDescription = null,
                                        tint = Color(0xFF38BDF8),
                                        modifier = Modifier.size(16.dp)
                                    )
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Text(
                                        text = bookmark.cameraName,
                                        color = Color.White,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 13.sp
                                    )
                                }

                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(
                                        imageVector = Icons.Default.Schedule,
                                        contentDescription = null,
                                        tint = Color(0xFF10B981),
                                        modifier = Modifier.size(14.dp)
                                    )
                                    Spacer(modifier = Modifier.width(4.dp))
                                    Text(
                                        text = bookmark.timestamp,
                                        color = Color(0xFF10B981),
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 11.sp
                                    )
                                }
                            }

                            Spacer(modifier = Modifier.height(8.dp))

                            // Incident Note / Description
                            Surface(
                                color = Color(0xFF0F172A),
                                shape = RoundedCornerShape(8.dp),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Text(
                                    text = bookmark.note,
                                    color = Color(0xFFE2E8F0),
                                    fontSize = 12.sp,
                                    modifier = Modifier.padding(10.dp)
                                )
                            }

                            Spacer(modifier = Modifier.height(10.dp))

                            // Bottom Row: Created By & Action Buttons
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "Saved by ${bookmark.createdBy}",
                                    color = Color(0xFF64748B),
                                    fontSize = 10.sp
                                )

                                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    // Mark as Reviewed Button (if unreviewed)
                                    if (!isReviewed) {
                                        IconButton(
                                            onClick = {
                                                onUpdateBookmarkStatus(bookmark.id, "REVIEWED")
                                                Toast.makeText(context, "Incident marked as Reviewed & Verified", Toast.LENGTH_SHORT).show()
                                            },
                                            modifier = Modifier.size(32.dp)
                                        ) {
                                            Icon(
                                                imageVector = Icons.Default.Verified,
                                                contentDescription = "Mark as Reviewed",
                                                tint = Color(0xFF38BDF8),
                                                modifier = Modifier.size(20.dp)
                                            )
                                        }
                                    }

                                    // Delete Bookmark Button (Protected: Allowed ONLY if REVIEWED)
                                    IconButton(
                                        onClick = {
                                            if (!isReviewed) {
                                                Toast.makeText(
                                                    context,
                                                    "Unreviewed events cannot be deleted. Mark as reviewed first.",
                                                    Toast.LENGTH_LONG
                                                ).show()
                                            } else {
                                                onDeleteBookmark(bookmark.id)
                                            }
                                        },
                                        modifier = Modifier.size(32.dp)
                                    ) {
                                        Icon(
                                            imageVector = Icons.Default.Delete,
                                            contentDescription = "Delete",
                                            tint = if (isReviewed) Color(0xFFEF4444) else Color(0xFF475569),
                                            modifier = Modifier.size(18.dp)
                                        )
                                    }

                                    // Jump to Playback Button
                                    Button(
                                        onClick = {
                                            val camToUse = matchedCam ?: CameraEntity(
                                                id = bookmark.cameraId,
                                                name = bookmark.cameraName,
                                                location = "Warehouse",
                                                localIp = "192.168.1.100",
                                                remoteHost = "",
                                                rtspPort = 554,
                                                httpPort = 80,
                                                username = "admin",
                                                password = "",
                                                channel = 1,
                                                nvrBrand = "HIKVISION",
                                                streamQuality = "MAIN"
                                            )
                                            onJumpToPlayback(camToUse, bookmark.timestamp)
                                        },
                                        colors = ButtonDefaults.buttonColors(
                                            containerColor = Color(0xFF10B981),
                                            contentColor = Color.White
                                        ),
                                        shape = RoundedCornerShape(8.dp),
                                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                                        modifier = Modifier.height(32.dp)
                                    ) {
                                        Icon(
                                            imageVector = Icons.Default.PlayArrow,
                                            contentDescription = null,
                                            modifier = Modifier.size(16.dp)
                                        )
                                        Spacer(modifier = Modifier.width(4.dp))
                                        Text(
                                            text = "Jump to Playback",
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 11.sp
                                        )
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
