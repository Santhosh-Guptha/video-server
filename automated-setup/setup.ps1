# Standalone entry point: copy this one file and run it in Administrator PowerShell.
# It fetches the complete develop checkout inside Ubuntu WSL.
[CmdletBinding()]
param(
    [ValidateSet('all','install','setup','check')][string]$Mode = 'all',
    [string]$Distro = 'Ubuntu-24.04',
    [string]$LinuxUser = 'santhosh',
    [string]$LanIp,
    [switch]$NetworkOnly
)
$ErrorActionPreference = 'Stop'
$Repo = 'https://github.com/Santhosh-Guptha/video-server.git'
if ($LinuxUser -notmatch '^[a-z_][a-z0-9_-]*$') { throw 'Invalid Linux user name.' }
if ($Distro -notmatch '^[A-Za-z0-9._-]+$') { throw 'Invalid WSL distribution name.' }
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $LanIp) {
    $route = Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1
    $LanIp = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex | Where-Object { $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1).IPAddress
}
[void][Net.IPAddress]::Parse($LanIp)
if (-not $admin -and ($Mode -ne 'check' -or $NetworkOnly)) {
    # Windows must show its UAC prompt; no stored password or silent bypass.
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"{0}"' -f $PSCommandPath),
                   '-Mode',$Mode,'-Distro',$Distro,'-LinuxUser',$LinuxUser,'-LanIp',$LanIp)
    if ($NetworkOnly) { $arguments += '-NetworkOnly' }
    $elevated = Start-Process -FilePath powershell.exe -ArgumentList $arguments -Verb RunAs -WindowStyle Hidden -Wait -PassThru
    exit $elevated.ExitCode
}
$distros = (& wsl.exe --list --quiet) -replace "`0", ''
if ($distros -notcontains $Distro) {
    if ($Mode -eq 'check' -or $NetworkOnly) { throw "WSL distribution $Distro is not installed." }
    & wsl.exe --install -d $Distro --no-launch
    if ($LASTEXITCODE -ne 0) { throw "Could not install $Distro." }
    $distros = (& wsl.exe --list --quiet) -replace "`0", ''
    if ($distros -notcontains $Distro) { throw "Windows must finish registering $Distro, possibly after a reboot." }
}

# Keep the distribution alive after the last WSL shell exits. Without this,
# WSL's default idle timeout stops every service even though systemd is active.
if ($Mode -ne 'check') {
    $wslConfigPath = Join-Path $env:USERPROFILE '.wslconfig'
    $wslConfig = if (Test-Path -LiteralPath $wslConfigPath) { [IO.File]::ReadAllText($wslConfigPath) } else { '' }
    $updatedWslConfig = $wslConfig
    if ($updatedWslConfig -match '(?m)^\s*instanceIdleTimeout\s*=') {
        $updatedWslConfig = [regex]::Replace($updatedWslConfig, '(?m)^\s*instanceIdleTimeout\s*=\s*[^\r\n]*', 'instanceIdleTimeout=-1')
    } elseif ($updatedWslConfig -match '(?m)^\[general\]\s*$') {
        $updatedWslConfig = [regex]::Replace($updatedWslConfig, '(?m)^\[general\]\s*$', "[general]`r`ninstanceIdleTimeout=-1", 1)
    } else {
        $updatedWslConfig = $updatedWslConfig.TrimEnd() + "`r`n[general]`r`ninstanceIdleTimeout=-1`r`n"
    }
    if ($updatedWslConfig -ne $wslConfig) {
        [IO.File]::WriteAllText($wslConfigPath, $updatedWslConfig, [Text.UTF8Encoding]::new($false))
        & wsl.exe --shutdown
        if ($LASTEXITCODE -ne 0) { throw 'Could not restart WSL after updating its idle timeout.' }
    }
}

# Bootstrap from this file alone. The repository supplies the Linux installer
# and its patch files; the caller does not need to keep an installer folder.
$bootstrap = @'
import pathlib, pwd, shutil, subprocess, sys, time
user, mode, repo = sys.argv[1:]
try:
    account = pwd.getpwnam(user)
