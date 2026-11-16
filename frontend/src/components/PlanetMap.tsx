import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Body } from '@/lib/types'
import { bodyAccent } from '@/lib/regions'
import { ClickTracker, round4 } from '@/lib/picking'

export interface Pin { id: string; label: string; lon: number; lat: number; rank?: number | null; eligible?: boolean; kind?: 'candidate' | 'stored' }
/** A transient selection marker (the user's picked point); drawn on top and never used to fit the view. */
export interface Marker { lon: number; lat: number; label: string }
export interface Footprint { id: string; label: string; bbox: number[]; kind?: string }

/**
 * Whether a pin's name is drawn permanently. Only the top three ranked candidates (or every pin when there are at most
 * three) keep a label; the rest show it on hover, so dense candidate clusters do not overprint each other.
 * With ranks withheld no pin is preferred, so the withheld ranking cannot leak through which labels are drawn.
 */
export const pinLabelShown = (p: Pin, all: Pin[]) => all.length <= 3 || (p.rank != null && p.rank <= 3)

const W = 720, H = 360
export const MIN_SPAN = 0.2
/** Mean radii (km) for the on-map scale readout only. */
export const RADIUS_KM: Partial<Record<Body, number>> = { Moon: 1737.4, Mars: 3389.5 }

/** NASA Trek global mosaics in geographic (equirectangular) tiling: level z has 2^(z+1) x 2^z tiles of 180/2^z degrees,
 *  top-left at (-180, 90), east-positive longitude, matching this map's planetocentric frame. Display only. */
export const BASEMAPS: Partial<Record<Body, { name: string; url: string; maxZoom: number; credit: string }>> = {
  Mars: { name: 'Viking MDIM 2.1 colour mosaic', maxZoom: 7, credit: 'NASA / USGS Viking MDIM 2.1 via NASA Trek',
    url: 'https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg' },
  Moon: { name: 'LRO WAC global mosaic', maxZoom: 8, credit: 'NASA / GSFC / Arizona State Univ. LRO WAC via NASA Trek',
    url: 'https://trek.nasa.gov/tiles/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0/default/default028mm/{z}/{y}/{x}.jpg' },
}
export const tileUrl = (body: Body, z: number, row: number, col: number) =>
  BASEMAPS[body]!.url.replace('{z}', String(z)).replace('{y}', String(row)).replace('{x}', String(col))

/** View = centre (lon, lat) and longitude span across the map width; latitude span is span/2 (equal degrees per pixel). */
export interface View { cx: number; cy: number; span: number }
export function clampView(v: View): View {
  const span = Math.min(360, Math.max(MIN_SPAN, v.span))
  const hx = span / 2, hy = span / 4
  return { span, cx: Math.min(180 - hx, Math.max(-180 + hx, v.cx)), cy: Math.min(90 - hy, Math.max(-90 + hy, v.cy)) }
}
/** Map a viewBox coordinate back to planetocentric lon/lat (inverse of the render transform). */
export function viewBoxToLonLat(v: View, px: number, py: number) {
  const b = bounds(v)
  return { lon: b.x0 + (px / W) * v.span, lat: b.y1 - (py / H) * (v.span / 2) }
}
const bounds = (v: View) => ({ x0: v.cx - v.span / 2, x1: v.cx + v.span / 2, y0: v.cy - v.span / 4, y1: v.cy + v.span / 4 })

/** Zoom by `factor` keeping the map point under viewBox coordinate (px, py) fixed. */
export function zoomAt(v: View, factor: number, px: number, py: number): View {
  const b = bounds(v)
  const lon = b.x0 + (px / W) * v.span, lat = b.y1 - (py / H) * (v.span / 2)
  const span = Math.min(360, Math.max(MIN_SPAN, v.span / factor))
  const x0 = lon - (px / W) * span, y1 = lat + (py / H) * (span / 2)
  return clampView({ span, cx: x0 + span / 2, cy: y1 - span / 4 })
}
export const panBy = (v: View, dpx: number, dpy: number): View =>
  clampView({ ...v, cx: v.cx - (dpx / W) * v.span, cy: v.cy + (dpy / H) * (v.span / 2) })

