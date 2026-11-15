import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Badge, Btn, DemoBanner, Empty, Meter, Notice, PageHeader, Panel, Scroll, Spinner, Tabs } from '@/components/ui'
import { EventLog, PhaseTimeline } from '@/components/Progress'
import { useEvents, useEvidence, useResult, useStatus } from '@/lib/hooks'
import { TERMINAL, type ReleaseEvidence, type MissionResult } from '@/lib/types'
import { isReleased, prosCons, qaCounts, rankSites, stability, timeBasis, unresolvedGaps } from '@/lib/analysis'
import { idx, money, days, ts } from '@/lib/format'
import { isDemoRun } from '@/lib/demo'

type Tab = 'ranking' | 'features' | 'confidence' | 'temporal' | 'gaps'

export default function Analysis() {
  const { runId = '' } = useParams()
  const status = useStatus(runId)
  const terminal = !!status.data && TERMINAL.includes(status.data.status)
  const { events, error: evErr } = useEvents(runId, !terminal)
  const ok = status.data?.status === 'completed' || status.data?.status === 'completed_with_limits'
  const result = useResult(runId, ok)
  const evidence = useEvidence(runId, ok)
  const demo = isDemoRun(runId)

  if (status.isLoading) return <Spinner label="Loading run" />
  if (status.isError) return <div className="mx-auto max-w-3xl px-4 py-10"><Notice tone="bad" title="Run not found or API unreachable">{(status.error as Error).message}. <Link className="underline" to="/workspace">Start a new mission</Link>.</Notice></div>
  const st = status.data!

  if (!terminal) {
    return (
      <>
        {demo && <DemoBanner>Lifecycle below is a labelled replay; nothing is being computed.</DemoBanner>}
        <div className="mx-auto max-w-5xl px-4 py-8">
          <PageHeader eyebrow="Mission in progress" title={<>Running <span className="mono text-2xl text-ember">{runId}</span></>} sub={`Status: ${st.status.replace(/_/g, ' ')} · attempt ${st.attempt}. Progress is the list of real events emitted by the worker — no estimated percentage.`} />
          <div className="grid gap-5 lg:grid-cols-[22rem_1fr]">
            <Panel eyebrow="P00 – P90" title="Pipeline"><PhaseTimeline events={events} /></Panel>
            <Panel eyebrow="Event stream" title="Live events">{evErr && <Notice tone="warn" title="Event polling issue">{evErr} — retrying.</Notice>}<EventLog events={events} /></Panel>
          </div>
        </div>
      </>
    )
  }
  if (!ok) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-10">
        <Notice tone="bad" title={`Run ${st.status}`}>{st.error ?? 'No error detail was published.'} No result exists for this run. <Link className="underline" to={`/activity/${runId}`}>See activity</Link> · <Link className="underline" to="/workspace">New mission</Link></Notice>
      </div>
    )
  }
  if (result.isLoading || evidence.isLoading) return <Spinner label="Loading result and evidence" />
  if (result.isError) return <div className="mx-auto max-w-3xl px-4 py-10"><Notice tone="bad" title="Result unavailable">{(result.error as Error).message}</Notice></div>
  return <Results runId={runId} r={result.data!} ev={evidence.data ?? null} evErr={evidence.isError ? (evidence.error as Error).message : null} demo={demo} />
}

