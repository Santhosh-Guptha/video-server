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


@router.get("/workers")
async def get_workers(auth_data: dict = Depends(verify_auth)):
    """Exposes statistics on worker process pools."""
    return await TranscodingWorkerPool.get_worker_status()
