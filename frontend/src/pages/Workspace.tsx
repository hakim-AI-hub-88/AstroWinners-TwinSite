import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Btn, DemoBanner, Notice, PageHeader, Panel } from '@/components/ui'
import { postMission, postPublishedMission, ApiError } from '@/lib/api'
import { useHealth } from '@/lib/hooks'
import { FIXTURES, pickFixture, demoRunIdFor, demoStart, demoRequest } from '@/lib/demo'
import { rememberRun } from '@/lib/recent'
import { getAnalysisMode, setAnalysisMode, type AnalysisMode } from '@/lib/api'
import { CRS, PRESETS } from '@/lib/regions'
import type { Body, MissionRequest } from '@/lib/types'

interface Feat { name: string; unit: string; weight: number; tolerance: number; required: boolean; on: boolean }
const FEATURES: Feat[] = [
  { name: 'slope_deg', unit: 'degree', weight: 0.45, tolerance: 20, required: true, on: true },
  { name: 'roughness_m', unit: 'm', weight: 0.35, tolerance: 6, required: false, on: true },
  { name: 'dry_fraction', unit: '1', weight: 0.2, tolerance: 0.5, required: false, on: true },
  { name: 'elevation_m', unit: 'm', weight: 0.1, tolerance: 500, required: false, on: false },
  { name: 'surface_temperature_k', unit: 'K', weight: 0.1, tolerance: 25, required: false, on: false },
]
type Box = [number, number, number, number]
const num = (v: string, d: number) => (v.trim() === '' || Number.isNaN(Number(v)) ? d : Number(v))