export function fitView(pins: Pin[], footprints: Footprint[]): View {
  const pts: number[][] = []
  for (const p of pins) pts.push([p.lon, p.lat])
  for (const f of footprints) pts.push([f.bbox[0], f.bbox[1]], [f.bbox[2], f.bbox[3]])
  if (pts.length === 0) return { cx: 0, cy: 0, span: 360 }
  const x0 = Math.min(...pts.map((p) => p[0])), x1 = Math.max(...pts.map((p) => p[0]))
  const y0 = Math.min(...pts.map((p) => p[1])), y1 = Math.max(...pts.map((p) => p[1]))
  const span = Math.max((x1 - x0) * 1.6, (y1 - y0) * 3.2, 4)
  return clampView({ cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, span })
}

function basemapTiles(body: Body, v: View) {
  const bm = BASEMAPS[body]
  if (!bm) return []
  const b = bounds(v)
  const z = Math.max(0, Math.min(bm.maxZoom, Math.ceil(Math.log2((W * 180) / (v.span * 256)))))
  const deg = 180 / 2 ** z, cols = 2 ** (z + 1), rows = 2 ** z
  const c0 = Math.max(0, Math.floor((b.x0 + 180) / deg)), c1 = Math.min(cols - 1, Math.floor((b.x1 + 180 - 1e-9) / deg))
  const r0 = Math.max(0, Math.floor((90 - b.y1) / deg)), r1 = Math.min(rows - 1, Math.floor((90 - b.y0 - 1e-9) / deg))
  const tiles: Array<{ key: string; href: string; lon: number; lat: number; deg: number }> = []
  for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++)
    tiles.push({ key: `${z}/${r}/${c}`, href: tileUrl(body, z, r, c), lon: -180 + c * deg, lat: 90 - r * deg, deg })
  return tiles.slice(0, 120)
}

const STEPS = [30, 10, 5, 2, 1, 0.5, 0.2, 0.1, 0.05, 0.02]
export const gridStep = (span: number) => STEPS.find((s) => span / s >= 4) ?? STEPS[STEPS.length - 1]
export const fmtDeg = (v: number, step: number) => `${Number(v.toFixed(step >= 1 ? 0 : step >= 0.1 ? 1 : 2))}°`

export function MapButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" aria-label={label} title={label} onClick={onClick}
    className="grid h-8 w-8 place-items-center rounded-md border border-line bg-panel/90 text-sm text-ivory backdrop-blur hover:border-ember hover:text-ember">{children}</button>
}

/** Equirectangular map for Moon/Mars: planetocentric east longitude, −180…180, with an optional NASA mosaic of the same body.
 *  Wheel / pinch / double-click / +− keys zoom, drag / arrow keys pan. No Earth imagery is ever shown on another body. */
