import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Body } from '@/lib/types'
import { bodyAccent } from '@/lib/regions'
import { BASEMAPS, MapButton, RADIUS_KM, tileUrl, type Footprint, type Pin } from './PlanetMap'

/** Orthographic 3D globe for the Moon and Mars. The NASA Trek equirectangular mosaic of the same body is assembled
 *  into one texture and inverse-projected per pixel in a fragment shader (exact orthographic projection, no mesh).
 *  Markers, footprints and the graticule are drawn on a 2D overlay with the matching forward projection. Display only. */

const D2R = Math.PI / 180
const MAX_ZOOM = 40

const VERT = 'attribute vec2 a; void main(){ gl_Position = vec4(a, 0.0, 1.0); }'
const FRAG = `precision highp float;
uniform sampler2D tex; uniform vec2 res; uniform float R; uniform vec2 center; uniform float hasTex; uniform vec3 tint;
const float PI = 3.141592653589793;
void main(){
  vec2 p = gl_FragCoord.xy - 0.5 * res;
  float x = p.x / R, y = p.y / R, rho2 = x * x + y * y;
  if (rho2 > 1.0) { float g = smoothstep(1.07, 1.0, sqrt(rho2)) * 0.22; gl_FragColor = vec4(tint * g, g); return; }
  float z = sqrt(1.0 - rho2);                          // cos(c): 1 at centre, 0 at limb
  float lat0 = center.y, lon0 = center.x;
  float lat = asin(clamp(z * sin(lat0) + y * cos(lat0), -1.0, 1.0));
  float lon = lon0 + atan(x, z * cos(lat0) - y * sin(lat0));
  vec2 uv = vec2((lon + PI) / (2.0 * PI), (0.5 * PI - lat) / PI);
  vec3 c = hasTex > 0.5 ? texture2D(tex, uv).rgb : tint * 0.35;
  gl_FragColor = vec4(c * (0.35 + 0.65 * pow(z, 0.6)), 1.0);
}`

interface Orient { lon0: number; lat0: number; zoom: number }

/** Forward orthographic projection; x/y on the unit disk, visible when cosc > 0. */
export function project(o: Orient, lon: number, lat: number) {
  const f = lat * D2R, l = (lon - o.lon0) * D2R, f0 = o.lat0 * D2R
  const cosc = Math.sin(f0) * Math.sin(f) + Math.cos(f0) * Math.cos(f) * Math.cos(l)
  return { x: Math.cos(f) * Math.sin(l), y: Math.cos(f0) * Math.sin(f) - Math.sin(f0) * Math.cos(f) * Math.cos(l), visible: cosc > 0 }
}
/** Inverse projection of a unit-disk point; null outside the globe. */
export function unproject(o: Orient, x: number, y: number) {
  const r2 = x * x + y * y
  if (r2 > 1) return null
  const z = Math.sqrt(1 - r2), f0 = o.lat0 * D2R
  const lat = Math.asin(Math.max(-1, Math.min(1, z * Math.sin(f0) + y * Math.cos(f0))))
  const lon = o.lon0 * D2R + Math.atan2(x, z * Math.cos(f0) - y * Math.sin(f0))
  return { lon: ((((lon / D2R) + 540) % 360) - 180), lat: lat / D2R }
}

function fitOrient(pins: Pin[], footprints: Footprint[]): Orient {
  const pts: number[][] = []
  for (const p of pins) pts.push([p.lon, p.lat])
  for (const f of footprints) pts.push([f.bbox[0], f.bbox[1]], [f.bbox[2], f.bbox[3]])
  if (!pts.length) return { lon0: 0, lat0: 15, zoom: 1 }
  const x0 = Math.min(...pts.map((p) => p[0])), x1 = Math.max(...pts.map((p) => p[0]))
  const y0 = Math.min(...pts.map((p) => p[1])), y1 = Math.max(...pts.map((p) => p[1]))
  const spanDeg = Math.max(x1 - x0, y1 - y0)
  // Visible half-width ≈ 2.17/zoom rad for a 2:1 frame; aim for features plus generous context.
  const zoom = Math.min(12, Math.max(1, 2.17 / (Math.max(spanDeg * 1.5, 15) * D2R)))
  return { lon0: (x0 + x1) / 2, lat0: (y0 + y1) / 2, zoom }
}

