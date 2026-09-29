# Unattended Video Server setup

For Windows, `setup.ps1` is the only file to copy or download. It fetches the complete `develop` checkout inside Ubuntu WSL and runs the bundled Linux installer. The other files remain in the repository for that installer.

## One command on this Windows + Ubuntu WSL machine

From PowerShell, run the copied file. It requests Windows elevation when needed:

```powershell
.\setup.ps1
```

This installs dependencies, fetches the `develop` checkout, builds the UI, configures services, checks health, disables WSL's idle shutdown, forwards LAN ports and registers a Windows logon task to start WSL and refresh changed addresses. It does not embed an administrator password. Windows still requires approval of its UAC prompt and may require a reboot to finish an initial WSL installation.

Optional separate commands:

```powershell
.\setup.ps1 -Mode install
.\setup.ps1 -Mode setup
.\setup.ps1 -Mode check
```

For another existing WSL installation, supply `-Distro`, `-LinuxUser`, and optionally `-LanIp`. The default Linux user is `santhosh`. Automatic IP selection uses the default IPv4 route; specify `-LanIp` when a VPN owns that route.

## One command directly in Ubuntu

```bash
sudo bash install.sh --user santhosh --lan-ip 172.22.3.86
```

Ubuntu-only setup does not manage Windows port forwarding. Use the PowerShell entry point for the full WSL/LAN setup. Systemd must already be enabled. The installer supports x86-64 and ARM64 Linux; it downloads SHA256-verified MediaMTX v1.21.0 and a current Node.js 22 build from their official release servers.

## Repeat runs and configuration

Existing database, recordings, credentials and service configuration are preserved. Older tested checkouts receive bundled fixes with backups under `/var/backups/video-server/setup-*`; current checkouts keep their committed source unchanged. An unrelated source revision is rejected. The standalone Windows file fetches current `develop` and fast-forwards a clean existing checkout. The Linux installer verifies that source descends from its tested base. Local changes are never overwritten automatically.

Open **Streaming Settings** in the app to select quality and recovery settings. Saved values live in `backend/app/configs/streaming_overrides.json` and take precedence over environment values for the fields exposed in that screen. Existing remote camera encoder configurations are not altered.

On a fresh install, a TURN password is generated and stored locally. Existing installations retain their TURN settings. Firewall rules are limited to the local subnet on Domain/Private profiles. No router/public Internet forwarding is configured.

## Validation scope

Service and HTTP checks verify the application, not every camera. Upstream addresses must be reachable and credentials valid. HD quality requires a working HD source; compatible device decoding and sufficient bandwidth are also required. A new machine may need VPN/routes to reach private cameras. No installer can automatically recover inaccessible remote cameras or create genuine HD detail from SD sources.

Fresh installation completed on a newly registered Ubuntu 24.04 WSL distribution on 25 September 2026. Service and HTTP checks passed. Windows Administrator port-forwarding and logon-task registration still require an elevated PowerShell run. See the streaming configuration document for camera-source limitations.

Shared RTSP ingest and editable per-endpoint capacity controls are included in the installer. Existing camera sources are preserved when above the default six-slot budget; new sources wait for capacity. See `STREAMING-CONFIGURATION.md` for scope, migration and configuration.
