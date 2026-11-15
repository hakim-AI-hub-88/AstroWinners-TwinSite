import { useMemo, useState } from 'react'
import type { Body } from '@/lib/types'
import { bodyAccent } from '@/lib/regions'

export interface Pin { id: string; label: string; lon: number; lat: number; rank?: number | null; eligible?: boolean }
export interface Footprint { id: string; label: string; bbox: number[]; kind?: string }

const W = 720, H = 360
/** Equirectangular map for Moon/Mars: planetocentric east longitude, −180…180. No Earth imagery is ever shown. */
export default function PlanetMap({ body, pins, footprints, layers }: { body: Body; pins: Pin[]; footprints: Footprint[]; layers: { pins: boolean; footprints: boolean; graticule: boolean } }) {
  const [fit, setFit] = useState(true)
  const view = useMemo(() => {
    const pts: number[][] = []
    for (const p of pins) pts.push([p.lon, p.lat])
    for (const f of footprints) { pts.push([f.bbox[0], f.bbox[1]], [f.bbox[2], f.bbox[3]]) }
    if (!fit || pts.length === 0) return { x0: -180, x1: 180, y0: -90, y1: 90 }
    let x0 = Math.min(...pts.map((p) => p[0])), x1 = Math.max(...pts.map((p) => p[0])), y0 = Math.min(...pts.map((p) => p[1])), y1 = Math.max(...pts.map((p) => p[1]))
    const spanX = Math.max(x1 - x0, 20), spanY = Math.max(y1 - y0, 10), padX = spanX * 0.25, padY = spanY * 0.35
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, sx = spanX + padX * 2, sy = spanY + padY * 2
    const s = Math.max(sx, sy * 2)
    x0 = cx - s / 2; x1 = cx + s / 2; y0 = cy - s / 4; y1 = cy + s / 4
    return { x0: Math.max(-180, x0), x1: Math.min(180, x1), y0: Math.max(-90, y0), y1: Math.min(90, y1) }
  }, [pins, footprints, fit])
  const X = (lon: number) => ((lon - view.x0) / (view.x1 - view.x0)) * W
  const Y = (lat: number) => ((view.y1 - lat) / (view.y1 - view.y0)) * H
  const step = (view.x1 - view.x0) > 200 ? 30 : (view.x1 - view.x0) > 60 ? 10 : (view.x1 - view.x0) > 20 ? 5 : 1
  const lons: number[] = [], lats: number[] = []
  for (let v = Math.ceil(view.x0 / step) * step; v <= view.x1; v += step) lons.push(v)
  for (let v = Math.ceil(view.y0 / step) * step; v <= view.y1; v += step) lats.push(v)
  const accent = bodyAccent[body]
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${body} equirectangular map, planetocentric east longitude`} className="w-full rounded-md border border-line" style={{ background: `radial-gradient(ellipse at 40% 30%, ${accent}22, #0b0a09 70%)` }}>
        {layers.graticule && <g stroke="#2c2824" strokeWidth="0.7">{lons.map((v) => <g key={'x' + v}><line x1={X(v)} x2={X(v)} y1="0" y2={H} /><text x={X(v) + 3} y={H - 4} fill="#8a8274" fontSize="9" stroke="none">{v}°</text></g>)}{lats.map((v) => <g key={'y' + v}><line y1={Y(v)} y2={Y(v)} x1="0" x2={W} /><text x="4" y={Y(v) - 3} fill="#8a8274" fontSize="9" stroke="none">{v}°</text></g>)}</g>}
        {layers.footprints && footprints.map((f) => { const x = X(f.bbox[0]), y = Y(f.bbox[3]), w = Math.max(12, X(f.bbox[2]) - x), h = Math.max(12, Y(f.bbox[1]) - y)
          return <g key={f.id}><rect x={x} y={y} width={w} height={h} fill={accent} fillOpacity="0.18" stroke={accent} strokeWidth="1.5" strokeDasharray="4 3" /><text x={x + w + 5} y={y + 10} fill="#efe7d6" fontSize="11">{f.label}</text></g> })}
        {layers.pins && pins.map((p) => <g key={p.id} transform={`translate(${X(p.lon)} ${Y(p.lat)})`}><circle r="8" fill={p.eligible === false ? '#1b1815' : accent} stroke="#efe7d6" strokeWidth="1.3" /><text y="3.5" textAnchor="middle" fontSize="10" fontWeight="600" fill={p.eligible === false ? '#efe7d6' : '#0b0a09'}>{p.rank ?? '×'}</text><text x="12" y="4" fill="#efe7d6" fontSize="11">{p.label}</text></g>)}
      </svg>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-mute">
        <span>{body} · planetocentric east longitude (−180…180) · equirectangular · no imagery basemap</span>
        <button className="underline" onClick={() => setFit(!fit)}>{fit ? 'Show whole body' : 'Fit to features'}</button>
      </div>
    </div>
  )
}