export default function PlanetMap({ body, pins, footprints, layers, onPick, extraPins = [], extraFootprints = [], marker }: { body: Body; pins: Pin[]; footprints: Footprint[]; layers: { pins: boolean; footprints: boolean; graticule: boolean; basemap?: boolean }; onPick?: (lon: number, lat: number) => void; extraPins?: Pin[]; extraFootprints?: Footprint[]; marker?: Marker | null }) {
  const fitted = useMemo(() => fitView(pins, footprints), [pins, footprints])
  const [view, setView] = useState<View>(fitted)
  useEffect(() => setView(fitted), [fitted, body])
  const svgRef = useRef<SVGSVGElement>(null)
  const pointers = useRef(new Map<number, { x: number; y: number }>())
  const pinch = useRef<number | null>(null)
  const click = useRef(new ClickTracker())

  const toViewBox = useCallback((clientX: number, clientY: number) => {
    const r = svgRef.current!.getBoundingClientRect()
    return { x: ((clientX - r.left) / r.width) * W, y: ((clientY - r.top) / r.height) * H, scale: W / r.width }
  }, [])

  // Non-passive wheel listener so the page does not scroll while zooming the map.
  useEffect(() => {
    const el = svgRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const p = toViewBox(e.clientX, e.clientY)
      setView((v) => zoomAt(v, Math.exp(-e.deltaY * 0.0015), p.x, p.y))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [toViewBox])

  const onPointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    click.current.down(e.clientX, e.clientY, pointers.current.size)
    pinch.current = null
  }
  const onPointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const prev = pointers.current.get(e.pointerId)
    if (!prev) return
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    click.current.move(e.clientX, e.clientY)
    const pts = [...pointers.current.values()]
    if (pts.length >= 2) {
      const [a, b] = pts
      const dist = Math.hypot(a.x - b.x, a.y - b.y)
      if (pinch.current) {
        const mid = toViewBox((a.x + b.x) / 2, (a.y + b.y) / 2)
        const f = dist / pinch.current
        setView((v) => zoomAt(v, f, mid.x, mid.y))
      }
      pinch.current = dist
      return
    }
    const { scale } = toViewBox(e.clientX, e.clientY)
    const dx = (e.clientX - prev.x) * scale, dy = (e.clientY - prev.y) * scale
    if (dx || dy) setView((v) => panBy(v, dx, dy))
  }
  const onPointerUp = (e: React.PointerEvent<SVGSVGElement>) => {
    const wasClick = e.type === 'pointerup' && pointers.current.size === 1 && click.current.up(e.clientX, e.clientY)
    pointers.current.delete(e.pointerId); pinch.current = null
    if (wasClick && onPick) {
      const p = toViewBox(e.clientX, e.clientY)
      const ll = viewBoxToLonLat(view, p.x, p.y)
      if (ll.lon >= -180 && ll.lon <= 180 && ll.lat >= -90 && ll.lat <= 90) onPick(round4(ll.lon), round4(ll.lat))
    }
  }
  const onDoubleClick = (e: React.MouseEvent<SVGSVGElement>) => { const p = toViewBox(e.clientX, e.clientY); setView((v) => zoomAt(v, e.shiftKey ? 0.5 : 2, p.x, p.y)) }
  const onKeyDown = (e: React.KeyboardEvent) => {
    const act: Record<string, (v: View) => View> = {
      '+': (v) => zoomAt(v, 1.5, W / 2, H / 2), '=': (v) => zoomAt(v, 1.5, W / 2, H / 2), '-': (v) => zoomAt(v, 1 / 1.5, W / 2, H / 2),
      ArrowLeft: (v) => panBy(v, 60, 0), ArrowRight: (v) => panBy(v, -60, 0), ArrowUp: (v) => panBy(v, 0, 60), ArrowDown: (v) => panBy(v, 0, -60),
      '0': () => fitted,
    }
    if (act[e.key]) { e.preventDefault(); setView(act[e.key]) }
  }

  const b = bounds(view)
  const X = (lon: number) => ((lon - b.x0) / view.span) * W
  const Y = (lat: number) => ((b.y1 - lat) / (view.span / 2)) * H
  const step = gridStep(view.span)
  const lons: number[] = [], lats: number[] = []
  for (let i = Math.ceil(b.x0 / step); i * step <= b.x1; i++) lons.push(i * step)
  for (let i = Math.ceil(b.y0 / step); i * step <= b.y1; i++) lats.push(i * step)
  const accent = bodyAccent[body]
  const showBasemap = layers.basemap !== false && !!BASEMAPS[body]
  const tiles = useMemo(() => (showBasemap ? basemapTiles(body, view) : []), [showBasemap, body, view])
  const radius = RADIUS_KM[body]
  const widthKm = radius ? (view.span * Math.PI / 180) * radius * Math.cos((view.cy * Math.PI) / 180) : null

  return (
    <div>
      <div className="relative" tabIndex={0} onKeyDown={onKeyDown} aria-label={`${body} map. Drag or use arrow keys to pan; scroll, pinch, double-click or plus and minus keys to zoom; 0 fits to features.`}>
        <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${body} equirectangular map, planetocentric east longitude`}
          className={`w-full ${onPick ? 'cursor-crosshair' : 'cursor-grab'} touch-none select-none rounded-md border border-line active:cursor-grabbing`}
          style={{ background: `radial-gradient(ellipse at 40% 30%, ${accent}22, #0b0a09 70%)` }}
          onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp} onDoubleClick={onDoubleClick}>
          {tiles.length > 0 && <g opacity="0.85">{tiles.map((t) => <image key={t.key} href={t.href} x={X(t.lon)} y={Y(t.lat)} width={X(t.lon + t.deg) - X(t.lon) + 0.5} height={Y(t.lat - t.deg) - Y(t.lat) + 0.5} preserveAspectRatio="none" />)}</g>}
          {layers.graticule && <g stroke="#2c2824" strokeWidth="0.7">{lons.map((v) => <g key={'x' + v}><line x1={X(v)} x2={X(v)} y1="0" y2={H} /><text x={X(v) + 3} y={H - 4} fill="#8a8274" fontSize="9" stroke="none">{fmtDeg(v, step)}</text></g>)}{lats.map((v) => <g key={'y' + v}><line y1={Y(v)} y2={Y(v)} x1="0" x2={W} /><text x="4" y={Y(v) - 3} fill="#8a8274" fontSize="9" stroke="none">{fmtDeg(v, step)}</text></g>)}</g>}
          {layers.footprints && [...footprints, ...extraFootprints].map((f) => { const x = X(f.bbox[0]), y = Y(f.bbox[3]), w = Math.max(12, X(f.bbox[2]) - x), h = Math.max(12, Y(f.bbox[1]) - y)
            return <g key={f.id}><rect x={x} y={y} width={w} height={h} fill={accent} fillOpacity="0.18" stroke={accent} strokeWidth="1.5" strokeDasharray="4 3" /><text x={x + w + 5} y={y + 10} fill="#efe7d6" fontSize="11">{f.label}</text></g> })}
          {layers.pins && extraPins.map((p) => <g key={p.id} transform={`translate(${X(p.lon)} ${Y(p.lat)})`}><title>{p.label}</title><rect x="-4" y="-4" width="8" height="8" transform="rotate(45)" fill="#0b0a09" fillOpacity="0.6" stroke="#efe7d6" strokeWidth="1.2" /></g>)}
          {layers.pins && pins.map((p) => <g key={p.id} className="group" transform={`translate(${X(p.lon)} ${Y(p.lat)})`}><title>{p.label}</title><circle r="8" fill={p.eligible === false ? '#1b1815' : accent} stroke="#efe7d6" strokeWidth="1.3" /><text y="3.5" textAnchor="middle" fontSize="10" fontWeight="600" fill={p.eligible === false ? '#efe7d6' : '#0b0a09'}>{p.rank ?? (p.eligible === false ? '×' : '•')}</text><text x="12" y="4" fill="#efe7d6" fontSize="11" className={pinLabelShown(p, pins) ? undefined : 'opacity-0 group-hover:opacity-100'}>{p.label}</text></g>)}
          {marker && <g transform={`translate(${X(marker.lon)} ${Y(marker.lat)})`} pointerEvents="none"><circle r="11" fill="none" stroke="#efe7d6" strokeWidth="1.5" /><circle r="3" fill="#c8642b" stroke="#efe7d6" strokeWidth="1" /><line x1="-16" x2="-12" stroke="#efe7d6" strokeWidth="1.5" /><line x1="12" x2="16" stroke="#efe7d6" strokeWidth="1.5" /><line y1="-16" y2="-12" stroke="#efe7d6" strokeWidth="1.5" /><line y1="12" y2="16" stroke="#efe7d6" strokeWidth="1.5" /><text x="18" y="-8" fill="#efe7d6" fontSize="11" fontWeight="600">{marker.label}</text></g>}
        </svg>
        <div className="absolute right-2 top-2 flex flex-col gap-1">
          <MapButton label="Zoom in" onClick={() => setView((v) => zoomAt(v, 2, W / 2, H / 2))}>+</MapButton>
          <MapButton label="Zoom out" onClick={() => setView((v) => zoomAt(v, 0.5, W / 2, H / 2))}>−</MapButton>
          <MapButton label="Fit to features" onClick={() => setView(fitted)}>⤢</MapButton>
          <MapButton label="Whole body" onClick={() => setView({ cx: 0, cy: 0, span: 360 })}>◯</MapButton>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-mute">
        <span>{body} · planetocentric east longitude (−180…180) · equirectangular · {showBasemap ? `basemap: ${BASEMAPS[body]!.credit} (display only, not used in analysis)` : 'no imagery basemap'}</span>
        <span className="mono">centre {view.cx.toFixed(2)}°, {view.cy.toFixed(2)}° · {view.span < 1 ? view.span.toFixed(2) : view.span.toFixed(0)}° across{widthKm != null ? ` ≈ ${widthKm < 10 ? widthKm.toFixed(1) : Math.round(widthKm).toLocaleString()} km` : ''}</span>
      </div>
      <p className="mt-1 text-xs text-mute">{onPick ? 'Click to select a site · ' : ''}Drag to pan · scroll, pinch or double-click to zoom (shift+double-click zooms out) · keys: arrows, + / −, 0 to fit.</p>
    </div>
  )
}
