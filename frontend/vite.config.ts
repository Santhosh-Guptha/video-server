import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    watch: {
      usePolling: true
    },
    proxy: {
      '/api': 'http://127.0.0.1:8005',
      '/ws': { target: 'ws://127.0.0.1:8005', ws: true }
    }
  },
  preview: {
    host: '0.0.0.0',
    port: 5173,
    headers: {
      'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'
    },
    proxy: {
      '/api': 'http://127.0.0.1:8005',
      '/ws': { target: 'ws://127.0.0.1:8005', ws: true }
    }
  }
})
