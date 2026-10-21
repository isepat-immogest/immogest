/// <reference types="vitest" />
import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// URL du backend Django (changer si le port 8000 est occupé : DJANGO_URL=http://127.0.0.1:8010 npm run dev).
const DJANGO_URL = process.env.DJANGO_URL ?? 'http://127.0.0.1:8000'

// L'application est servie par Django sous /app/ (même origine => cookies de session + CSRF).
export default defineConfig({
  base: '/app/',
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: DJANGO_URL, changeOrigin: true },
      '/media': { target: DJANGO_URL, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts'],
        },
      },
    },
  },
  test: { environment: 'jsdom', globals: true, setupFiles: ['./src/test-setup.ts'] },
})
