import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import HubPage from './pages/HubPage'
import DevBanner from './components/DevBanner'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <HubPage />
      <DevBanner />
    </QueryClientProvider>
  )
}
