import { describe, expect, it } from 'vitest'
import { ClickTracker, boxAround } from '@/lib/picking'
import { globePick, project } from '@/components/PlanetGlobe'
import { viewBoxToLonLat, zoomAt } from '@/components/PlanetMap'
import { observationsCsv, safeHref } from '@/lib/exports'
import type { EvidenceObservation } from '@/lib/types'

describe('click vs drag', () => {
  it('counts a still press/release as a click', () => {
    const t = new ClickTracker(); t.down(100, 100, 1); t.move(101, 101)
    expect(t.up(101, 100)).toBe(true)
  })
  it('rejects a drag even if it returns to its start point', () => {
    const t = new ClickTracker(); t.down(100, 100, 1); t.move(140, 100); t.move(100, 100)
    expect(t.up(100, 100)).toBe(false)
  })
  it('rejects a two-finger pinch', () => {
    const t = new ClickTracker(); t.down(100, 100, 1); t.down(200, 100, 2)
    expect(t.up(100, 100)).toBe(false)
  })
  it('requires a preceding press', () => { expect(new ClickTracker().up(0, 0)).toBe(false) })
})

describe('pick coordinates', () => {
  it('globe pick inverts the forward projection and ignores clicks off the disc', () => {
    const o = { lon0: 30.8, lat0: 20.2, zoom: 3 }, R = 300
    const p = project(o, 31.5, 19.4)
    const hit = globePick(o, p.x * R, -p.y * R, R)!
    expect(hit.lon).toBeCloseTo(31.5, 3); expect(hit.lat).toBeCloseTo(19.4, 3)
    expect(globePick(o, 0, 0, R)).toEqual({ lon: 30.8, lat: 20.2 })
    expect(globePick(o, R * 1.01, 0, R)).toBeNull()
  })
  it('2D map pick inverts the view transform after zoom', () => {
    const v = zoomAt({ cx: 0, cy: 0, span: 360 }, 4, 720 * 0.75, 360 * 0.25)
    const ll = viewBoxToLonLat(v, 720 * 0.75, 360 * 0.25)
    expect(ll.lon).toBeCloseTo(90); expect(ll.lat).toBeCloseTo(45)
  })
  it('builds a 1-degree box clamped to the body', () => {
    expect(boxAround(137.4, -4.6)).toEqual([136.9, -5.1, 137.9, -4.1])
    expect(boxAround(179.9, 89.9)).toEqual([179, 89, 180, 90])
  })
})

describe('observation CSV export', () => {
  const o = {
    schema_version: '1.0', evidence_id: 'ev-1', feature_id: 'slope_deg', site_id: 'gale', body: 'Mars',
    geometry: { type: 'bbox', coordinates: [137.3, -5.9, 138.3, -4.9], crs: 'Mars_planetocentric_east_180' },
    value: 3.2, unit: 'degree', source_product: 'MOLA MEGDR', source_granule_id: 'g1', source_url: 'https://pds.example/x', source_checksum: 'abc',
    source_asset_ids: ['a1', 'a2'], observation_period: { start: '1997-09-15T00:00:00Z', end: '2001-06-30T00:00:00Z' },
    spatial_resolution_m: 463, analysis_scale_m: 1852, quality_flags: ['ok', 'interp, filled'], valid_coverage_fraction: 0.98,
    uncertainty: { kind: 'interval', low: 2.9, high: 3.5, standard_deviation: null, basis: 'x' }, qa_status: 'ACCEPT',
  } as unknown as EvidenceObservation
  it('flattens nested fields and never writes [object Object]', () => {
    const csv = observationsCsv([o])
    const [head, row] = csv.split('\n')
    expect(head.split(',')).toContain('period_start')
    expect(csv).not.toMatch(/object Object/)
    expect(row).toContain('1997-09-15T00:00:00Z')
    expect(row).toContain('137.3;-5.9;138.3;-4.9')
    expect(row).toContain('"ok;interp, filled"')
    expect(row).toContain('a1;a2')
  })
  it('only links http(s) sources', () => {
    expect(safeHref('https://x.y')).toBe('https://x.y'); expect(safeHref('javascript:alert(1)')).toBeNull(); expect(safeHref(null)).toBeNull()
  })
})
