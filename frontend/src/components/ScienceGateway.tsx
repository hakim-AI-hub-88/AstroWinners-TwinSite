import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge, Btn, Notice, Panel, Scroll, Spinner } from '@/components/ui'
import { LocationPicker } from '@/components/LocationPicker'
import { ApiError, getCoverage, getSciObservations, getSciSites, postSciSite, sciAssetUrl, type SciObs } from '@/lib/api'

const KIND_TONE: Record<string, 'ok' | 'warn' | 'mute' | 'ember'> = {
  measurement: 'ok', derived_measurement: 'ok', reanalysis_model: 'ember', reference_constant: 'mute', visualization: 'warn', discovery_only: 'warn',
}
const STATUS_TONE: Record<string, 'ok' | 'warn' | 'mute' | 'bad' | 'ember'> = {
  real_data: 'ok', implemented: 'ok', reference_constant: 'mute', visualization_only: 'warn', source_metadata_only: 'warn', user_input: 'ember', user_input_only: 'ember', missing: 'bad',
}
const fmt = (v: number | null) => (v === null || v === undefined ? '—' : Math.abs(v) >= 1000 || (Math.abs(v) < 0.01 && v !== 0) ? v.toExponential(2) : String(Math.round(v * 1000) / 1000))

/** Persisted scientific observations from real NASA services, compared across any sites. Live API only. */
export function ScienceGateway() {
  const qc = useQueryClient()
  const sites = useQuery({ queryKey: ['sci-sites'], queryFn: getSciSites, retry: false })
  const [picked, setPicked] = useState<string[]>([])
  const [form, setForm] = useState({ name: '', lon: '', lat: '' })
  const all = sites.data?.sites ?? []
  const chosen = picked.length ? picked : all.filter((s) => s.body === 'Earth' && s.lon !== null).slice(0, 3).map((s) => s.site_id)
  const obs = useQuery({ queryKey: ['sci-obs', chosen], queryFn: () => getSciObservations(chosen), enabled: chosen.length > 0 })
  const coverage = useQuery({ queryKey: ['coverage'], queryFn: getCoverage, retry: false })
  const add = useMutation({
    mutationFn: () => postSciSite(form.name, Number(form.lon), Number(form.lat)),
    onSuccess: (r) => { setPicked((p) => [...new Set([...(p.length ? p : chosen), r.site_id])].slice(-6)); void qc.invalidateQueries({ queryKey: ['sci-sites'] }) },
  })
  const table = useMemo(() => {
    const byQ = new Map<string, Map<string, SciObs>>()
    for (const o of obs.data?.observations ?? []) {
      const k = `${o.domain}|${o.quantity}|${o.unit ?? ''}`
      if (!byQ.has(k)) byQ.set(k, new Map())
      byQ.get(k)!.set(o.site_id, o)
    }
    return [...byQ.entries()].sort()
  }, [obs.data])
  const images = (obs.data?.observations ?? []).filter((o) => o.kind === 'visualization' && o.asset_id)
  if (sites.isError) return <Notice tone="mute" title="Scientific Data Gateway needs the live API">{(sites.error as Error).message}</Notice>
  if (sites.isLoading) return <Spinner label="Loading persisted scientific sites" />
  const name = (id: string) => all.find((s) => s.site_id === id)?.name ?? id
  return (
    <div className="space-y-5">
      <Panel eyebrow="Scientific Data Gateway · persisted observations" title="Compare sites side by side">
        <p className="mb-3 text-sm text-ivory-dim">Values below were retrieved from NASA services (POWER climatology, GIBS imagery, CMR discovery, NSSDCA constants) and stored with source URL, asset SHA-256, units, support and QA flags. Reanalysis values are model products, not station measurements; imagery is visualization only.</p>
        <div className="mb-3 flex flex-wrap gap-2">
          {all.map((s) => (
            <label key={s.site_id} className={`cursor-pointer rounded-full border px-3 py-1 text-xs ${chosen.includes(s.site_id) ? 'border-ember text-ember' : 'border-line text-ivory-dim'}`}>
              <input type="checkbox" className="sr-only" checked={chosen.includes(s.site_id)}
                onChange={() => setPicked(chosen.includes(s.site_id) ? chosen.filter((x) => x !== s.site_id) : [...chosen, s.site_id].slice(-6))} />
              {s.name} <span className="text-mute">({s.body}, {s.observation_count})</span>
            </label>))}
        </div>
        <div className="mb-4 rounded-md border border-line p-3">
          <div className="mb-2 text-xs uppercase tracking-wide text-ember">Choose any Earth location</div>
          <LocationPicker value={form.lon && form.lat ? { lon: Number(form.lon), lat: Number(form.lat), name: form.name } : null}
            onChange={(v) => setForm({ name: v.name, lon: String(v.lon), lat: String(v.lat) })} />
        </div>
        <form className="mb-4 grid gap-2 sm:grid-cols-[1fr_8rem_8rem_auto]" onSubmit={(e) => { e.preventDefault(); add.mutate() }}>
          <div><label className="fld" htmlFor="sn">Add Earth site</label><input id="sn" placeholder="e.g. Atacama (Yungay)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
          <div><label className="fld" htmlFor="slon">Longitude</label><input id="slon" inputMode="decimal" value={form.lon} onChange={(e) => setForm({ ...form, lon: e.target.value })} /></div>
          <div><label className="fld" htmlFor="slat">Latitude</label><input id="slat" inputMode="decimal" value={form.lat} onChange={(e) => setForm({ ...form, lat: e.target.value })} /></div>
          <div className="flex items-end"><Btn variant="primary" disabled={add.isPending || !form.lon || !form.lat}>{add.isPending ? 'Retrieving from NASA…' : 'Retrieve real data'}</Btn></div>
        </form>
        {add.isError && <Notice tone="bad" title="Retrieval failed">{add.error instanceof ApiError ? add.error.message : String(add.error)}</Notice>}
        {obs.isLoading ? <Spinner /> : (
          <Scroll><table className="tbl">
            <caption className="sr-only">Observations by site</caption>
            <thead><tr><th>Domain</th><th>Quantity</th><th>Unit</th>{chosen.map((s) => <th key={s}>{name(s)}</th>)}<th>Kind / source</th></tr></thead>
            <tbody>{table.map(([k, m]) => {
              const [domain, quantity, unit] = k.split('|')
              const any = [...m.values()][0]
              return (
                <tr key={k}>
                  <td className="text-xs text-mute">{domain}</td><td>{quantity.replace(/_/g, ' ')}</td><td className="mono text-xs">{unit || '—'}</td>
                  {chosen.map((s) => { const o = m.get(s); return (
                    <td key={s} className="mono" title={o ? `${o.evidence_id}\n${o.statistic ?? ''}\n${o.temporal_support ?? ''}\n${o.comparability ?? ''}` : 'no observation'}>
                      {o ? (o.value === null ? <span className="text-warn">{o.missing_reason ? 'missing' : 'n/a'}</span> : fmt(o.value)) : <span className="text-mute">—</span>}
                      {o?.uncertainty?.low != null && <div className="text-[10px] text-mute">{fmt(o.uncertainty.low ?? null)}–{fmt(o.uncertainty.high ?? null)}</div>}
                    </td>) })}
                  <td><Badge tone={KIND_TONE[any.kind] ?? 'mute'}>{any.kind.replace(/_/g, ' ')}</Badge> <span className="text-xs text-mute">{any.source_id}</span></td>
                </tr>)
            })}</tbody>
          </table></Scroll>)}
        {images.length > 0 && (
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {images.map((o) => (
              <figure key={o.evidence_id} className="rounded-md border border-line p-2">
                <img src={sciAssetUrl(o.asset_id!)} alt={`NASA GIBS true colour over ${name(o.site_id)}`} className="w-full rounded" loading="lazy" />
                <figcaption className="mt-1 text-xs text-mute">{name(o.site_id)} · {o.product_id} · {o.temporal_support} · visualization only</figcaption>
              </figure>))}
          </div>)}
      </Panel>
      <Panel eyebrow="Completeness check · computed from persisted evidence" title="14-domain coverage matrix">
        {coverage.isLoading ? <Spinner /> : coverage.isError ? <Notice tone="mute" title="Coverage unavailable">{(coverage.error as Error).message}</Notice> : (
          <Scroll><table className="tbl">
            <thead><tr><th>Domain</th><th>Body</th><th>Status</th><th>Sources</th><th>Simple</th><th>AI</th><th>Explorer</th><th>Known gap</th></tr></thead>
            <tbody>{coverage.data!.rows.map((r) => (
              <tr key={r.domain + r.body}>
                <td>{r.domain.replace(/_/g, ' ')}</td><td>{r.body}</td>
                <td><Badge tone={STATUS_TONE[r.real_data_status] ?? 'mute'}>{r.real_data_status.replace(/_/g, ' ')}</Badge></td>
                <td className="text-xs text-ivory-dim">{r.sources.join(', ') || '—'}</td>
                <td>{r.simple_analysis ? '✓' : '—'}</td><td>{r.ai_agents ? '✓' : '—'}</td><td>{r.data_explorer ? '✓' : '—'}</td>
                <td className="text-xs text-mute">{r.limitations || '—'}</td>
              </tr>))}</tbody>
          </table></Scroll>)}
      </Panel>
    </div>
  )
}
