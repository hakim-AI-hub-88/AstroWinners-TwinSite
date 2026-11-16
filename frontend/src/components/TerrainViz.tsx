import { useEffect, useMemo, useRef, useState } from 'react'
import type { DatasetGrid, FeatureDistribution } from '@/lib/types'

// Sequential ramp inside the TwinSite palette: ink → ember → warm ivory. Low = dark, high = light.
const RAMP: Array<[number, [number, number, number]]> = [
  [0, [27, 24, 21]], [0.35, [143, 71, 32]], [0.65, [200, 100, 43]], [1, [239, 231, 214]],
]
function ramp(t: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, t))
  for (let i = 1; i < RAMP.length; i++) {
    const [t1, c1] = RAMP[i], [t0, c0] = RAMP[i - 1]
    if (x <= t1) { const f = (x - t0) / (t1 - t0); return [0, 1, 2].map((k) => Math.round(c0[k] + f * (c1[k] - c0[k]))) as [number, number, number] }
  }
  return RAMP[RAMP.length - 1][1]
}
const fmt = (v: number, d = 1) => v.toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d })

/** Elevation heatmap of a cleaned grid (display aggregation stated by the server). Null cells stay transparent. */
export function GridHeatmap({ grid }: { grid: DatasetGrid }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const { nrows, ncols, values, min, max, first_center, step_deg } = grid.display
  const [hover, setHover] = useState<{ lon: number; lat: number; v: number | null } | null>(null)
  useEffect(() => {
    const ctx = ref.current?.getContext('2d')
    if (!ctx || min == null || max == null) return
    const img = ctx.createImageData(ncols, nrows)
    values.forEach((v, i) => {
      const o = i * 4
      if (v == null) { img.data[o + 3] = 0; return }
      const [r, g, b] = ramp(max === min ? 0.5 : (v - min) / (max - min))
      img.data.set([r, g, b, 255], o)
    })
    ctx.putImageData(img, 0, 0)
  }, [values, nrows, ncols, min, max])
  const center = (r: number, c: number) => ({ lon: first_center[0] + c * step_deg[0], lat: first_center[1] - r * step_deg[1] })
  const nw = center(0, 0), se = center(nrows - 1, ncols - 1)
  const onMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    const c = Math.min(ncols - 1, Math.floor(((e.clientX - box.left) / box.width) * ncols))
    const r = Math.min(nrows - 1, Math.floor(((e.clientY - box.top) / box.height) * nrows))
    setHover({ ...center(r, c), v: values[r * ncols + c] })
  }
  // Equirectangular cells: true ground aspect = (E-W extent * cos(latitude)) / N-S extent.
  const midLat = (nw.lat + se.lat) / 2
  const aspect = (ncols * step_deg[0] * Math.cos((midLat * Math.PI) / 180)) / (nrows * step_deg[1])
  if (min == null || max == null) return <p className="text-sm text-mute">No valid cells in this grid.</p>
  return (
    <figure className="space-y-2">
      <div className="relative mx-auto max-w-md">
        <canvas ref={ref} width={ncols} height={nrows} onMouseMove={onMove} onMouseLeave={() => setHover(null)}
          role="img" aria-label={`Cleaned elevation grid ${nrows} by ${ncols} cells, ${fmt(min)} to ${fmt(max)} ${grid.unit}`}
          className="block w-full rounded border border-line" style={{ aspectRatio: String(aspect), imageRendering: 'pixelated', background: 'repeating-linear-gradient(45deg,#1b1815 0 4px,#141210 4px 8px)' }} />
        <div className="mono mt-1 flex justify-between text-[0.65rem] text-mute"><span>{fmt(nw.lon, 3)}°, {fmt(nw.lat, 3)}°</span><span>{fmt(se.lon, 3)}°, {fmt(se.lat, 3)}°</span></div>
      </div>
      <div className="mx-auto max-w-md">
        <div className="h-2 rounded" style={{ background: `linear-gradient(90deg, ${RAMP.map(([t, c]) => `rgb(${c.join(',')}) ${t * 100}%`).join(',')})` }} />
        <div className="mono mt-1 flex justify-between text-[0.65rem] text-mute"><span>{fmt(min)} {grid.unit}</span><span>{grid.vertical_datum}</span><span>{fmt(max)} {grid.unit}</span></div>
        <p className="mono mt-2 h-4 text-xs text-ivory-dim" aria-live="polite">{hover ? `${fmt(hover.lon, 4)}°, ${fmt(hover.lat, 4)}° · ${hover.v == null ? 'no data' : `${fmt(hover.v)} ${grid.unit}`}` : 'Hover the grid to read a cell.'}</p>
      </div>
      <figcaption className="text-xs text-mute">{grid.method} North is up and the frame keeps the true ground aspect ratio; corner labels are the centres of the corner display cells.</figcaption>
    </figure>
  )
}

