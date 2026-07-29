import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { execSync } from 'child_process'

function getBackendTarget() {
  if (process.env.VITE_BACKEND_URL) {
    return process.env.VITE_BACKEND_URL
  }

  // If running on Windows, resolve WSL IP address dynamically so proxy connects seamlessly to backend running in WSL
  if (process.platform === 'win32') {
    try {
      const wslIp = execSync('wsl hostname -I', { encoding: 'utf8' }).trim().split(' ')[0]
      if (wslIp) {
        console.log(`[vite] Auto-detected WSL IP: ${wslIp} for backend proxy target`)
        return `http://${wslIp}:8005`
      }
    } catch {
      // Fallback if WSL command is unavailable
    }
  }

  return 'http://127.0.0.1:8005'
}

const targetBackend = getBackendTarget()
const targetWs = targetBackend.replace(/^http/, 'ws')

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    watch: {
      usePolling: true
    },
    proxy: {
      '/api': targetBackend,
      '/ws': { target: targetWs, ws: true }
    }
  },
  preview: {
    host: '0.0.0.0',
    port: 3000,
    headers: {
      'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'
    },
    proxy: {
      '/api': targetBackend,
      '/ws': { target: targetWs, ws: true }
    }
  }
})
