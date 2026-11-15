import { lazy, Suspense, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Badge, Btn, Empty, Meter, Notice, Panel, Scroll, Spinner, Tabs } from '@/components/ui'
import PlanetMap from '@/components/PlanetMap'
import { EventLog, PhaseTimeline } from '@/components/Progress'
import { AgentActivity } from '@/components/AgentActivity'
import { ApiError, getAgents, getReportHtml, reportUrl } from '@/lib/api'
import { useExplorableIds } from '@/lib/hooks'
import { candidatePins, footprintsFor, targetBodies } from '@/lib/overlays'
import { observationsCsv, safeHref } from '@/lib/exports'
import { download, idx, money, days, short, toCsv } from '@/lib/format'
import { rankSites, stability } from '@/lib/analysis'
import { CRS } from '@/lib/regions'
import type { Body, MissionResult, Portfolio, ProgressEvent, ReleaseEvidence } from '@/lib/types'
const EarthMap = lazy(() => import('@/components/EarthMap'))
const PlanetGlobe = lazy(() => import('@/components/PlanetGlobe'))

const LAYERS = { pins: true, footprints: true, graticule: true, basemap: true }

export const SECTIONS = [
  { id: 'maps', label: 'Maps' }, { id: 'results', label: 'Results' }, { id: 'portfolios', label: 'Portfolios' },
  { id: 'data', label: 'Data & sources' }, { id: 'report', label: 'Report & downloads' }, { id: 'logs', label: 'Mission logs' },
] as const

export function SectionNav() {
  return (
    <nav aria-label="Mission dashboard sections" className="sticky top-0 z-10 -mx-4 mb-5 flex flex-wrap gap-1 border-b border-line bg-ink/90 px-4 py-2 backdrop-blur">
      {SECTIONS.map((s) => <a key={s.id} href={`#${s.id}`} className="rounded-full px-3 py-1 text-sm text-ivory-dim hover:bg-ember/10 hover:text-ivory">{s.label}</a>)}
    </nav>
  )
}

/** Target body map (2D / 3D for Moon and Mars) beside an Earth map of the candidate sites. */
export function MissionMaps({ r, showRanks }: { r: MissionResult; showRanks: boolean }) {
  const bodies = useMemo(() => targetBodies(r), [r])
  const [target, setTarget] = useState<Body | null>(bodies[0] ?? null)
  const [mode, setMode] = useState<'2d' | 'globe'>('2d')
  const tb = target && bodies.includes(target) ? target : bodies[0] ?? null
  const tFootprints = useMemo(() => (tb ? footprintsFor(r, tb) : []), [r, tb])
  const tPins = useMemo(() => (tb ? candidatePins(r, tb, showRanks) : []), [r, tb, showRanks])
  const ePins = useMemo(() => candidatePins(r, 'Earth', showRanks), [r, showRanks])
  const eFootprints = useMemo(() => footprintsFor(r, 'Earth'), [r])
  const eligible = r.sites.filter((s) => s.body === 'Earth' && s.eligible).length
  const ineligible = r.sites.filter((s) => s.body === 'Earth' && !s.eligible).length
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Panel eyebrow="Target" title={tb ? `${tb} target area` : 'Target area'}
        action={<div className="flex flex-wrap justify-end gap-2">
          {bodies.length > 1 && <Tabs<Body> label="Target body" value={tb ?? bodies[0]} onChange={setTarget} tabs={bodies.map((b) => ({ id: b, label: b }))} />}
          {tb && tb !== 'Earth' && <Tabs<'2d' | 'globe'> label={`${tb} view`} value={mode} onChange={setMode} tabs={[{ id: '2d', label: '2D' }, { id: 'globe', label: '3D' }]} />}
        </div>}>
        {!tb ? <Empty>This result has no target location.</Empty>
          : tb === 'Earth' ? <Suspense fallback={<Spinner label="Loading Earth map" />}><EarthMap pins={tPins} footprints={tFootprints} globe={false} layers={LAYERS} /></Suspense>
          : mode === 'globe' ? <Suspense fallback={<Spinner label={`Loading ${tb} globe`} />}><PlanetGlobe body={tb} pins={tPins} footprints={tFootprints} layers={LAYERS} /></Suspense>
          : <PlanetMap body={tb} pins={tPins} footprints={tFootprints} layers={LAYERS} />}
        {tb && <ul className="mt-2 space-y-0.5 text-xs text-ivory-dim">{tFootprints.map((f) => <li key={f.id}><span className="mono">{f.label}</span> · bbox [{f.bbox.map((v) => v.toFixed(3)).join(', ')}] · <span className="mono">{CRS[tb]}</span></li>)}</ul>}
      </Panel>
      <Panel eyebrow="Earth candidates" title={showRanks ? `${eligible} eligible · ${ineligible} not eligible` : `${eligible + ineligible} candidate site${eligible + ineligible === 1 ? '' : 's'}`}>
        <Suspense fallback={<Spinner label="Loading Earth map" />}><EarthMap pins={ePins} footprints={eFootprints} globe={false} layers={LAYERS} /></Suspense>
        <p className="mt-2 text-xs text-mute">{showRanks ? 'Numbered pins are eligible candidates by rank; × marks a candidate that is not eligible.' : 'Ranks are withheld until the release gate passes; pins show positions only.'} WGS84 lon/lat.</p>
      </Panel>
    </div>
  )
}

