import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// Contracts live one level above /frontend and are imported read-only.
const contracts = path.resolve(__dirname, '../contracts')
const apiTarget = process.env.TWINSITE_API_URL ?? 'http://127.0.0.1:8080'

// Served by Flask (and nginx) under /console/; API calls stay absolute at /v1.
export default defineConfig({
  base: '/console/',
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@contracts': contracts, '@': path.resolve(__dirname, 'src') } },
  server: {
    port: 5173,
    fs: { allow: [path.resolve(__dirname, '..')] },
    proxy: { '/v1': { target: apiTarget, changeOrigin: true } },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    globals: true,
    css: false,
  },
})
