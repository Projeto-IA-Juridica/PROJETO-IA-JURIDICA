import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiProxyTarget = env.VITE_API_PROXY_TARGET ?? 'https://projeto-ia-juridica-production.up.railway.app'

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: apiProxyTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
          secure: true,
          configure: (proxy, _options) => {
            proxy.on('error', (err, _req, _res) => {
              console.log('[Proxy Error]', err)
            })
            proxy.on('proxyReq', (proxyReq, req, _res) => {
              console.log(`[Proxy Request] ${req.method} ${req.url} -> ${proxyReq.path}`)
            })
            proxy.on('proxyRes', (proxyRes, req, _res) => {
              console.log(`[Proxy Response] ${proxyRes.statusCode} ${req.url}`)
            })
          },
        },
      },
    },
  }
})
