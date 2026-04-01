import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from './context/AuthContext'
import AppShell from './components/layout/AppShell'
import LoginPage from './pages/LoginPage'
import HubPage from './pages/HubPage'
import ClientDetailPage from './pages/ClientDetailPage'
import CRMPage from './pages/CRMPage'
import RAGPage from './pages/RAGPage'
import AnalyticsPage from './pages/AnalyticsPage'
import ProcessosPage from './pages/ProcessosPage'
import SettingsPage from './pages/SettingsPage'
import OperationsPage from './pages/OperationsPage'
import { Spinner } from './components/ui'

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 0,
      staleTime: 5 * 60_000,
      gcTime: 10 * 60_000,
      refetchOnWindowFocus: false,
    },
  },
})

function ProtectedRoutes() {
  const { isAuthenticated, loading } = useAuth()

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        <Spinner size={24} />
      </div>
    )
  }

  if (!isAuthenticated) return <Navigate to="/login" replace />

  return (
    <AppShell>
      <Routes>
        <Route path="/hub" element={<HubPage />} />
        <Route path="/hub/clientes/:id" element={<ClientDetailPage />} />
        <Route path="/crm" element={<CRMPage />} />
        <Route path="/processos" element={<ProcessosPage />} />
        <Route path="/rag" element={<RAGPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/operations" element={<OperationsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/hub" replace />} />
      </Routes>
    </AppShell>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/*" element={<ProtectedRoutes />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
