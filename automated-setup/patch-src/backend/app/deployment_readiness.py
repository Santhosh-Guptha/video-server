"""Read-only release checks. A healthy process is not a secure deployment."""
import argparse
import json
import time
from urllib.parse import urlsplit


def report(settings, mode="onprem"):
    if mode not in ("onprem", "hosted"):
        raise ValueError("Deployment mode must be onprem or hosted")
    checks = []

    def add(key, status, title, detail):
        checks.append(dict(id=key, status=status, title=title, detail=detail))

    # These capabilities must be implemented and verified, never enabled by a
    # self-declared environment flag or inferred from a proxy's response headers.
    add("identity", "blocked", "Identity and permissions",
        "Application sign-in and administrator/operator/viewer enforcement are not implemented. Restrict access to a trusted network.")
    add("media_authorization", "blocked", "Media access protection",
        "Direct MediaMTX access has not been secured with per-user authorization. Protecting the web page alone does not protect camera video.")
    add("tls", "unverified", "HTTPS and certificates",
        "Certificate validity, renewal and HTTPS-only access require an external deployment test.")
    add("restore", "unverified", "Disaster recovery",
        "Policy export is available. A tested restore of the database, media and private configuration is still required.")
    add("playback", "unverified", "Live and recording compatibility",
        "Complete a sustained device/network test measuring first decoded frame, freezes and recording playback; signaling success is insufficient.")

    quota = getattr(settings, "recording_storage_limit_gb", 0)
    retention = getattr(settings, "enable_retention", False)
    days = getattr(settings, "default_retention_days", 0)
    add("storage", "pass" if quota > 0 else "warning", "Recording space limit",
        "A recording quota is configured; monitor remaining disk space." if quota > 0 else
        "No recording quota is configured. Retention by age alone cannot bound disk usage.")
    add("retention", "pass" if retention and days > 0 else "warning", "Retention policy",
        "Automatic retention is configured; per-camera overrides may differ." if retention and days > 0 else
        "Automatic retention is disabled or has no positive default duration.")

    turn = getattr(settings, "turn_server_url", "")
    credential = getattr(settings, "turn_server_credential", "")
    known_defaults = {"", "vms_turn_password", "vms_secure_password", "password", "changeme"}
    add("turn", "warning" if not turn else "blocked" if credential in known_defaults else "unverified",
        "TURN relay", "TURN is not configured." if not turn else
        "Replace the default TURN credential." if credential in known_defaults else
        "A non-default credential is configured; relay reachability and credential rotation still need verification.")

    try:
        parsed = urlsplit(getattr(settings, "mediamtx_api_url", ""))
        loopback = parsed.scheme in ("http", "https") and parsed.hostname in ("127.0.0.1", "::1", "localhost")
    except ValueError:
        loopback = False
    add("media_management", "pass" if loopback else "warning",
        "Media management endpoint",
        "The application uses a loopback management endpoint. This does not verify the listener or firewall." if loopback else
        "The application uses a non-loopback media management endpoint. Verify authentication and network isolation.")
    if mode == "hosted":
        add("tenant_isolation", "blocked", "Customer isolation",
            "Use a separate instance, database, media storage and credentials per customer. Shared-database multi-tenancy is not implemented or verified.")
    return {"checked_at": time.time(), "mode": mode, "ready": False,
            "status": "blocked", "checks": checks,
            "blocking_count": sum(c["status"] == "blocked" for c in checks),
            "scope": "Configuration and known implementation gaps only; no camera connections or configuration changes are made."}


def enforce_deployment_mode(settings):
    mode = getattr(settings, "deployment_mode", "onprem")
    if mode not in ("onprem", "hosted"):
        raise RuntimeError("Unknown DEPLOYMENT_MODE; use onprem or hosted")
    if mode == "hosted" and not report(settings, mode)["ready"]:
        raise RuntimeError("Hosted deployment blocked: run python -m app.deployment_readiness --mode hosted for release requirements")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("onprem", "hosted"), default="onprem")
    args = parser.parse_args()
    from .config import settings
    result = report(settings, args.mode)
    print(json.dumps(result, indent=2))
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
