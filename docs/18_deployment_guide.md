# Deployment Guide
**Project**: Enterprise Video Management System (VMS)  
**Owner**: DevOps Team  

---

## 1. Ubuntu Server Deployment Steps
1. Install dependencies:
   ```bash
   sudo apt install -y git python3-pip python3-venv nodejs redis-server ffmpeg sqlite3
   ```
2. Clone repository to `/opt/video-server`.
3. Create Python virtual environment and run the automated `setup.sh` script.
4. Copy customized `mediamtx.service` and configuration files.
5. Reload systemd and start all services.
