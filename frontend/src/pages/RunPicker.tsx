import { Link } from 'react-router-dom'
import { Btn, Empty, PageHeader, Panel } from '@/components/ui'
import { loadRecent } from '@/lib/recent'

const WHAT: Record<string, { label: string; sub: string }> = {
  analysis: { label: 'Analysis', sub: 'the mission dashboard' },
  activity: { label: 'Activity', sub: 'the pipeline timeline' },
  portfolios: { label: 'Portfolios', sub: 'the portfolio trade-offs' },
  reports: { label: 'Report', sub: 'the printable report' },
}

/** Shown for bare mission routes (/activity, /portfolios, /report(s), /analysis): these pages need a run. */
export default function RunPicker({ seg }: { seg: keyof typeof WHAT }) {
  const w = WHAT[seg]
  const runs = loadRecent()
  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <PageHeader eyebrow={w.label} title="Choose a run" sub={`${w.label} shows ${w.sub} for one mission run. Pick one of your recent runs, or start a new mission.`}
        right={<Link to="/workspace"><Btn variant="primary">Go to Workspace</Btn></Link>} />
      <Panel eyebrow="This browser" title={`Recent runs (${runs.length})`}>
        {runs.length === 0 ? <Empty>No runs started in this browser yet. <Link className="underline" to="/workspace">Open the Workspace</Link> to start a mission or open a demo result.</Empty> : (
          <ul className="divide-y divide-line">
            {runs.map((r) => (
              <li key={r.runId} className="flex flex-wrap items-baseline justify-between gap-2 py-2">
                <Link className="min-w-0 break-words underline decoration-line underline-offset-4 hover:text-ember" to={`/${seg}/${r.runId}`}>{r.title}</Link>
                <span className="mono min-w-0 break-all text-xs text-mute">{r.body}{r.demo ? ' · demo' : ''} · {r.runId} · {new Date(r.at).toLocaleString()}</span>
              </li>))}
          </ul>)}
      </Panel>
    </div>
  )
}
