import asyncio
import time
import httpx
from typing import Dict, Any, Optional
from .policy_loader import PolicyLoader
from .transcoding_decision_engine import TranscodingDecisionEngine

class TranscodingClient:
    _http_client: Optional[httpx.AsyncClient] = None
    _active_cloud_sessions: Dict[str, dict] = {} # session_id -> {stream_id, start_time}
    _lock = asyncio.Lock()
    _health_task: Optional[asyncio.Task] = None

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        if cls._http_client is None:
            cls._http_client = httpx.AsyncClient(timeout=3.0)
        return cls._http_client

    @classmethod
    def _get_auth_headers(cls) -> dict:
        """Helper to generate JWT auth and Tenant/Node headers."""
        secret_key = PolicyLoader.get("security_policy.yaml", "api_key_secret", "vms_secure_secret_key")
        tenant_id = os.environ.get("TENANT_ID", "tenant_default")
        node_id = os.environ.get("NODE_ID", "node_default")
        
        # Simple token generation (can be replaced by PyJWT or simple hash for production)
        bearer_token = f"VMS-{secret_key}"
        
        tenant_header = PolicyLoader.get("security_policy.yaml", "tenant_header", "X-Tenant-ID")
        node_header = PolicyLoader.get("security_policy.yaml", "node_header", "X-Node-ID")
        
        return {
            "Authorization": f"Bearer {bearer_token}",
            tenant_header: tenant_id,
            node_header: node_id,
            "Content-Type": "application/json"
        }

    @classmethod
    async def start_session(
        cls,
        stream_id: str,
        session_id: str,
        source_url: str,
        target_url: str
    ) -> bool:
        """
        Calls the Cloud Transcoding Gateway POST /start endpoint.
        Uses cached health to proceed, avoiding blocking delays.
        """
        gateway_url = PolicyLoader.get("cluster_policy.yaml", "cloud_gateway_url", "http://localhost:8500")
        client = cls.get_client()
        headers = cls._get_auth_headers()
        
        payload = {
            "stream_id": stream_id,
            "session_id": session_id,
            "source_url": source_url,
            "target_url": target_url
        }
        
        try:
            url = f"{gateway_url.rstrip('/')}/start"
            print(f"[transcoding_client] Requesting cloud start: {url} for stream {stream_id}")
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                async with cls._lock:
                    cls._active_cloud_sessions[session_id] = {
                        "stream_id": stream_id,
                        "start_time": time.time()
                    }
                print(f"[transcoding_client] Cloud transcoder started successfully for {stream_id}")
                return True
            else:
                print(f"[transcoding_client] Cloud start failed with status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            print(f"[transcoding_client] Cloud connection error on start: {e}")
            return False

    @classmethod
    async def stop_session(cls, stream_id: str, session_id: str) -> bool:
        """Calls Cloud Transcoding Gateway DELETE /stop."""
        gateway_url = PolicyLoader.get("cluster_policy.yaml", "cloud_gateway_url", "http://localhost:8500")
        client = cls.get_client()
        headers = cls._get_auth_headers()
        
        payload = {
            "stream_id": stream_id,
            "session_id": session_id
        }
        
        async with cls._lock:
            cls._active_cloud_sessions.pop(session_id, None)

        try:
            url = f"{gateway_url.rstrip('/')}/stop"
            resp = await client.request("DELETE", url, json=payload, headers=headers)
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"[transcoding_client] Cloud connection error on stop: {e}")
            return False

    @classmethod
    async def run_background_health_check(cls):
        """
        Asynchronous loop running in background.
        Pings gateway health and sends session heartbeats.
        Guarantees that live stream router is NEVER BLOCKED by slow cloud calls.
        """
        print("[transcoding_client] Starting background health check & heartbeat loop...")
        while True:
            gateway_url = PolicyLoader.get("cluster_policy.yaml", "cloud_gateway_url", "http://localhost:8500")
            client = cls.get_client()
            headers = cls._get_auth_headers()
            
            # 1. Ping Health
            try:
                url = f"{gateway_url.rstrip('/')}/health"
                resp = await client.get(url, headers=headers, timeout=2.0)
                is_healthy = resp.status_code == 200
                await TranscodingDecisionEngine.set_cloud_health(is_healthy)
            except Exception:
                await TranscodingDecisionEngine.set_cloud_health(False)
            
            # 2. Send Heartbeats for active sessions
            active_sessions = []
            async with cls._lock:
                active_sessions = [
                    {"session_id": sid, "stream_id": data["stream_id"]}
                    for sid, data in cls._active_cloud_sessions.items()
                ]
            
            if active_sessions:
                try:
                    hb_url = f"{gateway_url.rstrip('/')}/heartbeat"
                    await client.post(hb_url, json={"sessions": active_sessions}, headers=headers, timeout=2.0)
                except Exception as ex:
                    print(f"[transcoding_client] Failed to send heartbeats: {ex}")

            # Interval between checks
            interval = PolicyLoader.get("session_policy.yaml", "heartbeat_interval_seconds", 15)
            await asyncio.sleep(interval)

    @classmethod
    def start_background_loop(cls):
        """Starts the background task."""
        if cls._health_task is None or cls._health_task.done():
            cls._health_task = asyncio.create_task(cls.run_background_health_check())

import os
