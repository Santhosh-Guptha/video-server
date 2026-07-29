# ============================================================
# WSL Network Expose Script
# Run this script as Administrator to forward WSL ports to LAN
# ============================================================

# Fetch current WSL IP dynamically
$WSL_IP = (wsl -d Ubuntu-22.04 hostname -I).Trim().Split()[0]
$WIN_IP  = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "Wi-Fi*", "Ethernet*" | Select-Object -First 1).IPAddress

$ports = @(
    @{ Port = 8005; Desc = "FastAPI Backend" },
    @{ Port = 8010; Desc = "Observability Portal" },
    @{ Port = 5173; Desc = "Web UI (Vite)" },
    @{ Port = 9999; Desc = "Edge TCP Push Receiver" },
    @{ Port = 8554; Desc = "MediaMTX RTSP" },
    @{ Port = 8889; Desc = "MediaMTX HTTP Signaling" },
    @{ Port = 8189; Desc = "MediaMTX WebRTC TCP Multiplexer" }
)

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Camera Video Platform - WSL Network Expose" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "WSL IP  : $WSL_IP" -ForegroundColor Yellow
Write-Host "Windows : $WIN_IP" -ForegroundColor Yellow
Write-Host ""

foreach ($p in $ports) {
    $port = $p.Port
    $desc = $p.Desc

    $existing = netsh interface portproxy show v4tov4 | Select-String ":$port"
    if ($existing) {
        netsh interface portproxy delete v4tov4 listenport=$port listenaddress=0.0.0.0 | Out-Null
        Write-Host "  Removed old rule for port $port" -ForegroundColor DarkGray
    }

    netsh interface portproxy add v4tov4 listenport=$port listenaddress=0.0.0.0 connectport=$port connectaddress=$WSL_IP | Out-Null
    Write-Host "  [PORT PROXY] $port ($desc) -> WSL:$port" -ForegroundColor Green

    $ruleName = "CamPlatform-$port"
    netsh advfirewall firewall delete rule name="$ruleName" | Out-Null
    netsh advfirewall firewall add rule name="$ruleName" dir=in action=allow protocol=TCP localport=$port | Out-Null
    Write-Host "  [FIREWALL]   Port $port opened inbound" -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " All ports are now exposed on your LAN!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " Access URLs (share with office colleagues):" -ForegroundColor White
Write-Host ""
Write-Host "  Web UI / API   : http://${WIN_IP}:8000" -ForegroundColor Yellow
Write-Host "  Edge TCP Push  : ${WIN_IP}:9999   (TCP)" -ForegroundColor Yellow
Write-Host "  RTSP Stream    : rtsp://${WIN_IP}:8554/{camera_id}" -ForegroundColor Yellow
Write-Host "  HLS / WebRTC   : http://${WIN_IP}:8889/{camera_id}" -ForegroundColor Yellow
Write-Host ""
Write-Host " Current Port Proxy Rules:" -ForegroundColor White
netsh interface portproxy show all
Write-Host ""
