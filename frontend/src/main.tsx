import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { AuthProvider } from './auth/AuthContext'
import { LowBandwidthProvider } from './context/LowBandwidthContext'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <LowBandwidthProvider>
            <App />
          </LowBandwidthProvider>
        </AuthProvider>
      </QueryClientProvider>
    </BrowserRouter>
  </React.StrictMode>,
)

if ('serviceWorker' in navigator && import.meta.env.DEV) {
  // Vite modules must always come from the dev server, never the PWA cache.
  void navigator.serviceWorker.getRegistrations().then(async registrations => {
    await Promise.all(registrations.filter(reg => {
      const worker = reg.active ?? reg.waiting ?? reg.installing
      return worker && new URL(worker.scriptURL).pathname === '/sw.js'
    })
      .map(reg => reg.unregister()))
    const names = await window.caches.keys()
    await Promise.all(names.filter(name => name.startsWith('resqnet-')).map(name => window.caches.delete(name)))
    if (navigator.serviceWorker.controller &&
        new URL(navigator.serviceWorker.controller.scriptURL).pathname === '/sw.js') window.location.reload()
  }).catch(err => console.warn('[sw] development cleanup failed:', err))
}

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js')
      .then((reg) => {
        console.info('[sw] registered with scope:', reg.scope)
      })
      .catch((err) => {
        console.error('[sw] registration failed:', err)
      })
  })
}
