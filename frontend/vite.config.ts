import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'

const backend = process.env.STEWARD_BACKEND ?? 'http://localhost:8095'

// The app runs behind Home Assistant ingress under an unknown path prefix:
// relative base, hash router, relative API URLs.
export default defineConfig({
  base: './',
  plugins: [vue(), vuetify({ autoImport: true })],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    outDir: fileURLToPath(new URL('../server/steward_server/static', import.meta.url)),
    emptyOutDir: true,
    assetsDir: 'assets',
    chunkSizeWarningLimit: 1200,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: backend, changeOrigin: true, ws: true },
    },
  },
})
