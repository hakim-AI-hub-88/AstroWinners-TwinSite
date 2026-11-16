import { describe, expect, it, vi } from 'vitest'
import { act, render, renderHook, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from '@/App'
import { demoEvidence, demoResult } from '@/lib/demo'
import { gateLabel, useReleaseGate } from '@/lib/release'
import { candidatePins } from '@/lib/overlays'
import { pinLabelShown } from '@/components/PlanetMap'
import { phaseLabel, splitAgentPhase } from '@/components/Progress'
import { missionTitle } from '@/lib/names'

vi.mock('@/components/EarthMap', () => ({ default: () => <div data-testid="earth-map-stub" /> }))

const r = demoResult('demo-earth-moon')
const measured = { ...r, data_status: 'measured' as const }
const blocked = { ...demoEvidence('demo-earth-moon'), release_action: 'BLOCK' as const, blocking_issues: ['C5_INDEPENDENT_REVIEW_REQUIRED'] }

describe('release gate (shared rule)', () => {
  it('labels blocked results with action and issues', () => {
    expect(gateLabel(blocked)).toBe('Unreleased diagnostic values (release gate: BLOCK — C5_INDEPENDENT_REVIEW_REQUIRED)')
    expect(gateLabel(null)).toMatch(/evidence missing/)
  })
  it('hides measured unreleased runs until revealed; reveal is shared per run', () => {
    const a = renderHook(() => useReleaseGate('run-x', measured, blocked))
    const b = renderHook(() => useReleaseGate('run-x', measured, blocked))
    expect(a.result.current.hide).toBe(true)
    act(() => a.result.current.setReveal(true))
    expect(a.result.current.hide).toBe(false)
    expect(b.result.current.revealed).toBe(true)
    act(() => a.result.current.setReveal(false))
    expect(b.result.current.hide).toBe(true)
  })
  it('is not gated while there is no result (no run selected or still loading)', () => {
    const { result } = renderHook(() => useReleaseGate('x', undefined, undefined))
    expect(result.current.gated).toBe(false)
    expect(result.current.hide).toBe(false)
  })
  it('does not hide synthetic runs (already labelled as demo data)', () => {
    const { result } = renderHook(() => useReleaseGate('demo-earth-moon', r, demoEvidence('demo-earth-moon')))
    expect(result.current.gated).toBe(false)
  })
  it('withheld pins carry no rank and are not in rank order', () => {
    const hidden = candidatePins(measured, 'Earth', false)
    expect(hidden.every((p) => p.rank == null && p.eligible === undefined)).toBe(true)
    expect(hidden.map((p) => p.label)).toEqual([...hidden.map((p) => p.label)].sort((x, y) => x.localeCompare(y)))
    // no label is preferred when ranks are withheld (unless there are at most three pins)
    if (hidden.length > 3) expect(hidden.some((p) => pinLabelShown(p, hidden))).toBe(false)
  })
})

describe('agent event phases', () => {
  it('splits the agent logical phase off the summary', () => {
    expect(splitAgentPhase('[P20] A02 Visual Interpreter: ai')).toEqual({ agentPhase: 'P20', text: 'A02 Visual Interpreter: ai' })
    expect(splitAgentPhase('[DEMO REPLAY] P10 acquire').agentPhase).toBeNull()
    expect(phaseLabel({ phase: 'P80', summary: '[P10] A01 Source Curator' })).toBe('P80 · agent P10')
    expect(phaseLabel({ phase: 'P30', summary: 'Engine running' })).toBe('P30')
  })
})

describe('mission naming', () => {
  it('match missions are titled by their target', () => {
    const m = { ...r, mission_id: 'match-abc' }
    const id = m.target_profiles[0]?.location.id ?? m.scope.locations.find((l) => l.body !== 'Earth')!.id
    expect(missionTitle(m, (x) => (x === id ? 'Jezero crater' : x))).toMatch(/^Earth analogs for Jezero crater/)
    expect(missionTitle(r, (x) => x)).toBe(`Mission ${r.mission_id}`)
  })
})

describe('bare mission routes', () => {
  it.each(['/activity', '/portfolios', '/report', '/reports'])('%s offers recent runs and the workspace', async (path) => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>)
    expect(await screen.findByRole('heading', { name: 'Choose a run' })).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /workspace/i }).length).toBeGreaterThan(0)
    expect(screen.queryByText('Page not found')).not.toBeInTheDocument()
  })
})
