import { describe, expect, it } from 'vitest'
import { demoResult, demoEvidence, demoEvents, demoRecords, demoCompare, FIXTURES } from '@/lib/demo'
import { isReleased, prosCons, rankSites, stability, timeBasis, unresolvedGaps } from '@/lib/analysis'

const r = demoResult('demo-earth-moon')
describe('analysis helpers', () => {
  it('ranks eligible sites first by similarity and never ranks ineligible ones', () => {
    const ranked = rankSites(r.sites)
    const ranks = ranked.filter((s) => s.rank).map((s) => s.rank)
    expect(ranks).toEqual(ranks.map((_, i) => i + 1))
    const el = ranked.filter((s) => s.rank)
    for (let i = 1; i < el.length; i++) expect((el[i - 1].observed_similarity ?? -1) >= (el[i].observed_similarity ?? -1)).toBe(true)
    expect(ranked.filter((s) => !s.eligible).every((s) => s.rank === null)).toBe(true)
  })
  it('derives pros/cons from contributions and failures only', () => {
    const e = r.sites.find((s) => !s.eligible)!
    expect(prosCons(e).cons.some((c) => c.text.includes('access constraint failed'))).toBe(true)
  })
  it('synthetic evidence is never treated as released', () => {
    const ev = demoEvidence('demo-earth-moon')
    expect(ev.release_action).toBe('BLOCK')
    expect(isReleased(r, ev)).toBe(false)
    expect(isReleased({ ...r, data_status: 'measured' }, null)).toBe(false)
    expect(timeBasis(ev)).toMatch(/No observation period/)
    expect(unresolvedGaps(r, ev).join(' ')).toMatch(/SYNTHETIC_ONLY/)
    expect(unresolvedGaps(r, null)[0]).toMatch(/unavailable/)
  })
  it('stability reports share of scenarios', () => {
    const s = stability(r)
    expect(s.scenarios).toBe(r.sensitivity.scenarios)
    expect(s.top?.share).toBeLessThanOrEqual(1)
  })
})
describe('demo adapter', () => {
  it('every fixture result is synthetic and labelled', () => { for (const f of FIXTURES) expect(f.res.data_status).toBe('synthetic') })
  it('replay emits ascending, labelled events', () => {
    const ev = demoEvents('demo-earth-moon', 0)
    expect(ev.length).toBe(20)
    expect(ev.every((e, i) => e.sequence === i + 1 && e.summary.startsWith('[DEMO REPLAY]'))).toBe(true)
    expect(demoEvents('demo-earth-moon', 18).map((e) => e.sequence)).toEqual([19, 20])
  })
  it('raw, cleaned and derived stages are distinct and compare aligns by record', () => {
    const raw = demoRecords('demo-ds-mobility', 'raw'), cl = demoRecords('demo-ds-mobility', 'cleaned'), dv = demoRecords('demo-ds-mobility', 'derived')
    expect(raw.columns).toContain('raw_value'); expect(cl.columns).toContain('transformation'); expect(dv.columns).toContain('similarity')
    const c = demoCompare('demo-ds-mobility', 'demo-ds-earth-moon', 'cleaned', ['value', 'unit'])
    expect(c.rows.length).toBeGreaterThan(0)
    expect(c.rows.some((x) => x.left && !x.right)).toBe(true)
  })
})
