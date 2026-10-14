import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/v1': { target: 'http://127.0.0.1:8765', changeOrigin: true },
    },
  },
  build: { outDir: '../static/dist', emptyOutDir: true },
})
