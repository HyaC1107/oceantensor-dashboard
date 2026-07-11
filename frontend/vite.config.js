import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// base: 배포 시 서브패스(/app/)로 서빙 — Grafana(/)와 같은 도메인에 공존.
// 로컬 dev/기본 빌드는 '/' 유지. 배포 빌드는 VITE_BASE=/app/ 로 지정.
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  plugins: [react(), tailwindcss()],
  server: {
    watch: { usePolling: true, interval: 300 },
  },
})
