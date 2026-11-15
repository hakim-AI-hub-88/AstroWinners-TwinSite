import { lazy, Suspense, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Badge, DemoBanner, Empty, Notice, PageHeader, Panel, Spinner, Tabs } from '@/components/ui'
import PlanetMap, { type Footprint, type Pin } from '@/components/PlanetMap'
import { useEvidence, useResult, useStatus } from '@/lib/hooks'
import { FIXTURES, demoRunIdFor, demoStart, isDemoRun } from '@/lib/demo'
import { loadRecent } from '@/lib/recent'
import { rankSites } from '@/lib/analysis'
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

  const { pins, footprints } = useMemo(() => {
    const pins: Pin[] = [], fps: Footprint[] = []
    if (r) {
      for (const s of rankSites(r.sites)) if (s.body === body) pins.push({ id: s.id, label: s.name, lon: s.longitude, lat: s.latitude, rank: s.rank, eligible: s.eligible })
      for (const l of r.scope.locations) if (l.body === body) fps.push({ id: l.id, label: l.id, bbox: l.bbox, kind: l.kind })
      for (const t of r.target_profiles) if (t.location.body === body && !fps.some((f) => f.id === t.location.id)) fps.push({ id: t.location.id, label: `${t.location.id} (target)`, bbox: t.location.bbox, kind: t.location.kind })
    }
    return { pins, footprints: fps }
  }, [r, body])
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
              <Tabs<Body> label="Body" value={body} onChange={setBody} tabs={[{ id: 'Earth', label: 'Earth' }, { id: 'Moon', label: 'Moon' }, { id: 'Mars', label: 'Mars' }]} />
              <Tabs<Mode> label={`${body} view`} value={mode} onChange={setMode} tabs={[{ id: '2d', label: '2D map' }, { id: 'globe', label: '3D globe' }]} />
            </div>
            {body === 'Earth'
              ? <Suspense fallback={<Spinner label="Loading Earth map" />}><EarthMap pins={pins} footprints={footprints} globe={mode === 'globe'} layers={layers} /></Suspense>
              : mode === 'globe'
                ? <Suspense fallback={<Spinner label={`Loading ${body} globe`} />}><PlanetGlobe body={body} pins={pins} footprints={footprints} layers={layers} /></Suspense>
                : <PlanetMap body={body} pins={pins} footprints={footprints} layers={layers} />}
            <p className="text-xs text-mute">Coordinate system: <span className="mono">{CRS[body]}</span>{body === 'Earth' ? ' · basemap tiles load from NASA GIBS; markers remain if tiles are unavailable' : ' · basemap tiles load from NASA Trek; markers remain if tiles are unavailable'}</p>
          </div>
          <aside className="space-y-4">
            <Panel eyebrow="Run" title={runId ? <span className="mono text-base">{runId}</span> : 'No run selected'}>
              {runId ? (status.isError ? <Notice tone="bad" title="Run not found">{(status.error as Error).message}</Notice> : !ok ? <p className="text-sm text-mute">Status: {status.data?.status ?? 'loading'} — candidates appear after completion.</p> : <div className="space-y-1 text-sm text-ivory-dim"><div>{r?.sites.length} candidates · {r?.target_profiles.length} targets</div><div className="mono text-xs">{evidence.data?.source_snapshot_id ?? 'no snapshot'}</div><Link className="underline" to={`/analysis/${runId}`}>Open analysis</Link></div>) : <p className="text-sm text-mute">Pick a run to place candidates and target footprints.</p>}
              <div className="mt-3"><label className="fld" htmlFor="run-pick">Choose run</label>
                <select id="run-pick" value={runId} onChange={(e) => { if (isDemoRun(e.target.value)) demoStart(e.target.value); setSp(e.target.value ? { run: e.target.value } : {}) }}>
                  <option value="">None</option>
                  {recents.filter((x) => !x.demo).length > 0 && <optgroup label="Your runs">{recents.filter((x) => !x.demo).map((x) => <option key={x.runId} value={x.runId}>{x.title} · {x.runId}</option>)}</optgroup>}
                  <optgroup label="Demo fixtures (synthetic)">{FIXTURES.map((f) => <option key={f.key} value={demoRunIdFor(f.key)}>{f.title}</option>)}</optgroup>
                </select></div>
            </Panel>
            <Panel eyebrow="Overlays" title={`${body} layers`}>
              {([['pins', 'Candidates & ranks'], ['footprints', 'Target / search footprints'], ...(body === 'Earth' ? [['basemap', 'NASA Blue Marble basemap']] : [['basemap', body === 'Mars' ? 'NASA Viking colour mosaic' : 'NASA LRO WAC mosaic'], ['graticule', 'Lon/lat graticule']])] as Array<[keyof typeof layers, string]>).map(([k, label]) => (
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