export default function Workspace() {
  const nav = useNavigate()
  const health = useHealth()
  const live = health.data?.status === 'ready'
  const [title, setTitle] = useState('mission-' + new Date().toISOString().slice(0, 10))
  const [targets, setTargets] = useState<Record<'Moon' | 'Mars', boolean>>({ Moon: true, Mars: false })
  const [region, setRegion] = useState<Record<'Moon' | 'Mars', string>>({ Moon: PRESETS.Moon[0].id, Mars: PRESETS.Mars[0].id })
  const [custom, setCustom] = useState<Record<'Moon' | 'Mars', Box | null>>({ Moon: null, Mars: null })
  const [mode, setMode] = useState<'auto' | 'custom'>('auto')
  const [earthArea, setEarthArea] = useState(PRESETS.Earth[0].id)
  const [feats, setFeats] = useState(FEATURES)
  const [minCov, setMinCov] = useState('0.65')
  const [maxSites, setMaxSites] = useState('2')
  const [budget, setBudget] = useState('')
  const [maxDays, setMaxDays] = useState('')
  const [allowUnknown, setAllowUnknown] = useState(false)
  const [pm, setPm] = useState<'standalone' | 'combined' | 'both'>('both')
  const [err, setErr] = useState<string | null>(null)
  const [unreachable, setUnreachable] = useState(false)

  const selected = (['Moon', 'Mars'] as const).filter((b) => targets[b])
  const boxFor = (b: 'Moon' | 'Mars'): Box => custom[b] ?? (PRESETS[b].find((p) => p.id === region[b])?.bbox as Box)

  const request = useMemo<MissionRequest>(() => {
    const locs = selected.map((b) => ({ id: region[b] === 'custom' ? `${b.toLowerCase()}-custom` : region[b], body: b as Body, coordinate_system: CRS[b], bbox: boxFor(b), kind: 'zone' as const }))
    if (mode === 'custom') {
      const p = PRESETS.Earth.find((x) => x.id === earthArea)
      locs.push({ id: earthArea === 'custom' ? 'earth-custom' : earthArea, body: 'Earth', coordinate_system: CRS.Earth, bbox: (custom as unknown as { Earth?: Box }).Earth ?? (p?.bbox as Box) ?? [-180, -90, 180, 90], kind: 'zone' })
    }
    const features = Object.fromEntries(feats.filter((f) => f.on).map((f) => [f.name, { unit: f.unit, weight: f.weight, tolerance: f.tolerance, required: f.required }]))
    return {
      schema_version: '1.0', data_status: 'measured',
      mission: {
        id: title, features, min_coverage: num(minCov, 0.65), max_sites: Math.max(1, Math.min(3, Math.round(num(maxSites, 2)))),
        budget: budget === '' ? null : num(budget, 0), max_days: maxDays === '' ? null : num(maxDays, 0), allow_unknown_access: allowUnknown,
        mode, start_trigger: 'user_request', portfolio_mode: pm, scope: { locations: locs, compare_with: ['Earth'] },
      },
      // Measurements are resolved server-side from approved assets (SHARED_CONTRACT: client assertions are not science).
      sites: [],
      target_profiles: selected.map((b) => ({ body: b, location: locs.find((l) => l.body === b)!, observations: {} })),
    } as unknown as MissionRequest
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, targets, region, custom, mode, earthArea, feats, minCov, maxSites, budget, maxDays, allowUnknown, pm])

  const [analysis, setAnalysis] = useState<AnalysisMode>(getAnalysisMode())
  const pickAnalysis = (m: AnalysisMode) => { setAnalysis(m); setAnalysisMode(m) }
  const fail = (e: unknown) => {
    const net = e instanceof ApiError && e.status === 0
    setUnreachable(net)
    setErr(e instanceof ApiError ? `${e.code}${e.field ? ` (${e.field})` : ''}: ${e.message}` : (e as Error).message)
    if (net) void health.refetch()
  }
  const run = useMutation({
    mutationFn: async () => {
      if (!live) {
        const f = pickFixture(selected)
        const id = demoRunIdFor(f.key)
        demoStart(id)
        return { runId: id, demo: true, title: f.title }
      }
      const key = crypto.randomUUID()
      const acc = await postMission(request, key)
      return { runId: acc.run_id, demo: false, title }
    },
    onSuccess: (r) => {
      rememberRun({ runId: r.runId, title: r.title, body: selected.join(' + ') || '—', demo: r.demo, at: Date.now() })
      nav(`/analysis/${r.runId}`)
    },
    onError: (e) => fail(e),
  })

  // Live API accepts measured input only when C1 evidence exists; until then the real pipeline can be exercised with a labelled synthetic fixture.
  const runFixture = useMutation({
    mutationFn: async () => {
      const f = pickFixture(selected)
      const acc = await postMission(demoRequest(demoRunIdFor(f.key)), crypto.randomUUID())
      return { runId: acc.run_id, demo: true, title: `${f.title} (synthetic, live API)` }
    },
    onSuccess: (r) => { rememberRun({ runId: r.runId, title: r.title, body: selected.join(' + ') || '—', demo: true, at: Date.now() }); nav(`/analysis/${r.runId}`) },
    onError: (e) => fail(e),
  })
  const published = useMutation({
    mutationFn: postPublishedMission,
    onSuccess: (r) => { rememberRun({ runId: r.run_id, title: 'Measured Zagora–Gale', body: 'Earth + Mars', demo: false, at: Date.now() }); nav(`/analysis/${r.run_id}`) },
    onError: (e) => fail(e),
  })
  const problems: string[] = []
  if (!selected.length) problems.push('Select at least one target body (Moon or Mars).')
  if (!feats.some((f) => f.on)) problems.push('Enable at least one feature.')
  if (feats.some((f) => f.on && f.tolerance <= 0)) problems.push('Tolerance must be greater than 0.')
  const cov = num(minCov, 0.65); if (cov < 0 || cov > 1) problems.push('Minimum coverage must be between 0 and 1.')
  const setFeat = (i: number, p: Partial<Feat>) => setFeats((fs) => fs.map((f, j) => (j === i ? { ...f, ...p } : f)))

  return (
    <>
      {!live && !health.isLoading && <DemoBanner>API offline: “Run” opens a pre-computed synthetic fixture. Your parameters are NOT scored.</DemoBanner>}
      <div className="mx-auto max-w-7xl px-4 py-8">
        <PageHeader eyebrow="Mission setup" title="Define your mission" sub="Pick the target region on the Moon or Mars, tell TwinSite which features matter, then run. Nothing is computed until you press Run; costs and effort are only what you provide." />
        <div className="mb-5"><Notice title="Published Earth / Mars evidence — review pending" tone="mute">
          Zagora SRTM and Gale MOLA at 1852.3 m scale, using cached NASA LP DAAC and PDS products with recorded source hashes.
          This preset uses fixed scenario weights and tolerances, unknown access/cost/duration, and keeps missing measurements missing. Scientific release stays blocked.
          <div className="mt-3"><Btn disabled={!live || published.isPending} onClick={() => published.mutate()}>Analyze measured Zagora–Gale pair</Btn></div>
        </Notice></div>
        <div className="grid gap-5 lg:grid-cols-[1fr_22rem]">
          <div className="space-y-5">
            <Panel eyebrow="1 · Targets" title="Where are we going?">
              <div className="grid gap-4 sm:grid-cols-2">
                {(['Moon', 'Mars'] as const).map((b) => (
                  <fieldset key={b} className={`rounded-md border p-3 ${targets[b] ? 'border-ember/60' : 'border-line'}`}>
                    <legend className="px-1 text-sm"><label className="flex items-center gap-2"><input className="!w-4" type="checkbox" checked={targets[b]} onChange={(e) => setTargets({ ...targets, [b]: e.target.checked })} /> {b} target</label></legend>
                    <label className="fld" htmlFor={`reg-${b}`}>Region</label>
                    <select id={`reg-${b}`} disabled={!targets[b]} value={region[b]} onChange={(e) => { setRegion({ ...region, [b]: e.target.value }); if (e.target.value !== 'custom') setCustom({ ...custom, [b]: null }); else setCustom({ ...custom, [b]: boxFor(b) }) }}>
                      {PRESETS[b].map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}<option value="custom">Custom bounding box…</option>
                    </select>
                    <BoxInputs disabled={!targets[b] || region[b] !== 'custom'} box={boxFor(b) ?? [0, 0, 0, 0]} onChange={(bx) => setCustom({ ...custom, [b]: bx })} crs={CRS[b]} />
                  </fieldset>
                ))}
              </div>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <div>
                  <span className="fld">Analysis mode</span>
                  <div role="radiogroup" aria-label="Analysis mode" className="flex gap-2">
                    {(['auto', 'custom'] as const).map((m) => (
                      <button key={m} role="radio" aria-checked={mode === m} onClick={() => setMode(m)} className={`flex-1 rounded-full border px-3 py-2 text-sm ${mode === m ? 'border-ember bg-ember text-ink' : 'border-line text-ivory-dim'}`}>{m === 'auto' ? 'Auto (global Earth search)' : 'Custom Earth area'}</button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="fld" htmlFor="earth-area">Earth search area {mode === 'auto' && '(automatic — not used)'}</label>
                  <select id="earth-area" disabled={mode === 'auto'} value={earthArea} onChange={(e) => setEarthArea(e.target.value)}>
                    {PRESETS.Earth.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                  </select>
                </div>
              </div>
              <p className="mt-3 text-xs text-mute">Bounding boxes are starting frames only. Moon/Mars use planetocentric east longitude (−180…180); Earth uses WGS84 lon/lat.</p>
            </Panel>

            <Panel eyebrow="2 · Features & weights" title="What makes a good analogue?">
              <div className="overflow-x-auto"><table className="tbl">
                <thead><tr><th>Use</th><th>Feature</th><th>Unit</th><th>Weight</th><th>Tolerance</th><th>Required</th></tr></thead>
                <tbody>{feats.map((f, i) => (
                  <tr key={f.name}>
                    <td><input className="!w-4" type="checkbox" aria-label={`Use ${f.name}`} checked={f.on} onChange={(e) => setFeat(i, { on: e.target.checked })} /></td>
                    <td className="mono">{f.name}</td><td className="mono text-ivory-dim">{f.unit}</td>
                    <td><input aria-label={`${f.name} weight`} className="!w-20" type="number" step="0.05" min="0" disabled={!f.on} value={f.weight} onChange={(e) => setFeat(i, { weight: num(e.target.value, 0) })} /></td>
                    <td><input aria-label={`${f.name} tolerance`} className="!w-24" type="number" step="any" min="0" disabled={!f.on} value={f.tolerance} onChange={(e) => setFeat(i, { tolerance: num(e.target.value, 0) })} /></td>
                    <td><input className="!w-4" aria-label={`${f.name} required`} type="checkbox" disabled={!f.on} checked={f.required} onChange={(e) => setFeat(i, { required: e.target.checked })} /></td>
                  </tr>))}</tbody>
              </table></div>
              <p className="mt-2 text-xs text-mute">Weights are your own priorities (the engine does not infer them). Tolerance is the feature difference at which similarity reaches zero.</p>
            </Panel>

            <Panel eyebrow="3 · Thresholds & user-provided constraints" title="Limits and trade-offs">
              <div className="grid gap-4 sm:grid-cols-3">
                <div><label className="fld" htmlFor="mincov">Min. evidence coverage (0–1)</label><input id="mincov" type="number" step="0.05" min="0" max="1" value={minCov} onChange={(e) => setMinCov(e.target.value)} /></div>
                <div><label className="fld" htmlFor="maxsites">Max sites in portfolio (1–3)</label><input id="maxsites" type="number" min="1" max="3" value={maxSites} onChange={(e) => setMaxSites(e.target.value)} /></div>
                <div><label className="fld" htmlFor="pm">Portfolio type</label><select id="pm" value={pm} onChange={(e) => setPm(e.target.value as typeof pm)}><option value="both">Standalone and combined</option><option value="standalone">Standalone only</option><option value="combined">Combined only</option></select></div>
                <div><label className="fld" htmlFor="budget">Budget (your units, optional)</label><input id="budget" type="number" min="0" placeholder="not provided" value={budget} onChange={(e) => setBudget(e.target.value)} /></div>
                <div><label className="fld" htmlFor="days">Max effort days (optional)</label><input id="days" type="number" min="0" placeholder="not provided" value={maxDays} onChange={(e) => setMaxDays(e.target.value)} /></div>
                <div className="flex items-end"><label className="flex items-center gap-2 text-sm"><input className="!w-4" type="checkbox" checked={allowUnknown} onChange={(e) => setAllowUnknown(e.target.checked)} /> Allow sites with unknown access</label></div>
              </div>
              <p className="mt-3 text-xs text-mute">TwinSite never estimates cost or effort. Leave blank to rank on science alone.</p>
            </Panel>
          </div>

          <aside className="space-y-4 lg:sticky lg:top-4 lg:self-start">
            <Panel eyebrow="4 · Run" title="Review and start">
              <label className="fld">Analysis engine</label>
              <div role="radiogroup" aria-label="Analysis engine: AI-Powered or Simple" className="mb-3 flex gap-2">
                {(['ai', 'simple'] as const).map((m) => (
                  <button key={m} role="radio" aria-checked={analysis === m} onClick={() => pickAnalysis(m)}
                    className={`flex-1 rounded-full border px-3 py-2 text-sm ${analysis === m ? 'border-ember bg-ember text-ink' : 'border-line text-ivory-dim'}`}>
                    {m === 'ai' ? 'AI-Powered Analysis' : 'Simple Analysis (no AI)'}</button>))}
              </div>
              <p className="mb-3 text-xs text-mute">{analysis === 'ai' ? 'Default. Specialised agents interpret imagery, analyse domains, propose labelled scenarios, synthesise and independently review, using free AI providers only. Deterministic code still computes every number. If AI is unavailable the real reason is shown and Simple Analysis completes.' : 'Deterministic engine only; no data leaves the server for AI providers.'}</p>
              <label className="fld" htmlFor="mid">Mission name</label>
              <input id="mid" value={title} onChange={(e) => setTitle(e.target.value.replace(/\s+/g, '-'))} />
              <dl className="mt-4 space-y-1 text-sm">
                <div className="flex justify-between"><dt className="text-mute">Targets</dt><dd>{selected.join(' + ') || '—'}</dd></div>
                <div className="flex justify-between"><dt className="text-mute">Mode</dt><dd>{mode}</dd></div>
                <div className="flex justify-between"><dt className="text-mute">Features</dt><dd>{feats.filter((f) => f.on).length}</dd></div>
                <div className="flex justify-between"><dt className="text-mute">Analysis</dt><dd>{analysis === 'ai' ? 'AI-Powered' : 'Simple'}</dd></div>
                <div className="flex justify-between"><dt className="text-mute">Data source</dt><dd>{live ? 'Live API' : 'Demo fixture'}</dd></div>
              </dl>
              {problems.length > 0 && <ul className="mt-3 list-disc pl-5 text-sm text-bad">{problems.map((p) => <li key={p}>{p}</li>)}</ul>}
              {err && <div className="mt-3"><Notice tone="bad" title={unreachable ? 'API unreachable' : 'The API rejected this mission'}>{unreachable ? 'The TwinSite backend is not running or not reachable. Start the API and worker (python scripts/integration/dev.py), then retry. Nothing was submitted.' : err}</Notice></div>}
              {live ? (<>
                <Btn variant="primary" className="mt-4 w-full py-3" disabled={problems.length > 0 || runFixture.isPending} onClick={() => { setErr(null); setUnreachable(false); runFixture.mutate() }}>{runFixture.isPending ? 'Submitting…' : 'Run synthetic fixture (DEMO data) →'}</Btn>
              </>) : (
                <Btn variant="primary" className="mt-4 w-full py-3" disabled={problems.length > 0 || run.isPending || health.isLoading} onClick={() => { setErr(null); run.mutate() }}>{health.isLoading ? 'Checking API…' : 'Open demo result →'}</Btn>
              )}
              <p className="mt-2 text-xs text-mute">Run is the only action that starts a job. Page loads never do.{live && ' The fixture button exercises the real pipeline with labelled synthetic values. Measured analysis is resolved server-side from published NASA evidence only: use “Analyze measured Zagora–Gale pair” above. Custom regions have no measured evidence yet, so they cannot be submitted as measured runs.'}</p>
            </Panel>
            {!live && (
              <Panel eyebrow="Demo fixtures" title="Pre-computed synthetic runs">
                <ul className="space-y-2 text-sm">{FIXTURES.map((f) => <li key={f.key}><a className="underline decoration-ember/60 underline-offset-4 hover:text-ember" href={`/analysis/${demoRunIdFor(f.key)}`} onClick={() => demoStart(demoRunIdFor(f.key))}>{f.title}</a></li>)}</ul>
              </Panel>
            )}
          </aside>
        </div>
      </div>
    </>
  )
}

function BoxInputs({ box, onChange, disabled, crs }: { box: Box; onChange: (b: Box) => void; disabled: boolean; crs: string }) {
  const labels = ['lon min', 'lat min', 'lon max', 'lat max']
  return (
    <div className="mt-3 grid grid-cols-4 gap-2" aria-label={`Bounding box (${crs})`}>
      {box.map((v, i) => (
        <div key={i}><label className="fld !text-[0.6rem]" htmlFor={`b-${crs}-${i}`}>{labels[i]}</label>
          <input id={`b-${crs}-${i}`} disabled={disabled} type="number" step="any" value={v} onChange={(e) => { const n = [...box] as Box; n[i] = num(e.target.value, v); onChange(n) }} /></div>
      ))}
    </div>
  )
}
