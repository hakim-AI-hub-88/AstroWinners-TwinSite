import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from '@/App'

vi.mock('@/components/EarthMap', () => ({ default: () => <div data-testid="earth-map-stub" /> }))

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>)
}

describe('route smoke (API offline → demo fixtures)', () => {
  it('landing shows mission sections', async () => {
    renderAt('/')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/analogue|Moon and Mars/i)
    expect(screen.getByText(/Workflow/)).toBeInTheDocument()
  })
  it('workspace has an explicit Run and does not start anything on load', async () => {
    renderAt('/workspace')
    expect(await screen.findByRole('button', { name: /open demo result|run analysis/i })).toBeEnabled()
    expect(screen.queryByText(/Mission in progress/)).not.toBeInTheDocument()
  })
  it('workspace Run → progress → results (G1 flow, demo replay)', async () => {
    sessionStorage.clear()
    renderAt('/workspace')
    const btn = await screen.findByRole('button', { name: /open demo result/i })
    await userEvent.click(btn)
    expect(await screen.findByText(/Mission in progress/)).toBeInTheDocument()
    // fast-forward the replay clock
    const id = [...Array(sessionStorage.length).keys()].map((i) => sessionStorage.key(i)!).find((k) => k.startsWith('twinsite.demo.start.'))!
    sessionStorage.setItem(id, String(Date.now() - 60_000))
    expect(await screen.findByText(/Ranked candidates/, {}, { timeout: 6000 })).toBeInTheDocument()
    expect(screen.getAllByTestId('demo-banner').length).toBeGreaterThan(0)
    expect(screen.getByTestId('strict-status')).toHaveTextContent(/BLOCK/)
  }, 15000)
  it.each([
    ['/analysis/demo-earth-moon', /Ranked candidates/],
    ['/portfolios/demo-earth-moon', /Individual and complementary/],
    ['/activity/demo-earth-moon', /Pipeline timeline/],
    ['/reports/demo-earth-moon', /Source-backed report/],
    ['/data', /Public datasets/],
    ['/docs', /Method, products and restrictions/],
    ['/explorer?run=demo-earth-moon', /Planetary map/],
  ])('%s renders', async (path, text) => {
    renderAt(path)
    expect(await screen.findByText(text, {}, { timeout: 5000 })).toBeInTheDocument()
  })
  it('data explorer shows raw, cleaned, derived and compare for a dataset', async () => {
    renderAt('/data/demo-ds-mobility')
    expect(await screen.findByRole('tab', { name: 'Raw' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('raw_value')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('tab', { name: 'Cleaned' }))
    await waitFor(() => expect(screen.getByText('transformation')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('tab', { name: 'Compare' }))
    expect(await screen.findByLabelText('Compare with')).toBeInTheDocument()
  })
  it('there is no login, account or settings route', async () => {
    renderAt('/')
    for (const t of [/log ?in/i, /sign ?in/i, /settings/i, /account/i, /profile/i]) expect(screen.queryByRole('link', { name: t })).not.toBeInTheDocument()
  })
})
