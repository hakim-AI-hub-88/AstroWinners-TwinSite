import { lazy, Suspense, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Badge, DemoBanner, Empty, Notice, PageHeader, Panel, Spinner, Tabs } from '@/components/ui'
import PlanetMap from '@/components/PlanetMap'
import { SelectedSitePanel } from '@/components/SelectedSite'
import { getSciSites } from '@/lib/api'
import { candidatePins, footprintsFor, storedSitePins } from '@/lib/overlays'
import { pointName, type PickedSite } from '@/lib/picking'
import { useEvidence, useExplorableIds, useResult, useStatus } from '@/lib/hooks'
import { FIXTURES, demoRunIdFor, demoStart, isDemoRun } from '@/lib/demo'
import { loadRecent } from '@/lib/recent'
import { CRS } from '@/lib/regions'
import type { Body } from '@/lib/types'
const EarthMap = lazy(() => import('@/components/EarthMap'))
const PlanetGlobe = lazy(() => import('@/components/PlanetGlobe'))

type Mode = '2d' | 'globe'
export default function Explorer() {
  const [sp, setSp] = useSearchParams()
  const runId = sp.get('run') ?? ''
  const initialBody = (['Earth', 'Moon', 'Mars'] as const).find((b) => b === sp.get('body')) ?? 'Earth'
  const [body, setBody] = useState<Body>(initialBody)
  const [mode, setMode] = useState<Mode>('2d')
  const [layers, setLayers] = useState({ pins: true, footprints: true, graticule: true, basemap: true })
  const status = useStatus(runId)
  const ok = !!runId && (status.data?.status === 'completed' || status.data?.status === 'completed_with_limits')
  const result = useResult(runId, ok)
  const evidence = useEvidence(runId, ok)
  const r = result.data

  const pins = useMemo(() => candidatePins(r, body), [r, body])
  const footprints = useMemo(() => footprintsFor(r, body), [r, body])
  const sci = useQuery({ queryKey: ['sci-sites'], queryFn: getSciSites, retry: false })
  const stored = useMemo(() => storedSitePins(sci.data?.sites, body), [sci.data, body])
  const explorable = useExplorableIds()
  const [picked, setPicked] = useState<PickedSite | null>(null)
  const pick = (lon: number, lat: number) => setPicked({ body, lon, lat, name: pointName(body, lon, lat) })
  const sel = picked && picked.body === body ? picked : null
  const marker = useMemo(() => (sel ? { lon: sel.lon, lat: sel.lat, label: 'Selected' } : null), [sel])
  const switchBody = (b: Body) => { setBody(b); setPicked(null) }
  const recents = loadRecent()
  const synthetic = r?.data_status === 'synthetic' || isDemoRun(runId)

  return (
    <>
      {synthetic && <DemoBanner>Candidate and target positions on this map come from synthetic fixtures.</DemoBanner>}
      <div className="mx-auto max-w-7xl px-4 py-8">
        <PageHeader eyebrow="Explorer" title="Planetary map" sub="Each body has its own coordinate system and overlays. Earth shows NASA Blue Marble imagery; Moon and Mars show NASA LRO and Viking mosaics of that same body on a planetocentric grid, so no Earth data is ever drawn on another body." />
        <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Tabs<Body> label="Body" value={body} onChange={switchBody} tabs={[{ id: 'Earth', label: 'Earth' }, { id: 'Moon', label: 'Moon' }, { id: 'Mars', label: 'Mars' }]} />
              <Tabs<Mode> label={`${body} view`} value={mode} onChange={setMode} tabs={[{ id: '2d', label: '2D map' }, { id: 'globe', label: '3D globe' }]} />
            </div>
            {body === 'Earth'
              ? <Suspense fallback={<Spinner label="Loading Earth map" />}><EarthMap pins={pins} footprints={footprints} globe={mode === 'globe'} layers={layers} onPick={pick} extraPins={stored} marker={marker} /></Suspense>
              : mode === 'globe'
                ? <Suspense fallback={<Spinner label={`Loading ${body} globe`} />}><PlanetGlobe body={body} pins={pins} footprints={footprints} layers={layers} onPick={pick} extraPins={stored} marker={marker} /></Suspense>
                : <PlanetMap body={body} pins={pins} footprints={footprints} layers={layers} onPick={pick} extraPins={stored} marker={marker} />}
            <p className="text-xs text-mute">Coordinate system: <span className="mono">{CRS[body]}</span>{body === 'Earth' ? ' · basemap tiles load from NASA GIBS; markers remain if tiles are unavailable' : ' · basemap tiles load from NASA Trek; markers remain if tiles are unavailable'}</p>
          </div>
          <aside className="space-y-4">
            {sel ? <SelectedSitePanel site={sel} onRename={(name) => setPicked({ ...sel, name })} onClear={() => setPicked(null)} />
              : <Notice tone="mute" title="Click the map to select a site">Pick any point on {body} to retrieve real data for it{body === 'Earth' ? '' : ' or find Earth analog matches'}.</Notice>}
            <Panel eyebrow="Run" title={runId ? <span className="mono text-base">{runId}</span> : 'No run selected'}>
              {runId ? (status.isError ? <Notice tone="bad" title="Run not found">{(status.error as Error).message}</Notice> : !ok ? <p className="text-sm text-mute">Status: {status.data?.status ?? 'loading'} — candidates appear after completion.</p> : <div className="space-y-1 text-sm text-ivory-dim"><div>{r?.sites.length} candidates · {r?.target_profiles.length} targets</div><div className="mono text-xs">{evidence.data?.source_snapshot_id ?? 'no snapshot'}</div><Link className="underline" to={`/analysis/${runId}`}>Open analysis</Link></div>) : <p className="text-sm text-mute">Pick a run to place candidates and target footprints.</p>}
              <div className="mt-3"><label className="fld" htmlFor="run-pick">Choose run</label>
                <select id="run-pick" value={runId} onChange={(e) => { if (isDemoRun(e.target.value)) demoStart(e.target.value); setSp(e.target.value ? { run: e.target.value } : {}) }}>
                  <option value="">None</option>
                  {recents.filter((x) => !x.demo).length > 0 && <optgroup label="Your runs">{recents.filter((x) => !x.demo).map((x) => <option key={x.runId} value={x.runId}>{x.title} · {x.runId}</option>)}</optgroup>}
                  <optgroup label="Demo fixtures (synthetic)">{FIXTURES.map((f) => <option key={f.key} value={demoRunIdFor(f.key)}>{f.title}</option>)}</optgroup>
                </select></div>
            </Panel>
            <Panel eyebrow="Stored scientific sites" title={`${stored.length} on ${body}`}>
              {sci.isLoading ? <p className="text-sm text-mute">Loading stored sites…</p>
                : sci.isError ? <p className="text-sm text-mute">Stored sites unavailable: {(sci.error as Error).message}</p>
                : stored.length === 0 ? <Empty>No stored sites on {body} yet.</Empty>
                : <ul className="max-h-56 space-y-0.5 overflow-auto text-sm">{(sci.data?.sites ?? []).filter((x) => x.body === body && x.lon != null && x.lat != null).map((x) => (
                  <li key={x.site_id} className="flex items-center justify-between gap-2">
                    <button type="button" className="text-left underline decoration-line underline-offset-4 hover:text-ember" onClick={() => setPicked({ body, lon: x.lon!, lat: x.lat!, name: x.name })}>{x.name}</button>
                    {explorable.has(x.site_id) ? <Link className="text-xs text-mute underline hover:text-ivory" to={`/data/${encodeURIComponent(x.site_id)}`}>{x.observation_count} obs</Link> : <span className="text-xs text-mute">{x.observation_count} obs</span>}</li>))}</ul>}
              <p className="mt-2 text-xs text-mute">◇ marks a stored site on the map. Selecting one fills the Selected site panel.</p>
            </Panel>
            <Panel eyebrow="Overlays" title={`${body} layers`}>
              {([['pins', 'Candidates, stored sites & selection'], ['footprints', 'Target / search footprints'], ...(body === 'Earth' ? [['basemap', 'NASA Blue Marble basemap']] : [['basemap', body === 'Mars' ? 'NASA Viking colour mosaic' : 'NASA LRO WAC mosaic'], ['graticule', 'Lon/lat graticule']])] as Array<[keyof typeof layers, string]>).map(([k, label]) => (
                <label key={k} className="flex items-center gap-2 py-1 text-sm"><input className="!w-4" type="checkbox" checked={layers[k]} onChange={(e) => setLayers({ ...layers, [k]: e.target.checked })} /> {label}</label>))}
            </Panel>
            <Panel eyebrow="On this map" title={`${pins.length} candidates · ${footprints.length} footprints`}>
              {pins.length + footprints.length === 0 ? <Empty>{r ? `This run has nothing on ${body}.` : 'Nothing to show yet.'}</Empty> : <ul className="space-y-1 text-sm">{pins.map((p) => <li key={p.id} className="flex items-center justify-between gap-2"><span>{p.rank ? `#${p.rank} ` : ''}{p.label}</span>{p.eligible === false && <Badge tone="bad">ineligible</Badge>}</li>)}{footprints.map((f) => <li key={f.id} className="text-ivory-dim">▭ {f.label}</li>)}</ul>}
            </Panel>
          </aside>
        </div>
      </div>
    </>
  )
}
