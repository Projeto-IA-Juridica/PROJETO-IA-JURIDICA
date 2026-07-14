import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Painel interno de vendas — app separado, porta 5199.
// Proxy /api → backend local em dev. Em produção, sirva este build atrás de
// autenticação interna (o backend também exige o tenant de vendas nas rotas).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5199,
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
})