function Results({ runId, r, ev, evErr, demo }: { runId: string; r: MissionResult; ev: ReleaseEvidence | null; evErr: string | null; demo: boolean }) {
  const [tab, setTab] = useState<Tab>('ranking')
  const [reveal, setReveal] = useState(false)
  const ranked = useMemo(() => rankSites(r.sites), [r])
  const released = isReleased(r, ev)
  const synthetic = r.data_status === 'synthetic'
  const hide = !synthetic && !released && !reveal
  const gaps = unresolvedGaps(r, ev)
  const targets = r.target_profiles.map((t) => `${t.body} · ${t.location.id}`)
  return (
    <>
      {(demo || synthetic) && <DemoBanner>{synthetic ? 'All values and costs in this result are synthetic; scientific release is BLOCKED by design.' : 'Demo run.'}</DemoBanner>}
      <div className="mx-auto max-w-7xl px-4 py-8">
        <PageHeader eyebrow="Analysis results" title={<>Mission <span className="text-ember">{r.mission_id}</span></>}
          sub={synthetic ? "Earth analogue candidates ranked by feature similarity to the selected target regions. Values are synthetic." : "Earth analogue candidates ranked by measured feature similarity to the selected target regions."}
          right={<div className="flex gap-2"><Link to={`/portfolios/${runId}`}><Btn>Portfolios</Btn></Link><Link to={`/explorer?run=${runId}`}><Btn>Open on map</Btn></Link><Link to={`/reports/${runId}`}><Btn variant="primary">Report</Btn></Link></div>} />

        <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="context-strip">
          <Ctx k="Run ID" v={<span className="mono">{runId}</span>} />
          <Ctx k="Active target" v={targets.join('; ') || '—'} />
          <Ctx k="Phase" v={r.status === 'completed' ? 'P90 · published' : 'Finished — no feasible portfolio'} />
          <Ctx k="Data snapshot" v={<span className="mono text-xs">{ev?.source_snapshot_id ?? 'unavailable'}</span>} />
          <Ctx k="Time basis" v={timeBasis(ev)} />
        </div>

        <StrictBanner r={r} ev={ev} evErr={evErr} released={released} />

        {hide ? (
          <div className="mt-5"><Notice tone="bad" title="Scores withheld">This measured run has not passed the release gate, so no ranking is presented as a finding. <button className="underline" onClick={() => setReveal(true)}>Show unreleased diagnostic values</button></Notice></div>
        ) : (
          <div className="mt-5 space-y-5">
            {reveal && !released && !synthetic && <Notice tone="bad" title="DIAGNOSTIC — unreleased values. Do not cite.">Release gate: {ev?.release_action ?? 'evidence missing'}.</Notice>}
            <Tabs<Tab> label="Analysis sections" value={tab} onChange={setTab} tabs={[
              { id: 'ranking', label: 'Ranked candidates' }, { id: 'features', label: 'Feature comparison' }, { id: 'confidence', label: 'Confidence' },
              { id: 'temporal', label: 'Temporal' }, { id: 'gaps', label: `Gaps (${gaps.length})` }]} />
            {tab === 'ranking' && <Ranking ranked={ranked} r={r} />}
            {tab === 'features' && <Features r={r} ranked={ranked} />}
            {tab === 'confidence' && <Confidence r={r} ev={ev} />}
            {tab === 'temporal' && <Temporal ev={ev} />}
            {tab === 'gaps' && <Gaps gaps={gaps} limitations={r.limitations} />}
          </div>
        )}
      </div>
    </>
  )
}

const Ctx = ({ k, v }: { k: string; v: React.ReactNode }) => (
  <div className="rounded-md border border-line bg-panel px-3 py-2"><div className="eyebrow !text-mute">{k}</div><div className="mt-1 text-sm">{v}</div></div>
)

function StrictBanner({ r, ev, evErr, released }: { r: MissionResult; ev: ReleaseEvidence | null; evErr: string | null; released: boolean }) {
  if (!ev) return <Notice tone="bad" title="Evidence unavailable — never implicit approval">{evErr ?? 'The release-evidence sidecar could not be loaded.'} Measured claims are not presented.</Notice>
  const tone = released ? 'ok' : 'bad'
  return (
    <div data-testid="strict-status" className={`rounded-md border px-4 py-3 ${released ? 'border-ok/40 bg-ok/10' : 'border-bad/50 bg-bad/10'}`}>
      <div className="flex flex-wrap items-center gap-3">
        <span className="eyebrow">Strict gate</span><Badge tone={tone}>{ev.strict_gate_status.replace('_', ' ')}</Badge>
        <span className="eyebrow">Release</span><Badge tone={tone}>{ev.release_action.replace('_', ' ')}</Badge>
        <Badge tone={r.data_status === 'synthetic' ? 'warn' : 'ok'}>{r.data_status}</Badge>
        <span className="text-xs text-mute">QA gate {ev.qa_gate_id} v{ev.qa_gate_version} · weights {ev.weights_version}</span>
      </div>
      {ev.blocking_issues.length > 0 && <div className="mt-2 text-sm text-ivory-dim">Blocking: {ev.blocking_issues.join(', ')}</div>}
    </div>
  )
}

