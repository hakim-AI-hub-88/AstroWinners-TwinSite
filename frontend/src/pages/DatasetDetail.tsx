import { Fragment, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Badge, Btn, DemoBanner, Empty, Notice, PageHeader, Panel, QueryError, Scroll, Spinner, Tabs } from '@/components/ui'
import { getCatalog, getGrid, getMetadata, getRecords, postCompare } from '@/lib/api'
import { Distributions, GridHeatmap } from '@/components/TerrainViz'
import { download, toCsv } from '@/lib/format'
import type { Stage } from '@/lib/types'

type Tab = Stage | 'grid' | 'metadata' | 'compare'
const MAX_ROWS = 100

export default function DatasetDetail() {
  const { datasetId = '' } = useParams()
  const [sp, setSp] = useSearchParams()
  const tab = (sp.get('tab') as Tab) ?? 'raw'
  const setTab = (t: Tab) => setSp({ ...Object.fromEntries(sp), tab: t })
  const cat = useQuery({ queryKey: ['catalog'], queryFn: getCatalog })
  const summary = cat.data?.data.find((d) => d.dataset_id === datasetId)
  return (
    <>
      {cat.data?.demo && <DemoBanner>{cat.data.note}</DemoBanner>}
      <div className="mx-auto max-w-7xl px-4 py-8">
        <p className="mb-2 text-sm"><Link className="text-mute hover:text-ivory" to="/data">← All datasets</Link></p>
        <PageHeader eyebrow="Dataset" title={<span className="mono text-2xl sm:text-3xl">{datasetId}</span>} sub={summary?.title} right={summary && <Badge tone={summary.data_status === 'synthetic' ? 'warn' : 'ok'}>{summary.data_status}</Badge>} />
        <div className="mb-5"><Tabs<Tab> label="Dataset views" value={tab} onChange={setTab} tabs={[{ id: 'raw', label: 'Raw' }, { id: 'cleaned', label: 'Cleaned' }, { id: 'derived', label: 'Derived' }, { id: 'grid', label: 'Grid map' }, { id: 'metadata', label: 'Source & QA' }, { id: 'compare', label: 'Compare' }]} /></div>
        {tab === 'grid' ? <GridView id={datasetId} /> : tab === 'metadata' ? <Meta id={datasetId} /> : tab === 'compare' ? <Compare id={datasetId} with0={sp.get('with')} /> : <Records id={datasetId} stage={tab} />}
      </div>
    </>
  )
}

