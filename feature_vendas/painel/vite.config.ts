import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Painel interno de vendas — app separado, porta 5199.
//
// NÃO precisa de deploy: rode local e aponte para a API que você quiser.
// É ferramenta interna de 2–3 pessoas; publicar só criaria uma superfície de
// login exposta à toa. O backend ainda exige JWT do tenant de vendas nas rotas.
//
//   local:      npm run dev
//   contra prod: VITE_API_TARGET=https://sua-api.railway.app npm run dev
const alvo = process.env.VITE_API_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5199,
    proxy: { '/api': { target: alvo, changeOrigin: true } },
  },
})
