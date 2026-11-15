import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from '@/App'

vi.mock('@/components/EarthMap', () => ({ default: () => <div data-testid="earth-map-stub" /> }))

// Production mounts the console at /console (BrowserRouter basename, Vite base '/console/').
function renderUnderConsole(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter basename="/console" initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>)
}

describe('console mounted under /console', () => {
  it('router links carry the /console prefix', () => {
    renderUnderConsole('/console/')
    const primary = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(primary).getByRole('link', { name: 'Workspace' })).toHaveAttribute('href', '/console/workspace')
  })
  it('main-site links stay at the site root', () => {
    renderUnderConsole('/console/workspace')
    const site = screen.getByRole('navigation', { name: 'TwinSite site' })
    for (const [name, href] of [['Home', '/'], ['Auto Mode', '/auto'], ['Data Hub', '/data'], ['Resources', '/resources']]) {
      expect(within(site).getByRole('link', { name })).toHaveAttribute('href', href)
    }
  })
})
