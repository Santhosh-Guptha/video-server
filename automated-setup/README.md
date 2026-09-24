# Unattended Video Server setup

Keep this entire folder together: `setup.py`, `setup.ps1`, `install.sh` and `patch-src`.

## One command on this Windows + Ubuntu WSL machine

From **Administrator PowerShell**, in this folder:

```powershell
.\setup.ps1
```

This installs dependencies, fetches the tested develop revision, applies bundled fixes, builds the UI, configures services, checks health, forwards LAN ports and registers a hidden Windows logon task to keep WSL running and refresh changed addresses. It does not embed an administrator password. OS elevation must already be granted; it cannot bypass Windows approval or an initial WSL install/reboot.

Optional separate commands:

```powershell
.\setup.ps1 -Mode install
.\setup.ps1 -Mode setup
.\setup.ps1 -Mode check
```

For another existing WSL installation, supply `-Distro`, `-LinuxUser`, and optionally `-LanIp`. The default Linux user is `santhosh`. Automatic IP selection uses the default IPv4 route; specify `-LanIp` when a VPN owns that route.

## One command directly in Ubuntu

```bash
sudo bash install.sh --user santhosh --lan-ip 172.16.2.243
```

Ubuntu-only setup does not manage Windows port forwarding. Use the PowerShell entry point for the full WSL/LAN setup. Systemd must already be enabled. The installer supports x86-64 and ARM64 Linux; it downloads SHA256-verified MediaMTX v1.21.0 and a current Node.js 22 build from their official release servers.

## Repeat runs and configuration

Existing database, recordings, credentials and service configuration are preserved. Patched source files are backed up under `/var/backups/video-server/setup-*` before replacement. An unrelated source revision is rejected instead of overwriting it. Installation pins the tested upstream base `7937d80044f76b072478197695d8a8e51dbf6891`, plus the included repairs; it does not pull arbitrary future code.

Open **Streaming Settings** in the app to select quality and recovery settings. Saved values live in `backend/app/configs/streaming_overrides.json` and take precedence over environment values for the fields exposed in that screen. Existing remote camera encoder configurations are not altered.

On a fresh install, a TURN password is generated and stored locally. Existing installations retain their TURN settings. Firewall rules are limited to the local subnet on Domain/Private profiles. No router/public Internet forwarding is configured.

## Validation scope

Service and HTTP checks verify the application, not every camera. Upstream addresses must be reachable and credentials valid. HD quality requires a working HD source; compatible device decoding and sufficient bandwidth are also required. A new machine may need VPN/routes to reach private cameras. No installer can automatically recover inaccessible remote cameras or create genuine HD detail from SD sources.

Fresh-machine installation has not yet been validated on a disposable clean Ubuntu instance. Current-host configuration and health verification are tracked separately in the delivery report.
