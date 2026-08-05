import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { execSync } from 'child_process'

function getBackendTarget() {
  if (process.env.VITE_BACKEND_URL) {
    return process.env.VITE_BACKEND_URL
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