function Ranking({ ranked, r }: { ranked: ReturnType<typeof rankSites>; r: MissionResult }) {
  return (
    <div className="space-y-4">
      {r.status === 'no_feasible_portfolio' && <Notice title="No feasible portfolio">Constraints could not be satisfied by any eligible combination. Candidates are still listed below.</Notice>}
      {ranked.map((s) => {
        const { pros, cons } = prosCons(s)
        return (
          <Panel key={s.id} className={s.eligible ? '' : 'opacity-80'}
            title={<span>{s.rank ? <span className="mr-3 text-ember">#{s.rank}</span> : <Badge tone="bad">Not eligible</Badge>} {s.name}</span>}
            action={<div className="text-right text-xs text-mute"><div>{s.body} · {s.latitude.toFixed(2)}°, {s.longitude.toFixed(2)}°</div><div className="mono">{s.coordinate_system}</div></div>}>
            <div className="grid gap-4 md:grid-cols-[16rem_1fr_1fr]">
              <dl className="space-y-2 text-sm">
                <div><dt className="eyebrow !text-mute">Observed similarity (0–1 index)</dt><dd><Meter value={s.observed_similarity} label="similarity" /></dd></div>
                <div><dt className="eyebrow !text-mute">Utility bounds (missing-data)</dt><dd className="mono text-xs">{idx(s.lower_utility)} – {idx(s.upper_utility)}</dd></div>
                <div><dt className="eyebrow !text-mute">Evidence coverage</dt><dd><Meter value={s.coverage} label="coverage" /></dd></div>
                <div className="flex gap-2"><Badge tone={s.access === 'pass' ? 'ok' : s.access === 'fail' ? 'bad' : 'warn'}>access {s.access}</Badge></div>
                <div className="text-xs text-mute">Cost {money(s.cost)} · Effort {days(s.days)} <span className="block">(as provided by you)</span></div>
              </dl>
              <div><h3 className="mb-1 text-sm text-ok">Strengths</h3>{pros.length ? <ul className="list-disc space-y-1 pl-5 text-sm text-ivory-dim">{pros.map((p, i) => <li key={i}>{p.text}</li>)}</ul> : <p className="text-sm text-mute">None above the 0.80 similarity mark.</p>}</div>
              <div><h3 className="mb-1 text-sm text-warn">Weaknesses &amp; gaps</h3>{cons.length ? <ul className="list-disc space-y-1 pl-5 text-sm text-ivory-dim">{cons.map((p, i) => <li key={i}>{p.text}</li>)}</ul> : <p className="text-sm text-mute">None recorded.</p>}</div>
            </div>
          </Panel>
        )
      })}
      <p className="text-xs text-mute">Strength = similarity ≥ 0.80; weakness = similarity &lt; 0.50, missing measurement, failed constraint or unknown access. These marks are display conventions, not scientific thresholds.</p>
    </div>
  )
}

function Features({ r, ranked }: { r: MissionResult; ranked: ReturnType<typeof rankSites> }) {
  const [sid, setSid] = useState(ranked[0]?.id ?? '')
  const site = ranked.find((s) => s.id === sid) ?? ranked[0]
  if (!site) return <Empty>No candidates.</Empty>
  const rows = Object.entries(site.contributions)
  return (
    <Panel eyebrow="Measured feature comparison" title="Candidate vs target, feature by feature"
      action={<div className="w-56"><label className="fld" htmlFor="site-sel">Candidate</label><select id="site-sel" value={sid} onChange={(e) => setSid(e.target.value)}>{ranked.map((s) => <option key={s.id} value={s.id}>{s.rank ? `#${s.rank} ` : ''}{s.name}</option>)}</select></div>}>
      {rows.length === 0 ? <Empty>This candidate has no comparable measurements.</Empty> : (
        <Scroll><table className="tbl">
          <caption className="sr-only">Feature comparison for {site.name}</caption>
          <thead><tr><th>Comparison</th><th>Candidate value</th><th>Target value</th><th>Unit</th><th>Similarity</th><th>Weighted</th><th>Weight</th><th>Source IDs</th></tr></thead>
          <tbody>{rows.map(([k, c]) => (
            <tr key={k}><td className="mono">{k}</td><td className="mono">{c.value}</td><td className="mono">{c.target_value}</td><td className="mono text-ivory-dim">{c.unit}</td>
              <td><Meter value={c.similarity} /></td><td className="mono">{idx(c.weighted_contribution)}</td><td className="mono">{idx(r.weights[k] ?? r.weights[c.feature_id])}</td>
              <td className="mono text-xs text-mute">{c.source_id}<br />→ {c.target_source_id ?? 'no target source'}</td></tr>))}</tbody>
        </table></Scroll>)}
      {site.missing.length > 0 && <p className="mt-3 text-sm text-warn">Missing: {site.missing.join(', ')} — lower coverage, not zero similarity.</p>}
    </Panel>
  )
}

function Confidence({ r, ev }: { r: MissionResult; ev: ReleaseEvidence | null }) {
  const qa = qaCounts(ev), stab = stability(r)
  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Panel eyebrow="1 · QA" title="Quality assurance">
        {ev ? <dl className="space-y-2 text-sm">
          <div className="flex justify-between"><dt className="text-mute">Strict gate</dt><dd>{ev.strict_gate_status}</dd></div>
          <div className="flex justify-between"><dt className="text-mute">Release action</dt><dd>{ev.release_action}</dd></div>
          <div><dt className="text-mute">Observation QA verdicts</dt><dd className="mt-1 flex flex-wrap gap-1">{Object.keys(qa).length ? Object.entries(qa).map(([k, v]) => <Badge key={k} tone={k === 'ACCEPT' ? 'ok' : 'warn'}>{k} × {v}</Badge>) : <span className="text-mute">no observations attested</span>}</dd></div>
        </dl> : <Empty>Evidence unavailable.</Empty>}
      </Panel>
      <Panel eyebrow="2 · Coverage" title="Evidence coverage">
        <dl className="space-y-2 text-sm">
          <div className="flex items-center justify-between"><dt className="text-mute">Run evidence coverage</dt><dd><Meter value={ev?.evidence_coverage ?? null} /></dd></div>
          <div className="flex items-center justify-between"><dt className="text-mute">Minimum across portfolios</dt><dd className="mono">{idx(Math.min(...r.portfolios.map((p) => p.minimum_evidence_coverage), 1))}</dd></div>
          <div className="text-xs text-mute">Per-candidate coverage is on the ranking tab. Lower coverage is not zero similarity.</div>
        </dl>
      </Panel>
      <Panel eyebrow="3 · Stability" title="Weight sensitivity">
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between"><dt className="text-mute">Scenarios</dt><dd className="mono">{stab.scenarios} (seed {r.sensitivity.seed})</dd></div>
          <div className="flex justify-between"><dt className="text-mute">Weight factor range</dt><dd className="mono">×{r.sensitivity.weight_factor_range.join(' – ×')}</dd></div>
          <div className="flex justify-between"><dt className="text-mute">Top portfolio held</dt><dd className="mono">{stab.top ? `${stab.top.ids} · ${stab.top.count}/${stab.scenarios}` : '—'}</dd></div>
          <div className="flex justify-between"><dt className="text-mute">Infeasible scenarios</dt><dd className="mono">{stab.infeasible}</dd></div>
        </dl>
      </Panel>
      <div className="md:col-span-3"><Notice tone="mute" title="Confidence is three separate readings, never one blended number.">QA, coverage and stability are shown independently so a strong value in one cannot hide a weakness in another.</Notice></div>
    </div>
  )
}

function Temporal({ ev }: { ev: ReleaseEvidence | null }) {
  const o = ev?.observations ?? []
  if (!ev) return <Empty>Evidence unavailable.</Empty>
  if (!o.length) return <Empty>No observation periods are attested in this run (synthetic runs carry none). Temporal tabs fill from the evidence sidecar for measured runs.</Empty>
  return (
    <Panel eyebrow="Time basis" title="Observation periods and resolution"><Scroll><table className="tbl">
      <thead><tr><th>Site</th><th>Feature</th><th>Body</th><th>Period</th><th>Spatial res.</th><th>Analysis scale</th><th>Product</th><th>QA</th></tr></thead>
      <tbody>{o.map((x) => <tr key={x.evidence_id}><td className="mono">{x.site_id}</td><td className="mono">{x.feature_id}</td><td>{x.body}</td>
        <td className="mono text-xs whitespace-nowrap">{ts(x.observation_period.start).slice(0, 10)} → {ts(x.observation_period.end).slice(0, 10)}</td>
        <td className="mono">{x.spatial_resolution_m ?? '—'} m</td><td className="mono">{x.analysis_scale_m ?? '—'} m</td><td className="mono text-xs">{x.source_product}</td><td><Badge tone={x.qa_status === 'ACCEPT' ? 'ok' : 'warn'}>{x.qa_status}</Badge></td></tr>)}</tbody>
    </table></Scroll></Panel>
  )
}

function Gaps({ gaps, limitations }: { gaps: string[]; limitations: string[] }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Panel eyebrow="Unresolved" title="Gaps and unknowns">{gaps.length ? <ul className="list-disc space-y-1 pl-5 text-sm">{gaps.map((g, i) => <li key={i}>{g}</li>)}</ul> : <p className="text-sm text-mute">No unresolved gaps recorded.</p>}</Panel>
      <Panel eyebrow="Method" title="Limitations of this result"><ul className="list-disc space-y-1 pl-5 text-sm text-ivory-dim">{limitations.map((g, i) => <li key={i}>{g}</li>)}</ul></Panel>
    </div>
  )
}
