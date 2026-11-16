import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge, Btn, Notice, Panel, Scroll } from '@/components/ui'
import { ApiError, getAnalysisMode, getSciObservations, postCharacterize, postMatch, type SciObs } from '@/lib/api'
import { rememberRun } from '@/lib/recent'
import type { PickedSite } from '@/lib/picking'

const errText = (e: unknown) => e instanceof ApiError
  ? e.status === 404 || e.status === 405 || e.status === 501 ? `This endpoint is not available on the API yet (${e.status}).` : e.status === 0 ? 'API unreachable. Start the backend and retry.' : `${e.code}${e.field ? ` (${e.field})` : ''}: ${e.message}`
  : (e as Error).message

/** Seconds since `active` became true; resets when it turns off. */
export function useElapsed(active: boolean) {
  const [s, setS] = useState(0)
  useEffect(() => {
    if (!active) { setS(0); return }
    const t0 = Date.now(), t = setInterval(() => setS(Math.floor((Date.now() - t0) / 1000)), 500)
    return () => clearInterval(t)
  }, [active])
  return s
}

/** Matching starts a full mission on the server: characterise the Moon/Mars target, pre-rank stored Earth sites, analyse the best. */
export function useMatch() {
  const nav = useNavigate()
  return useMutation({
    mutationFn: (t: PickedSite) => postMatch({ body: t.body as 'Moon' | 'Mars', longitude: t.lon, latitude: t.lat, name: t.name }, 12),
    onSuccess: (acc, t) => {
      rememberRun({ runId: acc.run_id, title: `Earth analogs for ${t.name}`, body: `Earth + ${t.body}`, demo: false, at: Date.now() })
      nav(`/analysis/${acc.run_id}`)
    },
  })
}
export const matchError = errText

/** Selected point: coordinates, real-data retrieval and (Moon/Mars) Earth-analog matching. */
export function SelectedSitePanel({ site, onRename, onClear }: { site: PickedSite; onRename?: (name: string) => void; onClear: () => void }) {
  const qc = useQueryClient()
  const characterize = useMutation({
    mutationFn: (s: PickedSite) => postCharacterize(s.body, s.lon, s.lat, s.name),
    onSuccess: (r) => { void qc.invalidateQueries({ queryKey: ['sci-sites'] }); void qc.invalidateQueries({ queryKey: ['site-obs', r.site_id] }) },
  })
  const match = useMatch()
  const charSecs = useElapsed(characterize.isPending), matchSecs = useElapsed(match.isPending)
  // A new pick discards the previous point's results.
  useEffect(() => { characterize.reset(); match.reset() }, [site.body, site.lon, site.lat]) // eslint-disable-line react-hooks/exhaustive-deps
  const d = characterize.data
  const offWorld = site.body !== 'Earth'
  return (
    <Panel eyebrow={`Selected site · ${site.body}`} title={<span className="mono text-base">{site.lat.toFixed(4)}°, {site.lon.toFixed(4)}°</span>}
      action={<button type="button" className="text-xs text-mute underline hover:text-ivory" onClick={onClear}>Clear</button>}>
      <div className="space-y-3 text-sm">
        <div className="text-xs text-mute">Latitude, longitude · {site.body === 'Earth' ? 'WGS84' : `${site.body} planetocentric east longitude`}</div>
        {onRename && <div><label className="fld" htmlFor="pick-name">Site name</label><input id="pick-name" value={site.name} onChange={(e) => onRename(e.target.value)} /></div>}
        <div className="flex flex-wrap gap-2">
          <Btn variant={offWorld ? 'ghost' : 'primary'} disabled={characterize.isPending || !site.name.trim()} onClick={() => characterize.mutate(site)}>
            {characterize.isPending ? `Retrieving… ${charSecs}s` : 'Retrieve real data'}</Btn>
          {offWorld && <Btn variant="primary" disabled={match.isPending || !site.name.trim()} onClick={() => match.mutate(site)}>
            {match.isPending ? `Submitting… ${matchSecs}s` : 'Find Earth analog matches'}</Btn>}
        </div>
        {characterize.isPending && <p className="text-xs text-mute" role="status">Retrieving {site.body === 'Earth' ? 'DEM and NASA POWER' : site.body === 'Moon' ? 'LRO LOLA and Diviner' : 'MGS MOLA'} data for this point. This can take 1–3 minutes on slow connections.</p>}
        {match.isPending && <p className="text-xs text-mute" role="status">Characterising the target from real data and ranking stored Earth sites. You will be taken to the mission page.</p>}
        {offWorld && <p className="text-xs text-mute">Matching runs a full mission in {getAnalysisMode() === 'ai' ? 'AI-Powered' : 'Simple'} Analysis mode on the top stored Earth candidates.</p>}
        {characterize.isError && <Notice tone="bad" title="Data retrieval failed">{errText(characterize.error)}</Notice>}
        {match.isError && <Notice tone="bad" title="Matching could not start">{errText(match.error)}</Notice>}
        {d && <CharacterizeResultView d={d} />}
      </div>
    </Panel>
  )
}