/** Portfolios inline: counts, sensitivity, and the standalone / combined lists. */
export function PortfoliosInline({ runId, r }: { runId: string; r: MissionResult }) {
  const [kind, setKind] = useState<'top' | 'standalone' | 'combined'>('top')
  const names = useMemo(() => Object.fromEntries(r.sites.map((s) => [s.id, s.name])), [r])
  const list: Portfolio[] = kind === 'top' ? r.portfolios : kind === 'standalone' ? r.standalone_portfolios : r.combined_portfolios
  const stab = stability(r)
  return (
    <Panel eyebrow="Portfolios" title={`${r.feasible_portfolio_count} feasible portfolio${r.feasible_portfolio_count === 1 ? '' : 's'}`}
      action={<Link to={`/portfolios/${runId}`}><Btn>Trade-off chart &amp; alternatives</Btn></Link>}>
      {r.status === 'no_feasible_portfolio' && <div className="mb-3"><Notice title="No feasible portfolio">No eligible combination satisfies the mission constraints. This is a valid outcome, not an error.</Notice></div>}
      <div className="mb-3 grid gap-3 sm:grid-cols-4">
        <Stat k="Weight scenarios" v={`${stab.scenarios} (seed ${r.sensitivity.seed})`} />
        <Stat k="Weight factor range" v={`×${r.sensitivity.weight_factor_range.join(' – ×')}`} />
        <Stat k="Top portfolio held" v={stab.top ? `${stab.top.ids.split(/[,+|]/).map((x) => names[x.trim()] ?? x.trim()).join(' + ')} · ${stab.top.count}/${stab.scenarios}` : '—'} />
        <Stat k="Infeasible scenarios" v={String(stab.infeasible)} />
      </div>
      <Tabs label="Portfolio list" value={kind} onChange={setKind} tabs={[
        { id: 'top', label: `Best (${r.portfolios.length})` }, { id: 'standalone', label: `Individual (${r.standalone_portfolios.length})` }, { id: 'combined', label: `Complementary (${r.combined_portfolios.length})` }]} />
      <div className="mt-3">
        {list.length === 0 ? <Empty>No portfolios in this list{r.portfolio_mode !== 'both' ? ` (portfolio mode was “${r.portfolio_mode}”)` : ''}.</Empty> : (
          <Scroll><table className="tbl">
            <thead><tr><th>#</th><th>Sites</th><th>Type</th><th>Objective</th><th>Coverage utility</th><th>Redundancy</th><th>Min evidence coverage</th><th>Cost</th><th>Effort</th><th>Ops</th></tr></thead>
            <tbody>{list.map((p, i) => <tr key={i}><td className="mono">{i + 1}</td><td>{p.site_ids.map((s) => names[s] ?? s).join(' + ')}</td><td>{p.kind}</td>
              <td><Meter value={p.objective} label="objective" /></td><td className="mono">{idx(p.test_coverage_utility)}</td><td className="mono">{idx(p.redundancy)}</td>
              <td className="mono">{idx(p.minimum_evidence_coverage)}</td><td className="mono">{money(p.cost)}</td><td className="mono">{days(p.days)}</td>
              <td><Badge tone={p.operational_status === 'pass' ? 'ok' : 'warn'}>{p.operational_status}</Badge></td></tr>)}</tbody>
          </table></Scroll>)}
      </div>
      <p className="mt-2 text-xs text-mute">Objective and utilities are unitless 0–1 indices from the deterministic engine. Cost and effort are only what you provided.</p>
    </Panel>
  )
}
const Stat = ({ k, v }: { k: string; v: string }) => <div className="rounded border border-line px-2 py-1.5"><div className="eyebrow !text-mute !text-[0.6rem]">{k}</div><div className="mono text-sm">{v}</div></div>

function DataLink({ id, ids }: { id: string; ids: Set<string> }) {
  return ids.has(id) ? <Link className="mono underline decoration-ember/60 underline-offset-4 hover:text-ember" to={`/data/${encodeURIComponent(id)}`}>{id}</Link> : <span className="mono" title="Not available in the Data Explorer">{id}</span>
}
function SrcLink({ url, children }: { url: string | null | undefined; children?: React.ReactNode }) {
  const h = safeHref(url)
  return h ? <a className="underline" href={h} target="_blank" rel="noreferrer">{children ?? 'source'}</a> : <span className="text-mute">{url ? short(url, 24) : '—'}</span>
}

