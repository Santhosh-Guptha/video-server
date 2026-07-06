import os
import sys
import time
import json
import asyncio
import subprocess
import shutil
from typing import List, Dict
import psutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="VMS Independent Monitoring Portal")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Services to monitor
MONITORED_SERVICES = {
    "video-backend": "video-backend.service",
    "video-frontend": "video-frontend.service",
    "mediamtx": "mediamtx.service",
    "redis-server": "redis-server.service",
    "postgresql": "postgresql.service"
}

# Service storage files configuration (ROM)
SERVICE_STORAGE_PATHS = {
    "video-backend": ["/opt/video-server/backend", "/opt/video-backend-venv"],
    "video-frontend": ["/opt/video-server/frontend"],
    "mediamtx": ["/mnt/storage"],
    "redis-server": ["/var/lib/redis"],
    "postgresql": ["/var/lib/postgresql"]
}

# In-memory storage/ROM usage cache
service_rom_usage = {
    "video-backend": "Calculating...",
    "video-frontend": "Calculating...",
    "mediamtx": "Calculating...",
    "redis-server": "Calculating...",
    "postgresql": "Calculating..."
}

# Cache for latest telemetry
latest_telemetry = {}
ws_connections: List[WebSocket] = []

# State for speed measurements
last_io_time = time.time()
disk_io = psutil.disk_io_counters()
net_io = psutil.net_io_counters()
last_disk_read = disk_io.read_bytes if disk_io else 0
last_disk_write = disk_io.write_bytes if disk_io else 0
last_net_recv = net_io.bytes_recv if net_io else 0
last_net_sent = net_io.bytes_sent if net_io else 0

def get_io_speeds():
    global last_io_time, last_disk_read, last_disk_write, last_net_recv, last_net_sent
    now = time.time()
    dt = now - last_io_time
    if dt <= 0:
        dt = 1.0
    
    disk_io = psutil.disk_io_counters()
    net_io = psutil.net_io_counters()
    
    curr_disk_read = disk_io.read_bytes if disk_io else 0
    curr_disk_write = disk_io.write_bytes if disk_io else 0
    curr_net_recv = net_io.bytes_recv if net_io else 0
    curr_net_sent = net_io.bytes_sent if net_io else 0
    
    disk_read_speed = max(0.0, (curr_disk_read - last_disk_read) / dt / (1024 * 1024))
    disk_write_speed = max(0.0, (curr_disk_write - last_disk_write) / dt / (1024 * 1024))
    net_in_speed = max(0.0, (curr_net_recv - last_net_recv) / dt / (1024 * 1024))
    net_out_speed = max(0.0, (curr_net_sent - last_net_sent) / dt / (1024 * 1024))
    
    last_io_time = now
    last_disk_read = curr_disk_read
    last_disk_write = curr_disk_write
    last_net_recv = curr_net_recv
    last_net_sent = curr_net_sent
    
    # Check I/O wait percent (Linux specific)
    io_wait = 0.0
    try:
        cpu_times = psutil.cpu_times_percent()
        io_wait = getattr(cpu_times, "iowait", 0.0)
    except Exception:
        pass
        
    return {
        "disk_read_mb_s": round(disk_read_speed, 2),
        "disk_write_mb_s": round(disk_write_speed, 2),
        "net_in_mb_s": round(net_in_speed, 2),
        "net_out_mb_s": round(net_out_speed, 2),
        "io_wait_percent": round(io_wait, 1)
    }

def get_service_status(service_name: str) -> dict:
    """Queries systemd status on Linux or returns mock on non-Linux."""
    short_name = service_name.replace(".service", "")
    rom_val = service_rom_usage.get(short_name, "Calculating...")
    
    if sys.platform != "linux":
        # Mock status for Windows local tests
        return {
            "status": "active" if service_name != "postgresql.service" else "inactive",
            "uptime": "2h 45m",
            "cpu_percent": 1.2,
            "memory_mb": 120.5,
            "threads": 8,
            "rom_usage": rom_val
        }
        
    try:
        # Check active status
        cmd = ["systemctl", "show", service_name, "--property=ActiveState,SubState,ActiveEnterTimestamp"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2.0)
        lines = res.stdout.strip().split("\n")
        props = {}
        for line in lines:
            if "=" in line:
                k, v = line.split("=", 1)
                props[k.strip()] = v.strip()
                
        status = props.get("ActiveState", "unknown")
        substate = props.get("SubState", "")
        
        # Calculate uptime
        uptime_str = "N/A"
        active_enter = props.get("ActiveEnterTimestamp", "")
        if active_enter and active_enter != "n/a" and active_enter != "":
            try:
                # Format: Mon 2026-07-06 14:57:11 UTC
                # Simply output a trimmed representation
                uptime_str = active_enter.split(" ", 1)[-1]
            except Exception:
                pass
                
        # Get resource consumption of the process
        cpu_percent = 0.0
        memory_mb = 0.0
        threads = 0
        
        # Find pid of systemd service
        pid_cmd = ["systemctl", "show", service_name, "--property=MainPID"]
        pid_res = subprocess.run(pid_cmd, stdout=subprocess.PIPE, text=True, timeout=2.0)
        pid_lines = pid_res.stdout.strip().split("=")
        if len(pid_lines) == 2 and pid_lines[1].isdigit():
            pid = int(pid_lines[1])
            if pid > 0:
                try:
                    proc = psutil.Process(pid)
                    cpu_percent = round(proc.cpu_percent(interval=None), 1)
                    memory_mb = round(proc.memory_info().rss / (1024 * 1024), 1)
                    threads = proc.num_threads()
                except Exception:
                    pass
                    
        return {
            "status": f"{status} ({substate})" if substate else status,
            "uptime": uptime_str,
            "cpu_percent": cpu_percent,
            "memory_mb": memory_mb,
            "threads": threads,
            "rom_usage": rom_val
        }
    except Exception as e:
        return {
            "status": f"failed to query: {str(e)}", 
            "uptime": "unknown", 
            "cpu_percent": 0.0, 
            "memory_mb": 0.0, 
            "threads": 0,
            "rom_usage": rom_val
        }

