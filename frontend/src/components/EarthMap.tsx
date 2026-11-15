import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { pinLabelShown, type Footprint, type Marker, type Pin } from './PlanetMap'

const GIBS = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg'

function fc(footprints: Footprint[]) {
  return { type: 'FeatureCollection' as const, features: footprints.map((f) => ({ type: 'Feature' as const, properties: { label: f.label },
    geometry: { type: 'Polygon' as const, coordinates: [[[f.bbox[0], f.bbox[1]], [f.bbox[2], f.bbox[1]], [f.bbox[2], f.bbox[3]], [f.bbox[0], f.bbox[3]], [f.bbox[0], f.bbox[1]]]] } })) }
}

/** Earth only (WGS84). 2D mercator or 3D globe. Basemap: NASA GIBS Blue Marble; markers still render if tiles fail. */
export default function EarthMap({ pins, footprints, globe, layers, onPick, extraPins, marker }: { pins: Pin[]; footprints: Footprint[]; globe: boolean; layers: { pins: boolean; footprints: boolean; basemap: boolean }; onPick?: (lon: number, lat: number) => void; extraPins?: Pin[]; marker?: Marker | null }) {
  const pickRef = useRef(onPick)
  pickRef.current = onPick
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const markers = useRef<maplibregl.Marker[]>([])
  const extras = useRef<maplibregl.Marker[]>([])
  const ready = useRef(false)

  useEffect(() => {
    if (!el.current) return
    const m = new maplibregl.Map({
      container: el.current, center: [10, 20], zoom: 1.4, attributionControl: { compact: true },
      style: { version: 8, sources: { bm: { type: 'raster', tiles: [GIBS], tileSize: 256, maxzoom: 8, attribution: 'Imagery: NASA GIBS / Blue Marble' }, fp: { type: 'geojson', data: fc([]) } },
        layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#0b0a09' } }, { id: 'bm', type: 'raster', source: 'bm' },
          { id: 'fp-fill', type: 'fill', source: 'fp', paint: { 'fill-color': '#c8642b', 'fill-opacity': 0.25 } }, { id: 'fp-line', type: 'line', source: 'fp', paint: { 'line-color': '#c8642b', 'line-width': 2, 'line-dasharray': [2, 1.5] } }] },
    })
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.on('load', () => { ready.current = true; m.fire('twinsite-ready' as never) })
    m.on('click', (e) => { if (pickRef.current) pickRef.current(Math.round(e.lngLat.wrap().lng * 1e4) / 1e4, Math.round(e.lngLat.lat * 1e4) / 1e4) })
    map.current = m
    return () => { markers.current.forEach((k) => k.remove()); extras.current.forEach((k) => k.remove()); m.remove(); map.current = null; ready.current = false }
  }, [])

  useEffect(() => {
    const m = map.current; if (!m) return
    const apply = () => { try { (m as unknown as { setProjection: (p: { type: string }) => void }).setProjection({ type: globe ? 'globe' : 'mercator' }) } catch { /* older engines: stay 2D */ } }
    if (ready.current) apply(); else m.once('load', apply)
  }, [globe])

  useEffect(() => {
    const m = map.current; if (!m) return
    const apply = () => {
      (m.getSource('fp') as maplibregl.GeoJSONSource | undefined)?.setData(fc(layers.footprints ? footprints : []))
      m.setLayoutProperty('bm', 'visibility', layers.basemap ? 'visible' : 'none')
      markers.current.forEach((k) => k.remove()); markers.current = []
      if (layers.pins) for (const p of pins) {
        const d = document.createElement('div')
        d.style.cssText = `display:flex;align-items:center;gap:6px;font:600 11px Inter,sans-serif;color:#efe7d6;text-shadow:0 0 3px #000`
        d.innerHTML = `<span style="width:20px;height:20px;border-radius:50%;background:${p.eligible === false ? '#1b1815' : '#c8642b'};color:${p.eligible === false ? '#efe7d6' : '#0b0a09'};border:1.5px solid #efe7d6;display:flex;align-items:center;justify-content:center">${p.rank ?? (p.eligible === false ? '×' : '•')}</span>`
        const label = document.createElement('span'); label.textContent = p.label; d.appendChild(label); d.title = p.label
        if (!pinLabelShown(p, pins)) {
          // Hover-only label: keeps dense candidate clusters readable.
          label.style.display = 'none'
          d.addEventListener('mouseenter', () => { label.style.display = ''; d.style.zIndex = '2' })
          d.addEventListener('mouseleave', () => { label.style.display = 'none'; d.style.zIndex = '' })
        }
        markers.current.push(new maplibregl.Marker({ element: d }).setLngLat([p.lon, p.lat]).addTo(m))
      }
      const pts = [...pins.map((p) => [p.lon, p.lat]), ...footprints.flatMap((f) => [[f.bbox[0], f.bbox[1]], [f.bbox[2], f.bbox[3]]])]
      if (pts.length) { const b = new maplibregl.LngLatBounds(pts[0] as [number, number], pts[0] as [number, number]); pts.forEach((p) => b.extend(p as [number, number])); m.fitBounds(b, { padding: 60, maxZoom: 6, duration: 0 }) }
    }
    if (ready.current) apply(); else m.once('load', apply)
  }, [pins, footprints, layers.pins, layers.footprints, layers.basemap])

  // Stored sites and the picked point never refit the view, so a click does not throw away the user's zoom.
  useEffect(() => {
    const m = map.current; if (!m) return
    const apply = () => {
      extras.current.forEach((k) => k.remove()); extras.current = []
      if (layers.pins) for (const p of extraPins ?? []) {
        const d = document.createElement('div'); d.title = p.label
        d.style.cssText = 'width:9px;height:9px;transform:rotate(45deg);background:rgba(11,10,9,.6);border:1.2px solid #efe7d6'
        extras.current.push(new maplibregl.Marker({ element: d }).setLngLat([p.lon, p.lat]).addTo(m))
      }
      if (marker) {
        const d = document.createElement('div')
        d.style.cssText = 'display:flex;align-items:center;gap:6px;font:600 11px Inter,sans-serif;color:#efe7d6;text-shadow:0 0 3px #000;pointer-events:none'
        d.innerHTML = '<span style="width:20px;height:20px;border-radius:50%;border:1.5px solid #efe7d6;display:flex;align-items:center;justify-content:center"><span style="width:6px;height:6px;border-radius:50%;background:#c8642b"></span></span>'
        const label = document.createElement('span'); label.textContent = marker.label; d.appendChild(label)
        extras.current.push(new maplibregl.Marker({ element: d, anchor: 'left', offset: [-10, 0] }).setLngLat([marker.lon, marker.lat]).addTo(m))
        // A point chosen outside the current view (e.g. from place search) is brought into view without changing the zoom.
        if (!m.getBounds().contains([marker.lon, marker.lat])) m.easeTo({ center: [marker.lon, marker.lat], duration: 600 })
      }
    }
    if (ready.current) apply(); else m.once('load', apply)
  }, [extraPins, marker, layers.pins])

  return <div ref={el} role="region" aria-label="Earth map" className={`h-[28rem] w-full overflow-hidden rounded-md border border-line ${onPick ? 'cursor-crosshair' : ''}`} />
}