const fmt = (v: number | null) => (v == null ? '—' : Math.abs(v) >= 1e5 || (Math.abs(v) < 0.01 && v !== 0) ? v.toExponential(2) : String(Math.round(v * 1000) / 1000))

/** Every observation stored for the site (topography plus, on Earth, climate and OpenStreetMap rows), grouped by domain. */
function StoredObservations({ siteId }: { siteId: string }) {
  const q = useQuery({ queryKey: ['site-obs', siteId], queryFn: () => getSciObservations([siteId], 200), retry: false })
  if (q.isLoading) return <p className="text-xs text-mute" role="status">Loading all stored observations for this site…</p>
  if (q.isError) return <Notice tone="warn" title="Stored observations unavailable">{errText(q.error)}</Notice>
  const obs = q.data?.observations ?? []
  const groups = new Map<string, SciObs[]>()
  for (const o of obs) { const g = groups.get(o.domain) ?? []; g.push(o); groups.set(o.domain, g) }
  return (
    <div className="space-y-2">
      <div className="text-xs uppercase tracking-wide text-ember">All stored observations ({obs.length}{q.data && q.data.total > obs.length ? ` of ${q.data.total}` : ''}) · {groups.size} domain{groups.size === 1 ? '' : 's'}</div>
      {obs.length === 0 ? <p className="text-xs text-mute">No observations are stored for this site.</p> : [...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([domain, rows]) => (
        <details key={domain} open className="rounded border border-line">
          <summary className="cursor-pointer px-2 py-1 text-xs text-ivory-dim">{domain.replace(/_/g, ' ')} <span className="text-mute">({rows.length})</span></summary>
          <ul className="divide-y divide-line text-xs">{rows.map((o) => (
            <li key={o.evidence_id} className="flex items-baseline justify-between gap-2 px-2 py-1" title={`${o.evidence_id}\n${o.source_id} · ${o.product_id}${o.temporal_support ? `\n${o.temporal_support}` : ''}`}>
              <span className="min-w-0 break-words">{o.quantity.replace(/_/g, ' ')}{o.statistic ? <span className="text-mute"> · {o.statistic}</span> : null}</span>
              <span className="mono shrink-0 text-right">{o.value == null ? <span className="text-warn">{o.missing_reason ? 'missing' : 'n/a'}</span> : fmt(o.value)} <span className="text-ivory-dim">{o.unit ?? ''}</span></span>
            </li>))}</ul>
        </details>))}
    </div>
  )
}

function CharacterizeResultView({ d }: { d: Awaited<ReturnType<typeof postCharacterize>> }) {
  return (
    <div className="space-y-3">
      <div className="break-words text-xs text-ivory-dim">Stored as <span className="mono">{d.site_id}</span>{d.aoi?.length === 4 && <> · AOI <span className="mono">[{d.aoi.map((v) => Number(v).toFixed(3)).join(', ')}]</span></>}</div>
      <StoredObservations siteId={d.site_id} />
      <div className="text-xs uppercase tracking-wide text-mute">Returned by this retrieval ({d.observations.length})</div>
      {d.observations.length === 0 ? <Notice tone="warn" title="No observations returned">The API retrieved no values for this point.</Notice> : (
        <Scroll><table className="tbl">
          <caption className="sr-only">Observations retrieved for {d.name}</caption>
          <thead><tr><th>Feature</th><th>Value</th><th>Unit</th><th>QA</th><th>Evidence</th></tr></thead>
          <tbody>{d.observations.map((o) => (
            <tr key={o.evidence_id}><td className="mono">{o.feature_id}</td><td className="mono">{o.value ?? '—'}</td><td className="mono text-ivory-dim">{o.unit ?? '—'}</td>
              <td><Badge tone={o.qa_status === 'ACCEPT' ? 'ok' : 'warn'}>{o.qa_status}</Badge></td><td className="mono text-xs text-mute">{o.evidence_id}</td></tr>))}</tbody>
        </table></Scroll>)}
      {d.acquisition_errors?.length > 0 && <Notice tone="warn" title={`${d.acquisition_errors.length} acquisition error(s)`}>
        <ul className="list-disc pl-5">{d.acquisition_errors.map((e, i) => <li key={i}>{typeof e === 'string' ? e : JSON.stringify(e)}</li>)}</ul></Notice>}
    </div>
  )
}
