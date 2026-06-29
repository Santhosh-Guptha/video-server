from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import time

from workers.ffmpeg_worker import TranscodingWorkerPool
from scheduler.gpu_scheduler import GPUScheduler

router = APIRouter()

# Simple shared API key secret for authentication
API_KEY_SECRET = "vms_secure_secret_key"

# Dependency to enforce Bearer token authentication and tenant header tracking
async def verify_auth(
    authorization: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None),
    x_node_id: Optional[str] = Header(None)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Expected Bearer token."
        )
    
    token = authorization.replace("Bearer ", "").strip()
    # Validate the VMS secret key token
    if token != f"VMS-{API_KEY_SECRET}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: invalid API key token."
        )
        
    if not x_tenant_id or not x_node_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required tenant headers: X-Tenant-ID and X-Node-ID."
        )
    return {"tenant_id": x_tenant_id, "node_id": x_node_id}


# Request Schemas
class StartTranscodeRequest(BaseModel):
    stream_id: str
    session_id: str
    source_url: str
    target_url: str
    session_type: Optional[str] = "live"

class StopTranscodeRequest(BaseModel):
    stream_id: str
    session_id: str
    session_type: Optional[str] = "live"

class ActiveSessionItem(BaseModel):
    session_id: str
    stream_id: str

class HeartbeatRequest(BaseModel):
    sessions: List[ActiveSessionItem]

class RegisterNodeRequest(BaseModel):
    node_id: str
    tenant_id: str
    vms_version: str