/** Every observation and asset with a link to its Data Explorer dataset (when one exists) and its source product / URL. */
export function DataProvenance({ r, ev, synthetic }: { r: MissionResult; ev: ReleaseEvidence | null; synthetic: boolean }) {
  const ids = useExplorableIds()
  const obs = ev?.observations ?? []
  const products = useMemo(() => {
    const m = new Map<string, { product: string; url: string; n: number }>()
    for (const o of obs) { const k = `${o.source_product}|${o.source_url}`; const e = m.get(k); if (e) e.n++; else m.set(k, { product: o.source_product, url: o.source_url, n: 1 }) }
    return [...m.values()]
  }, [obs])
  const ranked = useMemo(() => rankSites(r.sites), [r])
  return (
    <div className="space-y-5">
      <Panel eyebrow="Data navigation" title="Candidate and target datasets">
        <div className="grid gap-4 md:grid-cols-2">
          <div><h3 className="mb-1 text-sm text-ivory-dim">Candidate sites</h3>
            <ul className="space-y-1 text-sm">{ranked.map((s) => <li key={s.id} className="flex flex-wrap items-center gap-2"><DataLink id={s.id} ids={ids} /><span className="text-ivory-dim">{s.name}</span><span className="text-xs text-mute">{s.body}</span>
              <span className="mono text-xs text-mute">{[...new Set(Object.values(s.contributions).map((c) => c.source_id))].join(', ')}</span></li>)}</ul></div>
          <div><h3 className="mb-1 text-sm text-ivory-dim">Target profiles</h3>
            {r.target_profiles.length === 0 ? <p className="text-sm text-mute">None.</p> : <ul className="space-y-2 text-sm">{r.target_profiles.map((t) => (
              <li key={t.location.id}><DataLink id={t.location.id} ids={ids} /> <span className="text-xs text-mute">{t.body}</span>
                <ul className="mt-1 space-y-0.5 pl-4 text-xs text-ivory-dim">{Object.entries(t.observations).map(([k, o]) => <li key={k}><span className="mono">{k}</span> = <span className="mono">{o.value ?? '—'}</span> {o.unit} <span className="mono text-mute">· {o.source_id}</span>{o.missing_reason && <span className="text-warn"> · {o.missing_reason}</span>}</li>)}</ul></li>))}</ul>}
          </div>
        </div>
        <p className="mt-3 text-xs text-mute">Underlined ids open the dataset in the Data Explorer; plain ids have no dataset there.</p>
      </Panel>
      <Panel eyebrow="Evidence" title={`${obs.length} attested observation${obs.length === 1 ? '' : 's'}`}>
        {!ev ? <Empty>Evidence sidecar unavailable.</Empty> : obs.length === 0 ? <Empty>No observations are attested in this run{synthetic ? ' (synthetic runs carry none)' : ''}.</Empty> : (
          <Scroll><table className="tbl">
            <thead><tr><th>Evidence</th><th>Site</th><th>Feature</th><th>Value</th><th>QA</th><th>Source product</th><th>Granule</th><th>Assets</th><th>URL</th></tr></thead>
            <tbody>{obs.map((o) => <tr key={o.evidence_id}><td className="mono text-xs">{o.evidence_id}</td><td><DataLink id={o.site_id} ids={ids} /></td><td className="mono">{o.feature_id}</td>
              <td className="mono">{o.value ?? '—'} <span className="text-ivory-dim">{o.unit}</span></td><td><Badge tone={o.qa_status === 'ACCEPT' ? 'ok' : 'warn'}>{o.qa_status}</Badge></td>
              <td className="text-xs">{o.source_product}</td><td className="mono text-xs">{short(o.source_granule_id ?? '', 28)}</td><td className="mono text-xs">{o.source_asset_ids.join(', ')}</td><td className="text-xs"><SrcLink url={o.source_url} /></td></tr>)}</tbody>
          </table></Scroll>)}
      </Panel>
      <div className="grid gap-5 md:grid-cols-2">
        <Panel eyebrow="Source products" title={`${products.length} product${products.length === 1 ? '' : 's'}`}>
          {products.length === 0 ? <Empty>No source products are attested.</Empty> : <ul className="space-y-1 text-sm">{products.map((p) => <li key={p.product + p.url}>{p.product} <span className="text-xs text-mute">({p.n} obs)</span> · <SrcLink url={p.url} /></li>)}</ul>}
        </Panel>
        <Panel eyebrow="Assets" title={`${ev?.assets.length ?? 0} source asset${ev?.assets.length === 1 ? '' : 's'}`}>
          {!ev || ev.assets.length === 0 ? <Empty>No source assets are attested{synthetic ? ' (synthetic fixture)' : ''}.</Empty> : (
            <ul className="space-y-1 text-sm">{ev.assets.map((a) => <li key={a.asset_id}><span className="mono text-xs">{a.asset_id}</span> · {a.product_id} <span className="mono text-xs text-mute">{a.product_version}</span> · <span className="mono text-xs text-mute">sha256 {short(a.sha256, 10)}</span> · <SrcLink url={a.source_url} /></li>)}</ul>)}
        </Panel>
      </div>
    </div>
  )
}

