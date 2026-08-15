import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// The API is proxied under /api rather than called directly on port 8000.
//
// This is what makes HttpOnly + SameSite=Strict session cookies possible. A
// cookie set by 127.0.0.1:8000 is a *different site* from localhost:5173, so
// SameSite=Strict would stop the browser ever sending it and every
// authenticated request would fail. The alternative -- SameSite=None -- would
// re-open the CSRF hole the strict cookie exists to close, and would demand
// HTTPS in development too.
//
// Proxying makes the browser see a single origin, so the cookie is first-party,
// Strict works, and CORS stops being involved at all.
//
// In production there is no Vite: serve the built web_app/dist from the same
// origin as the API (the backend mounts it automatically when it exists), which
// gives the same property without a proxy.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
