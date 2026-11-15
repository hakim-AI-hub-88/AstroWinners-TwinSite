import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Badge, Btn, DemoBanner, Empty, Meter, Notice, PageHeader, Panel, Scroll, Spinner, Tabs } from '@/components/ui'
import { TradeoffChart } from '@/components/Scatter'
import { useEvidence, useResult, useStatus } from '@/lib/hooks'
import { postAlternatives, ApiError } from '@/lib/api'
import { isDemoRun } from '@/lib/demo'
import { idx, money, days } from '@/lib/format'
import type { Portfolio } from '@/lib/types'

type K = 'standalone' | 'combined'
export default function Portfolios() {
  const { runId = '' } = useParams()
  const nav = useNavigate()
  const status = useStatus(runId)
  const ok = status.data?.status === 'completed' || status.data?.status === 'completed_with_limits'
  const result = useResult(runId, ok)
  const evidence = useEvidence(runId, ok)
  const [kind, setKind] = useState<K>('combined')
  const [sel, setSel] = useState<number | null>(0)
  const [msg, setMsg] = useState<string | null>(null)
  const alt = useMutation({
    mutationFn: (p: Portfolio) => postAlternatives(runId, { schema_version: '1.0', source_snapshot_id: evidence.data!.source_snapshot_id, exclude_portfolios: [p.site_ids] }, crypto.randomUUID()),
    onSuccess: (a) => nav(`/analysis/${a.run_id}`),
    onError: (e) => setMsg(e instanceof ApiError && e.status === 501 ? 'Alternatives endpoint is not implemented yet (501).' : (e as Error).message),
  })
  if (status.isLoading || (ok && result.isLoading)) return <Spinner />
  if (!ok || !result.data) return <div className="mx-auto max-w-3xl px-4 py-10"><Notice tone="warn" title="Portfolios are available after the run completes">Current status: {status.data?.status ?? 'unknown'}. <Link className="underline" to={`/analysis/${runId}`}>Back to progress</Link></Notice></div>
  const r = result.data
  const names = Object.fromEntries(r.sites.map((s) => [s.id, s.name]))
  const list = kind === 'standalone' ? r.standalone_portfolios : r.combined_portfolios
  const chosen = sel != null ? list[sel] : null
  const demo = isDemoRun(runId)
  return (
    <>
      {(demo || r.data_status === 'synthetic') && <DemoBanner>Portfolio objectives, costs and days are synthetic scenario inputs.</DemoBanner>}
      <div className="mx-auto max-w-7xl px-4 py-8">
        <PageHeader eyebrow="Portfolios" title="Individual and complementary candidates"
          sub={`Standalone portfolios rank sites on their own; combined portfolios add complementary sites within the site-count and cost/effort limits you supplied. ${r.feasible_portfolio_count} feasible portfolios found.`} />
        {r.status === 'no_feasible_portfolio' ? <Notice title="No feasible portfolio">
          No eligible combination satisfies the mission constraints. This is a valid outcome, not an error.
          {r.sites.some((s) => !s.eligible) && <ul className="mt-2 list-disc pl-5 text-sm">{r.sites.filter((s) => !s.eligible).map((s) => <li key={s.id}><span className="text-ivory">{s.name}</span>: {s.failures.join('; ') || 'not eligible'}</li>)}</ul>}
        </Notice> : (
          <div className="space-y-5">
            <Tabs<K> label="Portfolio type" value={kind} onChange={(k) => { setKind(k); setSel(0) }} tabs={[{ id: 'combined', label: `Complementary (${r.combined_portfolios.length})` }, { id: 'standalone', label: `Individual (${r.standalone_portfolios.length})` }]} />
            {list.length === 0 ? <Empty>No {kind} portfolios in this run{r.portfolio_mode !== 'both' && r.portfolio_mode !== kind ? ` (portfolio mode was “${r.portfolio_mode}”)` : ''}.</Empty> : (
              <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
                <Panel eyebrow="Trade-off" title="Objective vs cost"><TradeoffChart items={list} names={names} selected={sel} onSelect={setSel} />
                  <p className="text-xs text-mute">Filled = combined, outline = individual. Cost is only what you entered; “no cost” means none was provided.</p></Panel>
                <Panel eyebrow="Selected" title={chosen ? chosen.site_ids.map((s) => names[s] ?? s).join(' + ') : 'Select a portfolio'}>
                  {chosen && <div className="space-y-3 text-sm">
                    <div className="grid grid-cols-2 gap-2"><Stat k="Objective" v={idx(chosen.objective)} /><Stat k="Test-coverage utility" v={idx(chosen.test_coverage_utility)} /><Stat k="Redundancy" v={idx(chosen.redundancy)} /><Stat k="Min evidence coverage" v={idx(chosen.minimum_evidence_coverage)} /><Stat k="Cost" v={money(chosen.cost)} /><Stat k="Effort" v={days(chosen.days)} /></div>
                    <div><div className="eyebrow !text-mute mb-1">Dimension coverage</div>{Object.entries(chosen.dimension_coverage).map(([k, v]) => <div key={k} className="flex items-center justify-between py-0.5"><span className="mono text-xs">{k}</span><Meter value={v} /></div>)}</div>
                    <Badge tone={chosen.operational_status === 'pass' ? 'ok' : 'warn'}>operations {chosen.operational_status}</Badge>
                    <div className="pt-2"><Btn disabled={demo || !evidence.data || alt.isPending} onClick={() => { setMsg(null); alt.mutate(chosen) }}>Find alternatives excluding this</Btn>
                      {demo && <p className="mt-1 text-xs text-mute">Disabled in demo mode.</p>}{msg && <p className="mt-1 text-xs text-bad">{msg}</p>}</div>
                  </div>}
                </Panel>
              </div>)}
            <Panel eyebrow="All portfolios" title="Comparison table"><Scroll><table className="tbl">
              <thead><tr><th>Sites</th><th>Type</th><th>Objective</th><th>Coverage utility</th><th>Redundancy</th><th>Cost</th><th>Effort</th><th>Ops</th></tr></thead>
              <tbody>{list.map((p, i) => <tr key={i} className={sel === i ? 'bg-ember/10' : ''}><td><button className="text-left underline decoration-line underline-offset-4 hover:text-ember" onClick={() => setSel(i)}>{p.site_ids.map((s) => names[s] ?? s).join(' + ')}</button></td><td>{p.kind}</td><td className="mono">{idx(p.objective)}</td><td className="mono">{idx(p.test_coverage_utility)}</td><td className="mono">{idx(p.redundancy)}</td><td className="mono">{money(p.cost)}</td><td className="mono">{days(p.days)}</td><td>{p.operational_status}</td></tr>)}</tbody>
            </table></Scroll></Panel>
            <Panel eyebrow="Alternatives" title="If your first choice is unavailable"><p className="text-sm text-ivory-dim">Alternatives reuse the same cached source snapshot ({evidence.data?.source_snapshot_id ?? 'unavailable'}) with an explicit exclusion set — no new NASA download. Sensitivity: the top portfolio held in {Object.values(r.sensitivity.top_portfolio_counts).sort((a, b) => b - a)[0] ?? 0} of {r.sensitivity.scenarios} weight scenarios.</p></Panel>
          </div>)}
      </div>
    </>
  )
}
const Stat = ({ k, v }: { k: string; v: string }) => <div className="rounded border border-line px-2 py-1.5"><div className="eyebrow !text-mute !text-[0.6rem]">{k}</div><div className="mono">{v}</div></div>