function Records({ id, stage }: { id: string; stage: Stage }) {
  const q = useQuery({ queryKey: ['records', id, stage], queryFn: () => getRecords(id, stage, MAX_ROWS) })
  if (q.isLoading) return <Spinner />
  if (q.isError || !q.data) return <QueryError error={q.error} what={`${stage} records`} />
  const d = q.data.data
  const blurb = { raw: 'Source asset metadata (raster bytes are not rendered).', cleaned: 'Published terrain summaries after documented cleaning.', derived: 'Derived terrain features with evidence lineage.' }[stage]
  return (
    <Panel eyebrow={`${stage} stage`} title={blurb} action={<Btn disabled={!d.rows.length} onClick={() => download(`${id}-${stage}-sample.csv`, toCsv(d.columns, d.rows), 'text/csv')}>Download sample CSV (≤ {MAX_ROWS} rows)</Btn>}>
      {d.sampled && <div className="mb-3"><Notice tone="mute" title="Sampled view">Showing {d.rows.length}{d.total ? ` of ${d.total.toLocaleString()}` : ''} rows. Large raw files are never rendered in full.</Notice></div>}
      {d.rows.length === 0 ? <Empty>No records in this stage.</Empty> : (
        <Scroll><table className="tbl"><caption className="sr-only">{stage} records</caption>
          <thead><tr>{d.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>{d.rows.slice(0, MAX_ROWS).map((r, i) => <tr key={i}>{d.columns.map((c) => <td key={c} className="mono text-xs">{r[c] == null ? <span className="text-mute">null</span> : String(r[c])}</td>)}</tr>)}</tbody></table></Scroll>)}
    </Panel>
  )
}

function GridView({ id }: { id: string }) {
  const q = useQuery({ queryKey: ['grid', id], queryFn: () => getGrid(id) })
  if (q.isLoading) return <Spinner label="Loading cleaned grid" />
  if (q.isError || !q.data) return <QueryError error={q.error} what="the cleaned grid" />
  const g = q.data
  return (
    <div className="grid gap-5 lg:grid-cols-[1.2fr_1fr]">
      <Panel eyebrow="Cleaned stage · elevation" title={`${g.dataset_id} · ${g.display.nrows}×${g.display.ncols} display cells`}><GridHeatmap grid={g} /></Panel>
      <div className="space-y-5">
        <Panel eyebrow="Integrity" title="Pinned object">
          <dl className="space-y-2 text-sm">
            {([['SHA-256', g.cleaned_sha256], ['Native grid', `${g.native.nrows}×${g.native.ncols} · ${g.native.registration}-registered · ${g.native.dlat.toPrecision(4)}° step`], ['Display factor', `${g.display.factor}×${g.display.factor}${g.display.trimmed_native_rows ? ` (last ${g.display.trimmed_native_rows} native rows/cols not shown)` : ''}`]] as Array<[string, string]>).map(([k, v]) => <div key={k} className="grid grid-cols-[7rem_1fr] gap-2"><dt className="text-mute">{k}</dt><dd className="mono break-all text-xs">{v}</dd></div>)}
          </dl>
        </Panel>
        <Panel eyebrow="Caveats" title="Read before interpreting"><ul className="list-disc space-y-1 pl-5 text-sm">{g.caveats.map((c) => <li key={c} className="break-words">{c}</li>)}</ul></Panel>
        <Panel eyebrow="Transformations" title="Cleaning applied"><ul className="list-disc space-y-1 pl-5 text-sm">{g.transformations.map((t) => <li key={t}>{t}</li>)}</ul></Panel>
      </div>
    </div>
  )
}

function Meta({ id }: { id: string }) {
  const q = useQuery({ queryKey: ['meta', id], queryFn: () => getMetadata(id) })
  if (q.isLoading) return <Spinner />
  if (q.isError || !q.data) return <QueryError error={q.error} what="dataset metadata" />
  const m = q.data.data
  const ext = m.extent ? `≈ ${m.extent.east_west_km} km E–W × ${m.extent.north_south_km} km N–S (bbox ${m.extent.bbox_deg.join(', ')}°)` : undefined
  const res = m.native_resolution_m != null ? `native ≈ ${m.native_resolution_m} m · analysis ${m.analysis_scale_m ?? '—'} m` : undefined
  const kv: Array<[string, string | undefined]> = [['Source', m.source], ['Product', m.product], ['Version', m.version], ['License', m.license], ['CRS', m.crs], ['AOI extent', ext], ['Resolution', res], ['Time basis', m.time_basis], ['QA', m.qa], ['Units', m.unit_notes]]
  return (
    <div className="grid gap-5 md:grid-cols-2">
      <Panel eyebrow="Provenance" title="Source and QA"><dl className="space-y-2 text-sm">{kv.map(([k, v]) => <div key={k} className="grid grid-cols-[7rem_1fr] gap-2"><dt className="text-mute">{k}</dt><dd className="mono break-all text-xs">{v ?? '—'}</dd></div>)}</dl></Panel>
      <div className="space-y-5">
        <Panel eyebrow="Lineage" title="Where it came from"><ul className="list-disc space-y-1 pl-5 text-sm">{m.lineage.map((l, i) => <li key={i} className="mono break-all text-xs">{l}</li>)}</ul></Panel>
        {m.distributions && Object.keys(m.distributions).length > 0 && <Panel eyebrow="Distributions" title="Spread across analysis blocks"><Distributions sets={[{ name: m.dataset_id, tone: 'var(--color-ember)', d: m.distributions }]} /></Panel>}
        <Panel eyebrow="Transformations" title="Cleaning applied"><ul className="list-disc space-y-1 pl-5 text-sm">{m.transforms.map((l, i) => <li key={i}>{l}</li>)}</ul></Panel>
      </div>
    </div>
  )
}

function Compare({ id, with0 }: { id: string; with0: string | null }) {
  const cat = useQuery({ queryKey: ['catalog'], queryFn: getCatalog })
  const [other, setOther] = useState(with0 ?? '')
  const [stage, setStage] = useState<Stage>('cleaned')
  const leftRec = useQuery({ queryKey: ['records', id, stage], queryFn: () => getRecords(id, stage, MAX_ROWS) })
  const rightRec = useQuery({ queryKey: ['records', other, stage], queryFn: () => getRecords(other, stage, MAX_ROWS), enabled: !!other })
  const common = useMemo(() => {
    const l = leftRec.data?.data.columns ?? [], r = rightRec.data?.data.columns ?? []
    return l.filter((c) => r.includes(c) && c !== 'record_id')
  }, [leftRec.data, rightRec.data])
  const [cols, setCols] = useState<string[] | null>(null)
  const use = (cols ?? common.slice(0, 4)).filter((c) => common.includes(c))
  const cmp = useQuery({ queryKey: ['cmp', id, other, stage, use.join('|')], enabled: !!other && use.length > 0 && !!leftRec.data && !!rightRec.data,
    queryFn: () => postCompare(id, other, stage, use, leftRec.data!.data.rows.map((r) => String(r.record_id)), rightRec.data!.data.rows.map((r) => String(r.record_id))) })
  const options = (cat.data?.data ?? []).filter((d) => d.dataset_id !== id)
  const leftMeta = useQuery({ queryKey: ['meta', id], queryFn: () => getMetadata(id) })
  const rightMeta = useQuery({ queryKey: ['meta', other], queryFn: () => getMetadata(other), enabled: !!other })
  return (
    <div className="space-y-5">
      <Panel eyebrow="Side-by-side" title="Compare two datasets">
        <div className="grid gap-3 sm:grid-cols-3">
          <div><label className="fld" htmlFor="cmp-right">Compare with</label><select id="cmp-right" value={other} onChange={(e) => { setOther(e.target.value); setCols(null) }}><option value="">Choose a dataset…</option>{options.map((d) => <option key={d.dataset_id} value={d.dataset_id}>{d.dataset_id}</option>)}</select></div>
          <div><label className="fld" htmlFor="cmp-stage">Stage</label><select id="cmp-stage" value={stage} onChange={(e) => setStage(e.target.value as Stage)}><option>raw</option><option>cleaned</option><option>derived</option></select></div>
          <div><span className="fld">Columns ({use.length})</span><div className="flex flex-wrap gap-1">{common.map((c) => <button key={c} aria-pressed={use.includes(c)} onClick={() => setCols(use.includes(c) ? use.filter((x) => x !== c) : [...use, c])} className={`rounded-full border px-2 py-0.5 text-xs ${use.includes(c) ? 'border-ember text-ember' : 'border-line text-mute'}`}>{c}</button>)}</div></div>
        </div>
      </Panel>
      {!other ? <Empty>Pick a second dataset to compare approved records. Comparison is server-controlled — no expressions or SQL.</Empty> : cmp.isLoading ? <Spinner /> : cmp.isError ? <QueryError error={cmp.error} what="the comparison" /> : cmp.data && (
        <Panel eyebrow={`${stage} stage`} title={`${id} ↔ ${other}`}>
          {cmp.data.demo && <p className="mb-2 text-xs text-warn">{cmp.data.note}</p>}
          {stage !== 'raw' && <div className="mb-5 space-y-3" aria-label="Measured feature differences">
            {cmp.data.data.rows.map((r) => {
              const a = r.left?.value, b = r.right?.value
              if (typeof a !== 'number' || typeof b !== 'number' || r.left?.unit !== r.right?.unit || r.left?.analysis_scale_m !== r.right?.analysis_scale_m) return null
              const max = Math.max(Math.abs(a), Math.abs(b), 0.00001)
              return <div key={r.key}>
                <p className="text-xs">{r.key}: left {a}, right {b} {String(r.left?.unit)} · right − left = {(b-a).toFixed(4)}. Bars are normalised per feature.</p>
                <svg viewBox="0 0 400 32" className="h-8 w-full" role="img" aria-label={`${r.key}: left ${a}, right ${b}`}>
                  <rect x="0" y="2" width={Math.abs(a)/max*390} height="10" fill="#e79d61" />
                  <rect x="0" y="18" width={Math.abs(b)/max*390} height="10" fill="#70b5b2" />
                </svg>
              </div>
            })}
            <p className="text-xs text-mute">Orange: left. Teal: right. Spatial summaries only; these differences do not establish scientific equivalence.</p>
            {cmp.data.data.rows.some((r) => r.key === 'local_relief_m') && leftMeta.data?.data.extent && rightMeta.data?.data.extent &&
              <Notice tone="warn" title="Relief depends on AOI extent">
                {id}: ≈ {leftMeta.data.data.extent.east_west_km} × {leftMeta.data.data.extent.north_south_km} km; {other}: ≈ {rightMeta.data.data.extent.east_west_km} × {rightMeta.data.data.extent.north_south_km} km.
                Max − min relief over areas of different size is not directly comparable; the measured run reports this as AOI_EXTENT_MISMATCH.
              </Notice>}
          </div>}
          {stage !== 'raw' && leftMeta.data?.data.distributions && rightMeta.data?.data.distributions && <div className="mb-5">
            <p className="mb-2 text-xs uppercase tracking-wider text-mute">Distributions across analysis blocks</p>
            <Distributions sets={[{ name: id, tone: '#e79d61', d: leftMeta.data.data.distributions }, { name: other, tone: '#70b5b2', d: rightMeta.data.data.distributions }]} />
          </div>}
          {common.length === 0 ? <Empty>These datasets share no comparable columns at this stage.</Empty> : (
            <Scroll><table className="tbl"><thead><tr><th rowSpan={2}>Record</th>{use.map((c) => <th key={c} colSpan={2} className="text-center">{c}</th>)}</tr><tr>{use.map((c) => <Fragment key={c}><th>left</th><th>right</th></Fragment>)}</tr></thead>
              <tbody>{cmp.data.data.rows.map((r) => <tr key={r.key}><td className="mono text-xs">{r.key}</td>{use.map((c) => { const a = r.left?.[c], b = r.right?.[c], diff = r.left && r.right && a !== b; const f = (v: unknown, has: boolean) => (!has ? <span className="text-mute">absent</span> : v == null ? <span className="text-mute">null</span> : String(v))
                return <Fragment key={c}><td className={`mono text-xs ${diff ? 'text-warn' : ''}`}>{f(a, !!r.left)}</td><td key={c + 'r'} className={`mono text-xs ${diff ? 'text-warn' : ''}`}>{f(b, !!r.right)}</td></Fragment> })}</tr>)}</tbody></table></Scroll>)}
        </Panel>)}
    </div>
  )
}