def get_service_logs(service_name: str, lines_count: int = 40) -> List[str]:
    """Retrieves journalctl log files for service on Linux or returns mock."""
    if sys.platform != "linux":
        return [
            f"[INFO] 2026-07-06T16:20:00Z {service_name} started successfully.",
            f"[WARNING] 2026-07-06T16:22:15Z {service_name} connection latency elevated.",
            f"[INFO] 2026-07-06T16:24:10Z {service_name} processing jobs cleanly."
        ]
        
    try:
        cmd = ["journalctl", "-u", service_name, "-n", str(lines_count), "--no-pager"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3.0)
        return res.stdout.strip().split("\n")
    except Exception as e:
        return [f"Failed to fetch logs for {service_name}: {str(e)}"]

def scan_log_issues() -> List[dict]:
    """Scrapes journalctl output for warnings and errors across services."""
    issues = []
    
    # Quick health check of services
    for service_name, systemd_unit in MONITORED_SERVICES.items():
        state = get_service_status(systemd_unit)
        if "active" not in state["status"]:
            issues.append({
                "id": f"service_down_{service_name}",
                "severity": "critical",
                "service": service_name,
                "message": f"Service is down: {state['status']}",
                "timestamp": int(time.time())
            })
            
        # Scrape logs for critical lines
        logs = get_service_logs(systemd_unit, 20)
        for log in logs:
            log_lower = log.lower()
            if "error" in log_lower or "exception" in log_lower or "failed" in log_lower:
                # Truncate clean message
                msg = log.split("]")[-1] if "]" in log else log
                issues.append({
                    "id": f"log_err_{service_name}_{hash(log)%100000}",
                    "severity": "warning",
                    "service": service_name,
                    "message": msg.strip()[:100],
                    "timestamp": int(time.time())
                })
                
    return issues[:15] # Limit list to prevent clutter

async def collect_telemetry_loop():
    global latest_telemetry
    print("[monitoring-app] Telemetry background collection loop started.")
    
    while True:
        try:
            # 1. Host Stats
            cpu_percent = psutil.cpu_percent()
            cpu_count = psutil.cpu_count()
            vm = psutil.virtual_memory()
            
            # Disk ROM stats
            def get_disk_stats(path: str):
                try:
                    usage = shutil.disk_usage(path)
                    return {
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": round((usage.used / usage.total) * 100.0, 1) if usage.total > 0 else 0.0
                    }
                except Exception:
                    return {"total": 0, "used": 0, "free": 0, "percent": 0.0}
                    
            storage_path = "/mnt/storage" if os.path.exists("/mnt/storage") else "/var/tmp"
            disk_root = get_disk_stats("/")
            disk_storage = get_disk_stats(storage_path)
            speeds = get_io_speeds()
            
            net_err = psutil.net_io_counters()
            packets_dropped = (net_err.dropin + net_err.dropout) if net_err else 0
            
            # 2. Services Info
            services_info = {}
            for name, unit in MONITORED_SERVICES.items():
                services_info[name] = get_service_status(unit)
                
            # 3. Logs Scraping
            logs_feed = {}
            for name, unit in MONITORED_SERVICES.items():
                logs_feed[name] = get_service_logs(unit, 30)
                
            # 4. Scrape active issues
            issues = scan_log_issues()
            
            # Additional hardware alerts
            if cpu_percent > 90.0:
                issues.append({"id": "cpu_extreme", "severity": "critical", "service": "system", "message": f"Extreme CPU consumption: {cpu_percent}%", "timestamp": int(time.time())})
            if vm.percent > 85.0:
                issues.append({"id": "ram_extreme", "severity": "critical", "service": "system", "message": f"Elevated RAM utilization: {vm.percent}%", "timestamp": int(time.time())})
            if disk_storage["percent"] > 95.0:
                issues.append({"id": "storage_full", "severity": "critical", "service": "storage", "message": f"Recording storage space full: {disk_storage['percent']}%", "timestamp": int(time.time())})
            
            # Compile payload
            latest_telemetry = {
                "timestamp": int(time.time()),
                "system": {
                    "cpu_percent": cpu_percent,
                    "cpu_count": cpu_count,
                    "ram_total_gb": round(vm.total / (1024**3), 2),
                    "ram_used_gb": round(vm.used / (1024**3), 2),
                    "ram_available_gb": round(vm.available / (1024**3), 2),
                    "ram_percent": vm.percent,
                    "disk_root": disk_root,
                    "disk_storage": disk_storage,
                    "speeds": speeds,
                    "packets_dropped": packets_dropped
                },
                "services": services_info,
                "logs": logs_feed,
                "issues": issues
            }
            
            # Broadcast to WebSockets
            dead_conns = []
            for ws in ws_connections:
                try:
                    await ws.send_json(latest_telemetry)
                except Exception:
                    dead_conns.append(ws)
            for ws in dead_conns:
                if ws in ws_connections:
                    ws_connections.remove(ws)
                    
        except Exception as e:
            print(f"[monitoring-app] Error in telemetry collector: {e}", file=sys.stderr)
            
        await asyncio.sleep(2.0)

