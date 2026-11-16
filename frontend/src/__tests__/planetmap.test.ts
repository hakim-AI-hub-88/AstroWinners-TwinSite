import { describe, expect, it } from 'vitest'
import { clampView, fitView, gridStep, panBy, zoomAt } from '@/components/PlanetMap'
import { project, unproject } from '@/components/PlanetGlobe'

describe('2D planet map view maths', () => {
  it('zooms around the cursor, keeping that point fixed', () => {
    const v = { cx: 0, cy: 0, span: 360 }
    const z = zoomAt(v, 4, 720 * 0.75, 360 * 0.25)   // point at lon 90, lat 45
    expect(z.span).toBe(90)
    const lon = z.cx - z.span / 2 + 0.75 * z.span, lat = z.cy + z.span / 4 - 0.25 * (z.span / 2)
    expect(lon).toBeCloseTo(90); expect(lat).toBeCloseTo(45)
  })
  it('clamps zoom and keeps the view on the body', () => {
    expect(zoomAt({ cx: 0, cy: 0, span: 1 }, 1000, 360, 180).span).toBe(0.2)
    expect(clampView({ cx: 500, cy: 500, span: 10 })).toEqual({ cx: 175, cy: 87.5, span: 10 })
    expect(clampView({ cx: 0, cy: 0, span: 9999 }).span).toBe(360)
  })
  it('pans by pixels in the drag direction', () => {
    const v = panBy({ cx: 0, cy: 0, span: 72 }, 72, 0)  // drag right by 1/10 width
    expect(v.cx).toBeCloseTo(-7.2)
  })
  it('fits footprints with context and picks a sensible graticule', () => {
    const v = fitView([], [{ id: 'gale', label: 'gale', bbox: [137.25, -4.75, 137.55, -4.45] }])
    expect(v.cx).toBeCloseTo(137.4); expect(v.span).toBe(4)
    expect(gridStep(360)).toBe(30); expect(gridStep(4)).toBe(1); expect(gridStep(0.5)).toBe(0.1)
  })
})

describe('orthographic globe projection', () => {
  it('round-trips visible points', () => {
    const o = { lon0: 137.4, lat0: -4.6, zoom: 4 }
    for (const [lon, lat] of [[137.4, -4.6], [150, 10], [100, -40], [-170, 20]]) {
      const p = project(o, lon, lat)
      if (!p.visible) continue
      const back = unproject(o, p.x, p.y)!
      expect(back.lon).toBeCloseTo(lon, 6); expect(back.lat).toBeCloseTo(lat, 6)
    }
  })
  it('hides the far side and puts the centre at the origin', () => {
    const o = { lon0: 0, lat0: 0, zoom: 1 }
    expect(project(o, 180, 0).visible).toBe(false)
    const c = project(o, 0, 0)
    expect(c.x).toBeCloseTo(0); expect(c.y).toBeCloseTo(0); expect(c.visible).toBe(true)
    expect(unproject(o, 1.2, 0)).toBeNull()
  })
})
