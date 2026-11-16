import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './index.css'

// Retry only transient failures (network / 5xx); a 4xx answer is final and shown immediately.
// The console is mounted at /console by the Flask site (Vite base '/console/').
const retry = (count: number, e: unknown) => count < 2 && !((e as { status?: number })?.status && (e as { status: number }).status < 500)
const qc = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry } } })
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><QueryClientProvider client={qc}><BrowserRouter basename="/console"><App /></BrowserRouter></QueryClientProvider></React.StrictMode>,
)