/** Embedded backend report and Blob downloads of every mission artefact. */
export function ReportSection({ runId, r, ev, demo }: { runId: string; r: MissionResult; ev: ReleaseEvidence | null; demo: boolean }) {
  const report = useQuery({ queryKey: ['report-html', runId], queryFn: () => getReportHtml(runId), enabled: !demo, retry: false })
  const [busy, setBusy] = useState(false), [msg, setMsg] = useState<string | null>(null)
  const obs = ev?.observations ?? []
  const trace = async () => {
    setBusy(true); setMsg(null)
    try { download(`${runId}-agent-trace.json`, JSON.stringify(await getAgents(runId), null, 2)) }
    catch (e) { setMsg(`Agent trace unavailable: ${e instanceof ApiError ? `${e.code}: ${e.message}` : (e as Error).message}`) }
    finally { setBusy(false) }
  }
  const ranking = () => download(`${runId}-ranking.csv`, toCsv(['rank', 'site_id', 'site', 'body', 'longitude', 'latitude', 'eligible', 'observed_similarity', 'lower_utility', 'upper_utility', 'coverage', 'access'],
    rankSites(r.sites).map((s) => ({ rank: s.rank, site_id: s.id, site: s.name, body: s.body, longitude: s.longitude, latitude: s.latitude, eligible: s.eligible, observed_similarity: s.observed_similarity, lower_utility: s.lower_utility, upper_utility: s.upper_utility, coverage: s.coverage, access: s.access }))), 'text/csv')
  return (
    <Panel eyebrow="Report" title="Server report and downloads">
      <div className="mb-4 flex flex-wrap gap-2">
        <Btn onClick={() => download(`${runId}-result.json`, JSON.stringify(r, null, 2))}>Result JSON</Btn>
        <Btn disabled={!ev} title={ev ? undefined : 'Evidence sidecar unavailable'} onClick={() => download(`${runId}-evidence.json`, JSON.stringify(ev, null, 2))}>Evidence JSON</Btn>
        <Btn disabled={demo || busy} title={demo ? 'Demo runs have no agent trace' : undefined} onClick={() => void trace()}>{busy ? 'Fetching…' : 'Agent trace JSON'}</Btn>
        <Btn disabled={!report.data} title={report.data ? undefined : 'Report HTML not loaded'} onClick={() => download(`${runId}-report.html`, report.data!, 'text/html')}>Report HTML</Btn>
        <Btn disabled={obs.length === 0} title={obs.length ? undefined : 'No attested observations'} onClick={() => download(`${runId}-observations.csv`, observationsCsv(obs), 'text/csv')}>Observations CSV ({obs.length})</Btn>
        <Btn onClick={ranking}>Ranking CSV</Btn>
        <Link to={`/reports/${runId}`}><Btn variant="primary">Printable report</Btn></Link>
      </div>
      {msg && <div className="mb-3"><Notice tone="bad" title="Download failed">{msg}</Notice></div>}
      {demo ? <Empty>Demo runs have no backend-rendered report. Use the printable report view.</Empty>
        : report.isLoading ? <Spinner label="Loading report" />
        : report.isError ? <Notice tone="bad" title="Report unavailable">{(report.error as Error).message}</Notice>
        : <>
          <iframe title="Mission report" sandbox="" srcDoc={report.data} className="h-[36rem] w-full rounded border border-line bg-white" />
          <a className="mt-2 inline-block text-sm underline" href={reportUrl(runId)} target="_blank" rel="noreferrer">Open report in new tab</a>
        </>}
    </Panel>
  )
}

/** Full event log, phase timeline and agent activity. */
export function MissionLogs({ runId, events, evErr }: { runId: string; events: ProgressEvent[]; evErr: string | null }) {
  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-[22rem_1fr]">
        <Panel eyebrow="P00 – P90" title="Pipeline"><PhaseTimeline events={events} /></Panel>
        <Panel eyebrow="Event stream" title={`Event log (${events.length})`}>{evErr && <div className="mb-2"><Notice tone="warn" title="Event log issue">{evErr}</Notice></div>}<EventLog events={events} /></Panel>
      </div>
      <AgentActivity runId={runId} live={false} />
    </div>
  )
}
