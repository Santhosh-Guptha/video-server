# Security Architecture Document
**Project**: Enterprise Video Management System (VMS)  
**Owner**: Security Architect  

---

## 1. Authentication & Authorization
- Token-based API access for administrative routes.
- Access checks for WHEP signaling using transient user UUIDs.

## 2. Network Layout
- Restrict access to MediaMTX API (`9997`) and CLI utilities.
- Allow ingress traffic only on ports `8000` (FastAPI), `8889` (WebRTC signaling), and `8189` (WebRTC UDP).
