import { NavLink, Outlet, useMatch, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { cx, Badge } from './ui'
import { useHealth } from '@/lib/hooks'
import { getStatus } from '@/lib/api'
import { isDemoRun } from '@/lib/demo'

const NAV = [
  { to: '/', label: 'Overview', end: true }, { to: '/workspace', label: 'Workspace' }, { to: '/explorer', label: 'Explorer' },
  { to: '/data', label: 'Data Explorer' }, { to: '/docs', label: 'Docs' },
]
const MISSION_TABS = [
  { seg: 'analysis', label: 'Analysis' }, { seg: 'portfolios', label: 'Portfolios' },
  { seg: 'activity', label: 'Activity' }, { seg: 'reports', label: 'Report' },
]

export function Logo() {
  return (
    <span className="flex items-center gap-3">
      <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="11" fill="none" stroke="#efe7d6" strokeWidth="1.2" /><ellipse cx="16" cy="16" rx="15" ry="5.5" transform="rotate(-28 16 16)" fill="none" stroke="#c8642b" strokeWidth="1.4" /><circle cx="26" cy="9" r="2" fill="#c8642b" /></svg>
      <span><span className="block font-serif text-[1.05rem] tracking-[0.28em]">TWINSITE</span><span className="block text-[0.62rem] tracking-wider text-mute">Planetary Analogue Discovery</span></span>
    </span>
  )
}

function MissionBar({ runId }: { runId: string }) {
  const q = useQuery({ queryKey: ['status', runId], queryFn: () => getStatus(runId), retry: 1, enabled: !!runId })
  return (
    <div className="border-b border-line bg-panel/60">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2">
        <div className="text-xs text-mute">Run <span className="mono text-ivory" data-testid="run-id">{runId}</span></div>
        {q.data && <Badge tone={q.data.status === 'failed' ? 'bad' : q.data.status.startsWith('completed') ? 'ok' : 'ember'}>{q.data.status.replace(/_/g, ' ')}</Badge>}
        {isDemoRun(runId) && <Badge tone="warn">Demo · synthetic</Badge>}
        <nav aria-label="Mission sections" className="ml-auto flex gap-1">
          {MISSION_TABS.map((t) => (
            <NavLink key={t.seg} to={`/${t.seg}/${runId}`} className={({ isActive }) => cx('rounded px-3 py-1 text-sm', isActive ? 'bg-panel2 text-ivory' : 'text-ivory-dim hover:text-ivory')}>{t.label}</NavLink>
          ))}
        </nav>
      </div>
    </div>
  )
}

export default function Layout() {
  const health = useHealth()
  const params = useParams()
  const onMission = useMatch('/:seg/:runId')
  const runId = onMission && ['analysis', 'portfolios', 'activity', 'reports'].includes(onMission.params.seg ?? '') ? onMission.params.runId : params.runId
  const live = health.data?.status === 'ready'
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-ember focus:p-2 focus:text-ink">Skip to content</a>
      <header className="border-b border-line bg-ink/95">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <NavLink to="/" aria-label="TwinSite home"><Logo /></NavLink>
          <nav aria-label="Primary" className="flex flex-wrap gap-1">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cx('rounded-full px-4 py-1.5 text-sm', isActive ? 'bg-panel2 text-ivory ring-1 ring-ember/70' : 'text-ivory-dim hover:text-ivory')}>{n.label}</NavLink>
            ))}
          </nav>
          <div className="text-xs text-mute" data-testid="api-mode">
            {health.isLoading ? 'Checking API…' : live ? <>API connected · AI {health.data?.ai_enabled ? 'on' : 'off'}</> : <span className="text-warn">API offline · demo fixtures</span>}
          </div>
        </div>
      </header>
      {runId && <MissionBar runId={runId} />}
      <main id="main" className="flex-1"><Outlet /></main>
      <footer className="border-t border-line px-4 py-6 text-center text-xs text-mute">TwinSite · NASA Space Apps Challenge entry · deterministic scoring engine, no AI in the measurement path · public NASA data, read-only</footer>
    </div>
  )
}