except KeyError:
    if mode in ("check", "network"): raise RuntimeError("Linux user is missing")
    subprocess.run(["useradd", "-m", "-s", "/bin/bash", "-G", "sudo", user], check=True)
    account = pwd.getpwnam(user)
root = pathlib.Path(account.pw_dir) / "video-server"
def output(*args):
    return subprocess.check_output(args, text=True).strip()
def as_user(*args):
    subprocess.run(["runuser", "-u", user, "--", *args], check=True)
if not shutil.which("git"):
    if mode in ("check", "network"): raise RuntimeError("Git is not installed")
    subprocess.run(["apt-get", "update"], check=True)
    subprocess.run(["apt-get", "install", "-y", "git", "ca-certificates"], check=True)
if not root.exists():
    if mode in ("check", "network"): raise RuntimeError("Video server is not installed")
    as_user("git", "clone", "--branch", "develop", "--single-branch", repo, str(root))
elif not (root / ".git").is_dir():
    if root.is_symlink() or any(p.is_file() or p.is_symlink() for p in root.rglob('*')):
        raise RuntimeError("Installation directory contains non-Git files; preserve or move them before setup")
    # A removed installation may leave empty recording directories behind.
    root.rename(root.with_name(root.name + ".empty-" + str(time.time_ns())))
    as_user("git", "clone", "--branch", "develop", "--single-branch", repo, str(root))
origin = output("runuser", "-u", user, "--", "git", "-C", str(root), "remote", "get-url", "origin")
if origin != repo: raise RuntimeError("Existing checkout has a different Git origin")
if mode not in ("check", "network"):
    remote = output("runuser", "-u", user, "--", "git", "ls-remote", repo, "refs/heads/develop").split()[0]
    local = output("runuser", "-u", user, "--", "git", "-C", str(root), "rev-parse", "HEAD")
    if local != remote:
        status = output("runuser", "-u", user, "--", "git", "-C", str(root), "status", "--porcelain")
        if status: raise RuntimeError("Checkout has local changes; refusing to overwrite them")
        as_user("git", "-C", str(root), "fetch", "origin", "develop")
        as_user("git", "-C", str(root), "checkout", "develop")
        as_user("git", "-C", str(root), "merge", "--ff-only", "FETCH_HEAD")
script = root / "automated-setup" / "setup.py"
if not script.is_file(): raise RuntimeError("Checkout is missing automated-setup/setup.py")
print(script)
'@
$bootstrapMode = if ($NetworkOnly) { 'network' } else { $Mode }
$bootstrapOutput = @(& wsl.exe -d $Distro -u root -- python3 -c $bootstrap $LinuxUser $bootstrapMode $Repo)
if ($LASTEXITCODE -ne 0) { throw 'Ubuntu bootstrap failed.' }
$linuxScript = [string]$bootstrapOutput[-1]
if (-not $linuxScript.StartsWith('/')) { throw 'Ubuntu bootstrap did not return an installer path.' }
if (-not $NetworkOnly) {
    & wsl.exe -d $Distro -u root -- python3 $linuxScript --mode $Mode --user $LinuxUser --lan-ip $LanIp
    if ($LASTEXITCODE -ne 0) { throw 'Ubuntu setup failed. No network rules were changed.' }
}
if ($Mode -in @('check','install') -and -not $NetworkOnly) { exit 0 }
& wsl.exe -d $Distro -u root -- python3 $linuxScript --mode network --user $LinuxUser --lan-ip $LanIp
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
if (-not $NetworkOnly) {
    $persistentDir = Join-Path $env:ProgramData 'VideoServer'
    New-Item -ItemType Directory -Path $persistentDir -Force | Out-Null
    $scriptPath = Join-Path $persistentDir 'setup.ps1'
    if ($PSCommandPath -ne $scriptPath) { Copy-Item -LiteralPath $PSCommandPath -Destination $scriptPath -Force }
    $arguments = "-NoProfile -WindowStyle Hidden -File `"$scriptPath`" -NetworkOnly -Distro `"$Distro`" -LinuxUser `"$LinuxUser`""
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User ([Security.Principal.WindowsIdentity]::GetCurrent().Name)
    $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Highest
    Register-ScheduledTask -TaskName 'VideoServer-WSL-Startup' -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
}
Write-Output "Video server ready: http://${LanIp}:5173/"