/** Horizontal box plot (p10–p90 box, median line, mean dot, min/max whiskers) on a shared axis. */
export function BoxRow({ label, s, lo, hi, tone }: { label: string; s: FeatureDistribution; lo: number; hi: number; tone: string }) {
  const W = 400, x = (v?: number) => (v == null || hi === lo ? 0 : ((v - lo) / (hi - lo)) * W)
  if (s.p10 == null || s.p90 == null || s.median == null) return null
  return (
    <div className="grid grid-cols-[minmax(5rem,12rem)_1fr] items-center gap-2">
      <span className="truncate text-xs text-ivory-dim" title={label}>{label}</span>
      <svg viewBox={`0 0 ${W} 22`} className="h-6 w-full overflow-visible" role="img"
        aria-label={`${label}: min ${s.min}, p10 ${s.p10}, median ${s.median}, mean ${s.mean}, p90 ${s.p90}, max ${s.max}, n ${s.n}`}>
        <line x1={x(s.min)} x2={x(s.max)} y1={11} y2={11} stroke="var(--color-mute)" strokeWidth={1} />
        <rect x={x(s.p10)} y={4} width={Math.max(1, x(s.p90) - x(s.p10))} height={14} rx={2} fill={tone} fillOpacity={0.35} stroke={tone} />
        <line x1={x(s.median)} x2={x(s.median)} y1={3} y2={19} stroke="var(--color-ivory)" strokeWidth={2} />
        {s.mean != null && <circle cx={x(s.mean)} cy={11} r={3} fill={tone} stroke="var(--color-ink)" />}
      </svg>
    </div>
  )
}

const FEATURE_LABEL: Record<string, string> = { slope_deg: 'Slope (degree)', roughness_m: 'Roughness (m)', local_relief_m: 'Block elevation (m)' }

/** Per-feature distributions for one or two datasets on a shared axis per feature. */
export function Distributions({ sets }: { sets: Array<{ name: string; tone: string; d: Record<string, FeatureDistribution> }> }) {
  const features = useMemo(() => [...new Set(sets.flatMap((s) => Object.keys(s.d)))].sort(), [sets])
  return (
    <div className="space-y-5">
      {features.map((f) => {
        const all = sets.map((s) => s.d[f]).filter(Boolean)
        // Relief stats are absolute block elevations on body-specific datums: never drawn on a shared axis.
        const shared = f !== 'local_relief_m'
        return (
          <div key={f}>
            <p className="mb-1 text-xs uppercase tracking-wider text-mute">{FEATURE_LABEL[f] ?? f}</p>
            <div className="space-y-1">
              {sets.map((s) => {
                const st = s.d[f]
                if (!st) return <p key={s.name} className="text-xs text-mute">{s.name}: not available</p>
                const lo = shared ? Math.min(...all.map((a) => a.min ?? 0)) : st.min ?? 0
                const hi = shared ? Math.max(...all.map((a) => a.max ?? 0)) : st.max ?? 1
                return <BoxRow key={s.name} label={`${s.name} · n=${st.n ?? '?'}`} s={st} lo={lo} hi={hi} tone={s.tone} />
              })}
            </div>
            {!shared && <p className="mt-1 text-xs text-mute">Absolute elevations on different vertical datums; each row has its own axis. Relief values (max − min) depend on AOI extent.</p>}
          </div>
        )
      })}
      <p className="text-xs text-mute">Box: p10–p90 spatial variability across analysis blocks (not instrument uncertainty). Line: median. Dot: mean, which is the published value for slope and roughness. Whiskers: min–max.</p>
    </div>
  )
}
