# Run from Administrator PowerShell. No stored administrator password or prompts.
[CmdletBinding()]
param(
    [ValidateSet('all','install','setup','check')][string]$Mode = 'all',
    [string]$Distro = 'Ubuntu-22.04',
    [string]$LinuxUser = 'santhosh',
    [string]$LanIp,
    [switch]$NetworkOnly
)
$ErrorActionPreference = 'Stop'
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw 'Start this command in Administrator PowerShell; Windows networking requires elevation.' }
if (-not $LanIp) {
    $route = Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1
    $LanIp = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex | Where-Object { $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1).IPAddress
}
[void][Net.IPAddress]::Parse($LanIp)
$distros = (& wsl.exe --list --quiet) -replace "`0", ''
if ($distros -notcontains $Distro) { throw "WSL distribution $Distro is required. Install it first with wsl --install -d $Distro; Windows may require a reboot." }
$linuxBundle = (& wsl.exe -d $Distro -- wslpath -a $PSScriptRoot).Trim()
if (-not $NetworkOnly) {
    if ($LASTEXITCODE -ne 0) { throw 'Could not resolve installer directory in WSL' }
    & wsl.exe -d $Distro -u root -- python3 "$linuxBundle/setup.py" --mode $Mode --user $LinuxUser --lan-ip $LanIp
    if ($LASTEXITCODE -ne 0) { throw 'Ubuntu setup failed. No network rules were changed.' }
}
if ($Mode -in @('check','install') -and -not $NetworkOnly) { exit 0 }
& wsl.exe -d $Distro -u root -- python3 "$linuxBundle/setup.py" --mode network --user $LinuxUser --lan-ip $LanIp
if ($LASTEXITCODE -ne 0) { throw 'Could not refresh application network addresses' }
$videoWslIp = ((& wsl.exe -d $Distro -- hostname -I).Trim() -split '\s+')[0]
[void][Net.IPAddress]::Parse($videoWslIp)
$existingProxyRules = (& netsh.exe interface portproxy show v4tov4) -join "`n"
foreach ($port in @(5173,8000,3478)) {
    # Reuse an existing wildcard listener instead of creating a conflicting listener.
    $listenIp = $LanIp
    if ($existingProxyRules -match "(?m)^\s*0\.0\.0\.0\s+$port\s+") { $listenIp = '0.0.0.0' }
    & netsh.exe interface portproxy add v4tov4 "listenaddress=$listenIp" "listenport=$port" "connectaddress=$videoWslIp" "connectport=$port"
    if ($LASTEXITCODE -ne 0) { throw "Port forwarding failed for $port" }
}
if (-not (Get-NetFirewallRule -Name 'VideoServer-LAN' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name 'VideoServer-LAN' -DisplayName 'Video Server LAN' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5173,8000,3478 -RemoteAddress LocalSubnet -Profile Domain,Private | Out-Null
}
Start-Process -FilePath wsl.exe -ArgumentList @('-d',$Distro,'--exec','tail','-f','/dev/null') -WindowStyle Hidden
if (-not $NetworkOnly) {
    $scriptPath = Join-Path $PSScriptRoot 'setup.ps1'
    $arguments = "-NoProfile -WindowStyle Hidden -File `"$scriptPath`" -NetworkOnly -Distro `"$Distro`" -LinuxUser `"$LinuxUser`""
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User ([Security.Principal.WindowsIdentity]::GetCurrent().Name)
    $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Highest
    Register-ScheduledTask -TaskName 'VideoServer-WSL-Startup' -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
}
Write-Output "Video server ready: http://${LanIp}:5173/"