# Endpoints
@router.post("/start", status_code=201)
async def start_transcoder(
    payload: StartTranscodeRequest,
    auth_data: dict = Depends(verify_auth)
):
    """Starts a shared transcoding process for a stream."""
    success = await TranscodingWorkerPool.start_transcoder(
        stream_id=payload.stream_id,
        session_id=payload.session_id,
        source_url=payload.source_url,
        target_url=payload.target_url,
        session_type=payload.session_type,
        node_id=auth_data.get("node_id", "default")
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to spawn transcoding FFmpeg process.")
    return {"status": "started", "stream_id": payload.stream_id, "route": payload.session_type}


@router.delete("/stop")
async def stop_transcoder(
    payload: StopTranscodeRequest,
    auth_data: dict = Depends(verify_auth)
):
    """Disconnects a viewer from a transcoding session, scheduling idle cleanup if count reaches 0."""
    success = await TranscodingWorkerPool.stop_transcoder(
        stream_id=payload.stream_id,
        session_id=payload.session_id,
        session_type=payload.session_type,
        node_id=auth_data.get("node_id", "default")
    )
    if not success:
        raise HTTPException(status_code=404, detail="Active transcoder session not found in pools.")
    return {"status": "deregistered"}


@router.post("/heartbeat")
async def process_heartbeat(
    payload: HeartbeatRequest,
    auth_data: dict = Depends(verify_auth)
):
    """Keeps cloud sessions alive. Returns status ok."""
    # Transcoding client sends this periodically for active sessions
    return {"status": "ok", "sessions_processed": len(payload.sessions)}


@router.post("/register")
async def register_node(
    payload: RegisterNodeRequest,
    auth_data: dict = Depends(verify_auth)
):
    """Registers a VMS node with the central platform."""
    print(f"[api] Registered node {payload.node_id} for tenant {payload.tenant_id} (VMS: {payload.vms_version})")
    return {"status": "registered", "node_id": payload.node_id}


@router.get("/status")
async def get_status(auth_data: dict = Depends(verify_auth)):
    """Returns the statuses of active pools and scheduler sessions."""
    worker_status = await TranscodingWorkerPool.get_worker_status()
    gpu_status = await GPUScheduler.get_cluster_status()
    return {
        "timestamp": time.time(),
        "workers": worker_status,
        "gpus": gpu_status
    }


@router.get("/health")
async def get_health():
    """Liveness check for load balancer and customer VMS client pings."""
    # Non-authenticated endpoint for fast liveness checks
    return {"status": "healthy", "service": "transcoding-server", "timestamp": time.time()}


from fastapi.responses import HTMLResponse

@router.get("/workers")
async def get_workers(auth_data: dict = Depends(verify_auth)):
    """Exposes statistics on worker process pools."""
    return await TranscodingWorkerPool.get_worker_status()


@router.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Serves the standalone VMS Transcoder Node Monitor dashboard."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>VMS Transcoder Node Monitor</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
        <style>
            body {
                font-family: 'Plus Jakarta Sans', sans-serif;
                background-color: #030712;
            }
            code, pre {
                font-family: 'JetBrains Mono', monospace;
            }
            .glass-card {
                background: rgba(15, 23, 42, 0.45);
                backdrop-filter: blur(12px);
                border: 1px solid rgba(255, 255, 255, 0.05);
            }
        </style>
    </head>
    <body class="text-slate-100 min-h-screen pb-12">
        <!-- Header -->
        <header class="border-b border-slate-900 bg-slate-950/80 backdrop-blur-md sticky top-0 z-40">
            <div class="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
                <div class="flex items-center gap-3">
                    <div class="h-9 w-9 rounded-xl bg-purple-600/10 border border-purple-500/20 flex items-center justify-center text-purple-400 font-extrabold text-sm">TR</div>
                    <div>
                        <h1 class="text-base font-bold tracking-tight">VMS Transcoder Monitor</h1>
                        <p class="text-xs text-slate-500">Standalone Node Management Console</p>
                    </div>
                </div>
                <div class="flex items-center gap-4">
                    <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-semibold">
                        <span class="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
                        Live Node Healthy
                    </div>
                    <button onclick="logout()" class="text-xs text-slate-500 hover:text-slate-300 font-medium">Reset Credentials</button>
                </div>
            </div>
        </header>

        <main class="max-w-7xl mx-auto px-6 mt-8 flex flex-col gap-8">
            <!-- Stats Grid -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <!-- KPI 1 -->
                <div class="glass-card rounded-2xl p-6 flex items-center gap-5">
                    <div class="p-3 bg-purple-500/10 border border-purple-500/20 rounded-xl text-purple-400">
                        <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
                    </div>
                    <div>
                        <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Live Streams</div>
                        <div id="live-count" class="text-2xl font-extrabold mt-1">0</div>
                    </div>
                </div>
                <!-- KPI 2 -->
                <div class="glass-card rounded-2xl p-6 flex items-center gap-5">
                    <div class="p-3 bg-sky-500/10 border border-sky-500/20 rounded-xl text-sky-400">
                        <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 11-3-3V3m3 0V3h-3m3 0H8"/></svg>
                    </div>
                    <div>
                        <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Playback Streams</div>
                        <div id="playback-count" class="text-2xl font-extrabold mt-1">0</div>
                    </div>
                </div>
                <!-- KPI 3 -->
                <div class="glass-card rounded-2xl p-6 flex items-center gap-5">
                    <div class="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-400">
                        <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                    </div>
                    <div>
                        <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Active Viewers</div>
                        <div id="viewer-count" class="text-2xl font-extrabold mt-1">0</div>
                    </div>
                </div>
            </div>

            <!-- Active Sessions Section -->
            <div class="glass-card rounded-3xl p-6 md:p-8 flex flex-col gap-6">
                <h3 class="text-lg font-bold tracking-tight">Active Transcoding Streams</h3>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse text-sm">
                        <thead>
                            <tr class="border-b border-slate-900 text-slate-500 text-xs font-bold uppercase tracking-wider">
                                <th class="pb-4 px-4">Stream / Session Key</th>
                                <th class="pb-4 px-4">Engine type</th>
                                <th class="pb-4 px-4">GPU allocation</th>
                                <th class="pb-4 px-4">Uptime</th>
                                <th class="pb-4 px-4">Viewers</th>
                            </tr>
                        </thead>
                        <tbody id="sessions-body" class="divide-y divide-slate-900/40">
                            <!-- Populated via Javascript -->
                        </tbody>
                    </table>
                </div>
                <div id="no-sessions" class="hidden text-center py-12 text-slate-600">
                    No streams are currently being transcoded. Sessions are spawned dynamically on-demand when user streams start.
                </div>
            </div>

            <!-- GPU Scheduler Section -->
            <div id="gpu-section" class="glass-card rounded-3xl p-6 md:p-8 hidden">
                <h3 class="text-lg font-bold tracking-tight mb-4">Hardware GPU Accelerators</h3>
                <div id="gpu-grid" class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <!-- Populated via Javascript -->
                </div>
            </div>
        </main>

        <!-- Credentials Dialog Modal -->
        <div id="auth-modal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-md hidden">
            <div class="glass-card max-w-md w-full p-8 rounded-3xl shadow-2xl flex flex-col gap-6 mx-4">
                <div>
                    <h3 class="text-xl font-bold tracking-tight">Unlock Dashboard</h3>
                    <p class="text-sm text-slate-500 mt-2">Enter the VMS API secret key configured on this transcoding node to view performance metrics.</p>
                </div>
                <div class="flex flex-col gap-2">
                    <label class="text-xs font-bold text-slate-400 uppercase">Secret API Key</label>
                    <input type="password" id="auth-key" placeholder="Enter key (e.g. vms_secure_secret_key)" class="w-full bg-slate-900/60 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-purple-500 text-slate-100 placeholder:text-slate-600 transition-all">
                    <p id="auth-error" class="text-xs text-rose-400 font-semibold mt-1 hidden">Invalid API key credentials.</p>
                </div>
                <button onclick="submitKey()" class="w-full py-3 bg-purple-600 hover:bg-purple-700 active:bg-purple-800 text-sm font-semibold rounded-xl text-white shadow-lg transition-all">Authenticate Console</button>
            </div>
        </div>

        <script>
            function getHeaders() {
                const key = localStorage.getItem('vms_key');
                return {
                    'Authorization': `Bearer VMS-${key}`,
                    'X-Tenant-ID': 'tenant_default',
                    'X-Node-ID': 'node_default'
                };
            }

            function logout() {
                localStorage.removeItem('vms_key');
                window.location.reload();
            }

            async function submitKey() {
                const keyInput = document.getElementById('auth-key').value;
                document.getElementById('auth-error').classList.add('hidden');
                
                try {
                    // Try to authenticate against /status using entered key
                    const res = await fetch('/status', {
                        headers: {
                            'Authorization': `Bearer VMS-${keyInput}`,
                            'X-Tenant-ID': 'tenant_default',
                            'X-Node-ID': 'node_default'
                        }
                    });
                    if (res.status === 200) {
                        localStorage.setItem('vms_key', keyInput);
                        document.getElementById('auth-modal').classList.add('hidden');
                        loadDashboard();
                        setInterval(loadDashboard, 3000);
                    } else {
                        document.getElementById('auth-error').classList.remove('hidden');
                    }
                } catch (e) {
                    document.getElementById('auth-error').innerText = "Connection failed: " + e.message;
                    document.getElementById('auth-error').classList.remove('hidden');
                }
            }

            function formatUptime(seconds) {
                const m = Math.floor(seconds / 60);
                const s = seconds % 60;
                return `${m}m ${s}s`;
            }

            async function loadDashboard() {
                const key = localStorage.getItem('vms_key');
                if (!key) {
                    document.getElementById('auth-modal').classList.remove('hidden');
                    return;
                }

                try {
                    const res = await fetch('/status', { headers: getHeaders() });
                    if (res.status === 401) {
                        logout();
                        return;
                    }
                    const data = await res.json();

                    // Update KPIs
                    const liveWorkerCount = data.workers?.live_worker_count || 0;
                    const playbackWorkerCount = data.workers?.playback_worker_count || 0;
                    document.getElementById('live-count').innerText = liveWorkerCount;
                    document.getElementById('playback-count').innerText = playbackWorkerCount;

                    // Compile active sessions list
                    const sessions = [];
                    let totalViewers = 0;
                    
                    if (data.workers?.live_active_sessions) {
                        data.workers.live_active_sessions.forEach(s => {
                            sessions.push({ ...s, type: 'live' });
                            totalViewers += s.viewers;
                        });
                    }
                    if (data.workers?.playback_active_sessions) {
                        data.workers.playback_active_sessions.forEach(s => {
                            sessions.push({ stream_id: s.session_key, gpu_index: s.gpu_index, viewers: s.viewers, uptime_s: s.uptime_s, type: 'playback' });
                            totalViewers += s.viewers;
                        });
                    }

                    document.getElementById('viewer-count').innerText = totalViewers;

                    // Populate sessions table
                    const tbody = document.getElementById('sessions-body');
                    tbody.innerHTML = '';
                    
                    if (sessions.length === 0) {
                        document.getElementById('no-sessions').classList.remove('hidden');
                    } else {
                        document.getElementById('no-sessions').classList.add('hidden');
                        sessions.forEach(s => {
                            const tr = document.createElement('tr');
                            tr.className = "border-b border-slate-900 bg-slate-950/20";
                            tr.innerHTML = `
                                <td class="py-4 px-4 font-semibold text-slate-200 font-mono">${s.stream_id}</td>
                                <td class="py-4 px-4">
                                    <span class="px-2 py-1 rounded-md text-xs font-semibold border ${s.type === 'live' ? 'bg-purple-500/10 border-purple-500/20 text-purple-400' : 'bg-sky-500/10 border-sky-500/20 text-sky-400'}">
                                        ${s.type.toUpperCase()}
                                    </span>
                                </td>
                                <td class="py-4 px-4 text-slate-300">
                                    ${s.gpu_index !== null ? `<span class="text-emerald-400 font-semibold">GPU Node (${s.gpu_index})</span>` : 'CPU Engine'}
                                </td>
                                <td class="py-4 px-4 text-slate-400 font-mono">${formatUptime(s.uptime_s)}</td>
                                <td class="py-4 px-4 text-purple-400 font-bold">${s.viewers} viewers</td>
                            `;
                            tbody.appendChild(tr);
                        });
                    }

                    // Populate GPU Scheduler Grid
                    const gpuSection = document.getElementById('gpu-section');
                    const gpuGrid = document.getElementById('gpu-grid');
                    gpuGrid.innerHTML = '';

                    if (data.gpus && data.gpus.length > 0) {
                        gpuSection.classList.remove('hidden');
                        data.gpus.forEach(g => {
                            const card = document.createElement('div');
                            card.className = "p-6 rounded-2xl bg-slate-950/30 border border-slate-900/80 flex flex-col gap-4";
                            card.innerHTML = `
                                <div class="flex justify-between items-center">
                                    <span class="text-sm font-bold text-slate-300">GPU ${g.index}: ${g.name}</span>
                                    <span class="text-xs text-slate-500">Free VRAM: ${Math.round(g.memory_free / 1024)} GB</span>
                                </div>
                                <div>
                                    <div class="flex justify-between text-xs text-slate-400 mb-2">
                                        <span>GPU Utilization</span>
                                        <strong>${g.utilization}%</strong>
                                    </div>
                                    <div class="h-6 w-full bg-slate-950 rounded-lg overflow-hidden border border-slate-900">
                                        <div class="h-full bg-gradient-to-r from-emerald-500 to-teal-500" style="width: ${g.utilization}%"></div>
                                    </div>
                                </div>
                            `;
                            gpuGrid.appendChild(card);
                        });
                    } else {
                        gpuSection.classList.add('hidden');
                    }

                } catch (e) {
                    console.error("Dashboard update failed:", e);
                }
            }

            // Initialize dashboard
            const savedKey = localStorage.getItem('vms_key');
            if (savedKey) {
                loadDashboard();
                setInterval(loadDashboard, 3000);
            } else {
                document.getElementById('auth-modal').classList.remove('hidden');
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)