# REST API Endpoints
class ServiceAction(BaseModel):
    action: str # "start", "stop", "restart"

@app.post("/api/services/{service_name}/action")
def control_service(service_name: str, payload: ServiceAction):
    if service_name not in MONITORED_SERVICES:
        raise HTTPException(status_code=404, detail="Service not monitored")
        
    unit = MONITORED_SERVICES[service_name]
    action = payload.action.lower()
    
    if action not in ["start", "stop", "restart"]:
        raise HTTPException(status_code=400, detail="Invalid service action")
        
    if sys.platform != "linux":
        return {"status": "ok", "message": f"[MOCK] Executed {action} on {unit} successfully."}
        
    try:
        cmd = ["sudo", "systemctl", action, unit]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5.0)
        if res.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Failed to control service: {res.stderr.strip()}")
        return {"status": "ok", "message": f"Successfully performed {action} on {service_name}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/telemetry")
def get_current_telemetry():
    return latest_telemetry if latest_telemetry else {"status": "loading", "message": "Telemetry server warming up..."}

@app.websocket("/ws")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_connections.append(websocket)
    try:
        # Send initial payload immediately
        if latest_telemetry:
            await websocket.send_json(latest_telemetry)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in ws_connections:
            ws_connections.remove(websocket)
    except Exception:
        if websocket in ws_connections:
            ws_connections.remove(websocket)

# Mount frontend static directory
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    @app.get("/")
    def fallback_index():
        return HTMLResponse("<h3>VMS Monitor Static Front-End is not yet created. Check back soon.</h3>")

async def scan_directories_size_loop():
    global service_rom_usage
    print("[monitoring-app] Directory size scan loop started.")
    
    while True:
        try:
            if sys.platform != "linux":
                # Mock ROM usage for non-Linux
                service_rom_usage["video-backend"] = "5.5 GB"
                service_rom_usage["video-frontend"] = "145.0 MB"
                service_rom_usage["mediamtx"] = "461.0 GB"
                service_rom_usage["redis-server"] = "27.0 MB"
                service_rom_usage["postgresql"] = "100.0 MB"
            else:
                for service, paths in SERVICE_STORAGE_PATHS.items():
                    total_kb = 0
                    for path in paths:
                        if os.path.exists(path):
                            try:
                                # Quick subprocess du
                                res = subprocess.run(["du", "-sk", path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5.0)
                                if res.returncode == 0:
                                    total_kb += int(res.stdout.strip().split()[0])
                            except Exception:
                                pass
                    # Format
                    if total_kb >= 1024 * 1024:
                        service_rom_usage[service] = f"{round(total_kb / (1024 * 1024), 2)} GB"
                    elif total_kb >= 1024:
                        service_rom_usage[service] = f"{round(total_kb / 1024, 1)} MB"
                    else:
                        service_rom_usage[service] = f"{total_kb} KB"
        except Exception as e:
            print(f"[monitoring-app] Error in directory scanner: {e}", file=sys.stderr)
            
        # Run every 120 seconds
        await asyncio.sleep(120.0)

@app.on_event("startup")
async def app_startup():
    # Run the collector loop and directory scanner in background tasks
    asyncio.create_task(scan_directories_size_loop())
    asyncio.create_task(collect_telemetry_loop())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8010, reload=True)
