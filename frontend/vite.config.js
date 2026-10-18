import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
export default defineConfig({
  resolve: {
    alias: {
      '@framework': fileURLToPath(new URL('./src', import.meta.url)),
      'vue': fileURLToPath(new URL('./node_modules/vue/dist/vue.runtime.esm-bundler.js', import.meta.url)),
      '@iconify/vue': fileURLToPath(new URL('./node_modules/@iconify/vue/dist/iconify.mjs', import.meta.url)),
    },
    dedupe: ['vue'],
  },
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/v1': { target: 'http://127.0.0.1:8765', changeOrigin: true },
    },
  },
  build: { outDir: '../static/dist', emptyOutDir: true, manifest: true },
})
