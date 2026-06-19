# WebRTC Public Network Exposure & Production Hardening Guide

This document describes the configurations, network requirements, and security prerequisites for exposing the Video Management System (VMS) WebRTC live streaming to a public network or the internet.

---

## 1. The Core Challenge: NAT and Firewalls

In a Local Area Network (LAN), WebRTC connections can be established directly between the server and the browser using **Host Candidates** (local IP addresses). 

However, across the public internet:
1. **Symmetric NATs / Firewalls** block direct, unsolicited incoming UDP/TCP traffic to local clients.
2. **Private IP Addresses** (e.g., `172.20.100.235` or `192.168.x.x`) are not routable over the internet.

To solve this, WebRTC utilizes the **ICE (Interactive Connectivity Establishment)** framework, which relies on STUN and TURN servers.

---

## 2. Infrastructure Configuration Checklists

To make WebRTC work publicly, you must configure three distinct components: **Firewalls**, the **TURN Server (Coturn)**, and the **Streaming Media Server (MediaMTX)**.

### A. Firewall Port Configuration
Ensure your network router or cloud security group allows traffic on the following ports:

| Port / Range | Protocol | Type | Description |
| :--- | :--- | :--- | :--- |
| `80` / `443` | TCP | Inbound | Web application traffic (HTTP/HTTPS) and WHEP signaling. |
| `3478` | UDP & TCP | Inbound | Coturn listening port (STUN/TURN signaling). |
| `5349` | UDP & TCP | Inbound | Secure TURN listening port (TURNS - TLS). |
| `8554` | UDP | Inbound | MediaMTX WebRTC connection port. |
| `49152` - `65535` | UDP | Inbound | Dynamic media relay port range (used by Coturn). |

---

### B. Coturn TURN Server Configuration
Update your `/etc/turnserver.conf` to advertise the public IP address:

```ini
# Listening port
listening-port=3478

# Listening IP (internal IP address)
listening-ip=172.20.100.235

# External IP mapping (Internal_IP/Public_IP)
external-ip=172.20.100.235/<YOUR_PUBLIC_IP>

# Enable long-term credential mechanism
lt-cred-mech

# Define realm (usually server hostname or domain)
realm=vms.yourdomain.com

# User accounts (matching backend configuration)
user=admin:admin123
```

*Restart the service to apply changes:*
```bash
sudo systemctl restart coturn
```

---

### C. MediaMTX Configuration
MediaMTX must map its internal address to the public IP address so it generates public ICE candidates.

1. Open `/opt/mediamtx/mediamtx.yml`.
2. Locate and configure `webrtcICEHostNATMap` and `webrtcICEServers2`:

```yaml
# Map internal server IP to public IP for ICE host candidates
webrtcICEHostNATMap:
  172.20.100.235: <YOUR_PUBLIC_IP>

# Provide browsers with STUN/TURN servers to bypass NATs
webrtcICEServers2:
  - url: stun:stun.l.google.com:19302
  - url: turn:<YOUR_PUBLIC_IP>:3478?transport=udp
    username: admin
    password: admin123
```

*Restart the service to apply changes:*
```bash
sudo systemctl restart mediamtx
```

---

## 3. The Browser Prerequisite: HTTPS (Secure Context)

Browsers enforce a strict security policy for WebRTC: **WebRTC APIs are only available in secure contexts (HTTPS or localhost)**. If the client accesses the UI via plain HTTP over a public IP address (e.g. `http://<public-ip>:5173`), the browser will throw security errors and refuse to initialize the `RTCPeerConnection`.

### Setting up Nginx Reverse Proxy with SSL (Recommended)
Place Nginx in front of the Vite UI and FastAPI backend to terminate SSL:

```nginx
server {
    listen 443 ssl;
    server_name vms.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/vms.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vms.yourdomain.com/privkey.pem;

    # Frontend UI
    location / {
        proxy_pass http://127.0.0.1:5173;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Backend API & WHEP Signaling Proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 4. Troubleshooting Checklist

If WebRTC connections time out or fail to load video on public networks:

1. **Verify ICE Candidates**:
   - In Chrome, open `chrome://webrtc-internals/`.
   - Inspect the active `RTCPeerConnection` for `icecandidate` events.
   - Verify that candidates of type `relay` (containing the TURN server IP) or `srflx` (containing the public client IP) are gathered successfully.
   - If only `host` candidates are shown, the TURN server is unreachable or misconfigured.
2. **Check Port Connectivity**:
   - Use `nc -zuv <YOUR_PUBLIC_IP> 3478` to confirm UDP port 3478 is open from the client machine.
3. **Verify HTTPS Secure Context**:
   - Inspect the browser console. Look for errors stating `RTCPeerConnection is not a constructor` or `navigator.mediaDevices is undefined`, which confirm an insecure HTTP context blocker.
