import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import VendasPage from './VendasPage'
import './styles.css'

const qc = new QueryClient()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <VendasPage />
    </QueryClientProvider>
  </React.StrictMode>,
)
