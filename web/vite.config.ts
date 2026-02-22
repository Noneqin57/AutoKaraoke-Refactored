import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:18632',
        changeOrigin: true,
      },
      '/api/task/ws': {
        target: 'ws://127.0.0.1:18632',
        ws: true,
      },
      '/api/model/ws': {
        target: 'ws://127.0.0.1:18632',
        ws: true,
      },
      '/api/msst/ws': {
        target: 'ws://127.0.0.1:18632',
        ws: true,
      },
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  }
})
