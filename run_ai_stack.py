import os
import sys
import subprocess
import time
import shutil

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    ai_service_dir = os.path.join(root_dir, "ai_service")
    ai_frontend_dir = os.path.join(root_dir, "ai_frontend")

    print("=" * 70)
    print("      LAUNCHING STANDALONE AI ANALYTICS MICROSERVICE & UI STACK      ")
    print("=" * 70)
    print(f"[1/2] AI Service Directory : {ai_service_dir}")
    print(f"[2/2] AI Frontend Directory: {ai_frontend_dir}")
    print("-" * 70)

    # 1. Start AI Service Backend on port 8001
    sys.path.insert(0, root_dir)
    print(">> Starting AI Service FastAPI Backend on http://localhost:8001 ...")
    
    service_cmd = [
        sys.executable, "-m", "uvicorn",
        "ai_service.main:app",
        "--host", "0.0.0.0",
        "--port", "8001",
        "--reload"
    ]

    service_proc = subprocess.Popen(service_cmd, cwd=root_dir)

    # Give backend a moment to bind port 8001
    time.sleep(2)

    # 2. Check node / npm for AI Frontend UI
    npm_path = shutil.which("npm") or shutil.which("npm.cmd")
    if npm_path and os.path.exists(os.path.join(ai_frontend_dir, "package.json")):
        print(">> Launching AI Analytics Dashboard UI on http://localhost:5174 ...")
        # Check node_modules
        if not os.path.exists(os.path.join(ai_frontend_dir, "node_modules")):
            print(">> Running npm install for AI Frontend...")
            subprocess.run([npm_path, "install"], cwd=ai_frontend_dir, shell=True)

        frontend_proc = subprocess.Popen([npm_path, "run", "dev"], cwd=ai_frontend_dir, shell=True)
    else:
        frontend_proc = None
        print(">> Note: npm not found locally or node_modules missing. You can launch UI via 'npm run dev' inside ai_frontend/")

    print("=" * 70)
    print("AI STACK IS ONLINE:")
    print(" - AI REST & WebSocket API : http://localhost:8001 (Docs: /docs)")
    print(" - AI Analytics UI         : http://localhost:5174")
    print("=" * 70)
    print("Press Ctrl+C to terminate the AI Stack processes.")

    try:
        service_proc.wait()
        if frontend_proc:
            frontend_proc.wait()
    except KeyboardInterrupt:
        print("\nStopping AI Stack processes...")
        service_proc.terminate()
        if frontend_proc:
            frontend_proc.terminate()

if __name__ == "__main__":
    main()