/** Assemble the equirectangular texture from Trek tiles at level z (2^(z+1) x 2^z tiles of 256 px).
 *  `base` (a coarser mosaic) is upscaled first so the globe never goes blank while finer tiles arrive. */
function loadMosaic(body: Body, z: number, base: HTMLCanvasElement | null, onUpdate: (c: HTMLCanvasElement) => void) {
  const cols = 2 ** (z + 1), rows = 2 ** z
  const canvas = document.createElement('canvas')
  canvas.width = cols * 256; canvas.height = rows * 256
  const ctx = canvas.getContext('2d')!
  if (base) ctx.drawImage(base, 0, 0, canvas.width, canvas.height)
  let cancelled = false, timer: number | null = null
  const flush = () => { timer = null; if (!cancelled) onUpdate(canvas) }
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => { if (cancelled) return; ctx.drawImage(img, c * 256, r * 256); if (timer == null) timer = window.setTimeout(flush, 150) }
    img.src = tileUrl(body, z, r, c)
  }
  return () => { cancelled = true; if (timer != null) clearTimeout(timer) }
}

export default function PlanetGlobe({ body, pins, footprints, layers }: { body: Body; pins: Pin[]; footprints: Footprint[]; layers: { pins: boolean; footprints: boolean; graticule: boolean; basemap?: boolean } }) {
  const wrap = useRef<HTMLDivElement>(null)
  const glCanvas = useRef<HTMLCanvasElement>(null)
  const overlay = useRef<HTMLCanvasElement>(null)
  const gl = useRef<{ ctx: WebGLRenderingContext; prog: WebGLProgram; tex: WebGLTexture; hasTex: boolean } | null>(null)
  const fitted = useMemo(() => fitOrient(pins, footprints), [pins, footprints])
  const orient = useRef<Orient>(fitted)
  const [readout, setReadout] = useState<Orient>(fitted)
  const [glError, setGlError] = useState(false)
  const [texLevel, setTexLevel] = useState(0)
  const mosaic = useRef<{ body: Body; canvas: HTMLCanvasElement } | null>(null)
  const frame = useRef<number | null>(null)
  const accent = bodyAccent[body]
  const showBasemap = layers.basemap !== false && !!BASEMAPS[body]

  const draw = useCallback(() => {
    frame.current = null
    const w = wrap.current, c = glCanvas.current, ov = overlay.current
    if (!w || !c || !ov) return
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const cssW = w.clientWidth, cssH = Math.round(cssW / 2)
    for (const el of [c, ov]) { if (el.width !== Math.round(cssW * dpr)) { el.width = Math.round(cssW * dpr); el.height = Math.round(cssH * dpr) } el.style.height = `${cssH}px` }
    const o = orient.current
    const Rcss = o.zoom * cssH * 0.46
    const g = gl.current
    if (g) {
      const { ctx } = g
      ctx.viewport(0, 0, c.width, c.height)
      ctx.clearColor(0, 0, 0, 0); ctx.clear(ctx.COLOR_BUFFER_BIT)
      ctx.uniform2f(ctx.getUniformLocation(g.prog, 'res'), c.width, c.height)
      ctx.uniform1f(ctx.getUniformLocation(g.prog, 'R'), Rcss * dpr)
      ctx.uniform2f(ctx.getUniformLocation(g.prog, 'center'), o.lon0 * D2R, o.lat0 * D2R)
      ctx.uniform1f(ctx.getUniformLocation(g.prog, 'hasTex'), g.hasTex && showBasemap ? 1 : 0)
      const hex = accent.replace('#', '')
      ctx.uniform3f(ctx.getUniformLocation(g.prog, 'tint'), parseInt(hex.slice(0, 2), 16) / 255, parseInt(hex.slice(2, 4), 16) / 255, parseInt(hex.slice(4, 6), 16) / 255)
      ctx.drawArrays(ctx.TRIANGLES, 0, 6)
    }
    // Overlay in CSS pixels.
    const o2 = ov.getContext('2d')!
    o2.setTransform(dpr, 0, 0, dpr, 0, 0)
    o2.clearRect(0, 0, cssW, cssH)
    const cx = cssW / 2, cy = cssH / 2
    const S = (lon: number, lat: number) => { const p = project(o, lon, lat); return { x: cx + p.x * Rcss, y: cy - p.y * Rcss, v: p.visible } }
    const polyline = (pts: Array<{ x: number; y: number; v: boolean }>) => {
      o2.beginPath(); let pen = false
      for (const p of pts) { if (!p.v) { pen = false; continue } if (pen) o2.lineTo(p.x, p.y); else { o2.moveTo(p.x, p.y); pen = true } }
      o2.stroke()
    }
    if (layers.graticule) {
      const step = o.zoom > 8 ? 2 : o.zoom > 3 ? 5 : o.zoom > 1.5 ? 10 : 30, res = Math.min(2, step / 4)
      o2.strokeStyle = 'rgba(239,231,214,0.18)'; o2.lineWidth = 0.7
      for (let lon = -180; lon < 180; lon += step) { const pts = []; for (let lat = -90; lat <= 90; lat += res) pts.push(S(lon, lat)); polyline(pts) }
      for (let lat = -90 + step; lat < 90; lat += step) { const pts = []; for (let lon = -180; lon <= 180; lon += res) pts.push(S(lon, lat)); polyline(pts) }
    }
    o2.font = '11px Inter, ui-sans-serif, system-ui'
    if (layers.footprints) for (const f of footprints) {
      const [w0, s0, e0, n0] = f.bbox, n = 24, ring: Array<{ x: number; y: number; v: boolean }> = []
      for (let i = 0; i <= n; i++) ring.push(S(w0 + ((e0 - w0) * i) / n, s0))
      for (let i = 0; i <= n; i++) ring.push(S(e0, s0 + ((n0 - s0) * i) / n))
      for (let i = 0; i <= n; i++) ring.push(S(e0 - ((e0 - w0) * i) / n, n0))
      for (let i = 0; i <= n; i++) ring.push(S(w0, n0 - ((n0 - s0) * i) / n))
      if (!ring.some((p) => p.v)) continue
      const xs = ring.filter((p) => p.v).map((p) => p.x), ys = ring.filter((p) => p.v).map((p) => p.y)
      o2.strokeStyle = accent; o2.lineWidth = 1.5; o2.setLineDash([4, 3])
      if (Math.max(...xs) - Math.min(...xs) < 8) {
        const c0 = S((w0 + e0) / 2, (s0 + n0) / 2); o2.strokeRect(c0.x - 6, c0.y - 6, 12, 12)
      } else { o2.fillStyle = accent + '2e'; o2.beginPath(); ring.filter((p) => p.v).forEach((p, i) => (i ? o2.lineTo(p.x, p.y) : o2.moveTo(p.x, p.y))); o2.closePath(); o2.fill(); o2.stroke() }
      o2.setLineDash([]); o2.fillStyle = '#efe7d6'; o2.fillText(f.label, Math.max(...xs) + 8, Math.min(...ys) + 10)
    }
    if (layers.pins) for (const p of pins) {
      const s = S(p.lon, p.lat)
      if (!s.v) continue
      o2.beginPath(); o2.arc(s.x, s.y, 8, 0, 2 * Math.PI); o2.fillStyle = p.eligible === false ? '#1b1815' : accent; o2.fill()
      o2.lineWidth = 1.3; o2.strokeStyle = '#efe7d6'; o2.stroke()
      o2.fillStyle = p.eligible === false ? '#efe7d6' : '#0b0a09'; o2.textAlign = 'center'; o2.fillText(String(p.rank ?? '×'), s.x, s.y + 4)
      o2.textAlign = 'left'; o2.fillStyle = '#efe7d6'; o2.fillText(p.label, s.x + 12, s.y + 4)
    }
  }, [accent, footprints, layers.footprints, layers.graticule, layers.pins, pins, showBasemap])

  const request = useCallback(() => { if (frame.current == null) frame.current = requestAnimationFrame(draw) }, [draw])
  const update = useCallback((fn: (o: Orient) => Orient) => {
    const n = fn(orient.current)
    orient.current = { lon0: ((n.lon0 + 540) % 360) - 180, lat0: Math.max(-89.9, Math.min(89.9, n.lat0)), zoom: Math.max(0.8, Math.min(MAX_ZOOM, n.zoom)) }
    setReadout(orient.current)
    if (orient.current.zoom > 3 && texLevel < 3) setTexLevel(3)
    request()
  }, [request, texLevel])

  // WebGL setup once per mount.
  useEffect(() => {
    const c = glCanvas.current!
    const ctx = c.getContext('webgl', { premultipliedAlpha: false, antialias: true })
    if (!ctx) { setGlError(true); return }
    const sh = (type: number, src: string) => { const s = ctx.createShader(type)!; ctx.shaderSource(s, src); ctx.compileShader(s); return s }
    const prog = ctx.createProgram()!
    ctx.attachShader(prog, sh(ctx.VERTEX_SHADER, VERT)); ctx.attachShader(prog, sh(ctx.FRAGMENT_SHADER, FRAG)); ctx.linkProgram(prog)
    if (!ctx.getProgramParameter(prog, ctx.LINK_STATUS)) { setGlError(true); return }
    ctx.useProgram(prog)
    const buf = ctx.createBuffer(); ctx.bindBuffer(ctx.ARRAY_BUFFER, buf)
    ctx.bufferData(ctx.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), ctx.STATIC_DRAW)
    const loc = ctx.getAttribLocation(prog, 'a'); ctx.enableVertexAttribArray(loc); ctx.vertexAttribPointer(loc, 2, ctx.FLOAT, false, 0, 0)
    ctx.enable(ctx.BLEND); ctx.blendFunc(ctx.SRC_ALPHA, ctx.ONE_MINUS_SRC_ALPHA)
    const tex = ctx.createTexture()!
    ctx.bindTexture(ctx.TEXTURE_2D, tex)
    ctx.texParameteri(ctx.TEXTURE_2D, ctx.TEXTURE_WRAP_S, ctx.REPEAT)
    ctx.texParameteri(ctx.TEXTURE_2D, ctx.TEXTURE_WRAP_T, ctx.CLAMP_TO_EDGE)
    ctx.texParameteri(ctx.TEXTURE_2D, ctx.TEXTURE_MIN_FILTER, ctx.LINEAR)
    ctx.texParameteri(ctx.TEXTURE_2D, ctx.TEXTURE_MAG_FILTER, ctx.LINEAR)
    gl.current = { ctx, prog, tex, hasTex: false }
    request()
    return () => { gl.current = null }
  }, [request])

  // Texture: level 2 (2048x1024) first; level 3 (4096x2048) once the user zooms in, if the GPU allows it.
  useEffect(() => {
    const g = gl.current
    if (!g || !showBasemap) return
    const max = g.ctx.getParameter(g.ctx.MAX_TEXTURE_SIZE) as number
    const z = texLevel >= 3 && max >= 4096 ? 3 : 2
    const base = mosaic.current?.body === body ? mosaic.current.canvas : null
    return loadMosaic(body, z, base, (canvas) => {
      mosaic.current = { body, canvas }
      const cur = gl.current
      if (!cur) return
      cur.ctx.bindTexture(cur.ctx.TEXTURE_2D, cur.tex)
      cur.ctx.texImage2D(cur.ctx.TEXTURE_2D, 0, cur.ctx.RGB, cur.ctx.RGB, cur.ctx.UNSIGNED_BYTE, canvas)
      cur.hasTex = true
      request()
    })
  }, [body, showBasemap, texLevel, request])

  useEffect(() => { orient.current = fitted; setReadout(fitted); setTexLevel(fitted.zoom > 3 ? 3 : 0); request() }, [fitted, body, request])
  useEffect(() => { request() }, [draw, request])
  useEffect(() => {
    const ro = new ResizeObserver(() => request())
    if (wrap.current) ro.observe(wrap.current)
    return () => ro.disconnect()
  }, [request])

  // Interaction: drag rotates, wheel / pinch / double-click zoom.
  const pointers = useRef(new Map<number, { x: number; y: number }>())
  const pinch = useRef<number | null>(null)
  useEffect(() => {
    const el = overlay.current
    if (!el) return
    const onWheel = (e: WheelEvent) => { e.preventDefault(); update((o) => ({ ...o, zoom: o.zoom * Math.exp(-e.deltaY * 0.0015) })) }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [update])
  const radiusPx = () => orient.current.zoom * (wrap.current?.clientWidth ?? 720) / 2 * 0.46
  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => { e.currentTarget.setPointerCapture(e.pointerId); pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY }); pinch.current = null }
  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const prev = pointers.current.get(e.pointerId)
    if (!prev) return
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    const pts = [...pointers.current.values()]
    if (pts.length >= 2) {
      const d = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y)
      if (pinch.current) update((o) => ({ ...o, zoom: o.zoom * (d / pinch.current!) }))
      pinch.current = d
      return
    }
    const R = radiusPx()
    update((o) => ({ ...o, lon0: o.lon0 - ((e.clientX - prev.x) / R) / D2R / Math.max(0.25, Math.cos(o.lat0 * D2R)), lat0: o.lat0 + ((e.clientY - prev.y) / R) / D2R }))
  }
  const onPointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => { pointers.current.delete(e.pointerId); pinch.current = null }
  const onDoubleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect(), R = radiusPx()
    const hit = unproject(orient.current, (e.clientX - r.left - r.width / 2) / R, -(e.clientY - r.top - r.height / 2) / R)
    update((o) => ({ lon0: hit?.lon ?? o.lon0, lat0: hit?.lat ?? o.lat0, zoom: o.zoom * (e.shiftKey ? 0.5 : 2) }))
  }
  const onKeyDown = (e: React.KeyboardEvent) => {
    const step = 10 / orient.current.zoom
    const act: Record<string, (o: Orient) => Orient> = {
      '+': (o) => ({ ...o, zoom: o.zoom * 1.5 }), '=': (o) => ({ ...o, zoom: o.zoom * 1.5 }), '-': (o) => ({ ...o, zoom: o.zoom / 1.5 }),
      ArrowLeft: (o) => ({ ...o, lon0: o.lon0 - step }), ArrowRight: (o) => ({ ...o, lon0: o.lon0 + step }),
      ArrowUp: (o) => ({ ...o, lat0: o.lat0 + step }), ArrowDown: (o) => ({ ...o, lat0: o.lat0 - step }), '0': () => fitted,
    }
    if (act[e.key]) { e.preventDefault(); update(act[e.key]) }
  }

  if (glError) return <p className="rounded-md border border-line p-6 text-sm text-mute">3D view needs WebGL, which is unavailable in this browser. Use the 2D map.</p>
  const radius = RADIUS_KM[body]
  return (
    <div>
      <div ref={wrap} className="relative overflow-hidden rounded-md border border-line" style={{ background: 'radial-gradient(ellipse at 50% 50%, #141210, #0b0a09 70%)' }}
        tabIndex={0} onKeyDown={onKeyDown} aria-label={`${body} 3D globe. Drag or arrow keys rotate; scroll, pinch, double-click or plus and minus zoom; 0 fits to features.`}>
        <canvas ref={glCanvas} className="block w-full" role="img" aria-label={`${body} orthographic globe${showBasemap ? ` with ${BASEMAPS[body]!.name}` : ''}`} />
        <canvas ref={overlay} className="absolute inset-0 block w-full cursor-grab touch-none select-none active:cursor-grabbing"
          onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp} onDoubleClick={onDoubleClick} />
        <div className="absolute right-2 top-2 flex flex-col gap-1">
          <MapButton label="Zoom in" onClick={() => update((o) => ({ ...o, zoom: o.zoom * 2 }))}>+</MapButton>
          <MapButton label="Zoom out" onClick={() => update((o) => ({ ...o, zoom: o.zoom / 2 }))}>−</MapButton>
          <MapButton label="Fit to features" onClick={() => update(() => fitted)}>⤢</MapButton>
          <MapButton label="Whole globe" onClick={() => update((o) => ({ ...o, zoom: 1 }))}>◯</MapButton>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-mute">
        <span>{body} · orthographic globe · planetocentric east longitude · {showBasemap ? `${BASEMAPS[body]!.credit}, ${texLevel >= 3 ? '4096' : '2048'}-px mosaic (display only)` : 'no imagery basemap'}</span>
        <span className="mono">centre {readout.lon0.toFixed(2)}°, {readout.lat0.toFixed(2)}° · zoom {readout.zoom.toFixed(1)}×{radius ? ` · R ${radius.toLocaleString()} km` : ''}</span>
      </div>
      <p className="mt-1 text-xs text-mute">Drag to rotate · scroll, pinch or double-click to zoom (shift+double-click zooms out) · keys: arrows, + / −, 0 to fit. For detail beyond the mosaic resolution, use the 2D map.</p>
    </div>
  )
}
