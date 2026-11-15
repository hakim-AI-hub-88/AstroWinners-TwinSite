import type { MissionResult, ReleaseEvidence, Site } from './types'

export const PRO_AT = 0.8
export const CON_BELOW = 0.5

/** Eligible sites first, by observed similarity desc (null last); ineligible after. Ties keep input order. */
export function rankSites(sites: Site[]): Array<Site & { rank: number | null }> {
  const key = (s: Site) => (s.observed_similarity == null ? -1 : s.observed_similarity)
  const el = sites.filter((s) => s.eligible).map((s, i) => ({ s, i })).sort((a, b) => key(b.s) - key(a.s) || a.i - b.i)
  const rest = sites.filter((s) => !s.eligible)
  return [...el.map((x, n) => ({ ...x.s, rank: n + 1 })), ...rest.map((s) => ({ ...s, rank: null }))]
}

export interface ProCon { text: string; feature: string }
export function prosCons(s: Site): { pros: ProCon[]; cons: ProCon[] } {
  const pros: ProCon[] = [], cons: ProCon[] = []
  for (const c of Object.values(s.contributions)) {
    const line = `${c.feature_id} vs ${c.target_body}: ${c.value} ${c.unit} against target ${c.target_value} (similarity ${c.similarity.toFixed(2)})`
    if (c.similarity >= PRO_AT) pros.push({ text: line, feature: c.feature_id })
    else if (c.similarity < CON_BELOW) cons.push({ text: line, feature: c.feature_id })
  }
  for (const m of s.missing) cons.push({ text: `No measurement for ${m}`, feature: m })
  for (const f of s.failures) cons.push({ text: f, feature: 'constraint' })
  if (s.access === 'unknown') cons.push({ text: 'Access status unknown', feature: 'access' })
  return { pros, cons }
}

export function qaCounts(ev?: ReleaseEvidence | null) {
  const c: Record<string, number> = {}
  for (const o of ev?.observations ?? []) c[o.qa_status] = (c[o.qa_status] ?? 0) + 1
  return c
}
export function timeBasis(ev?: ReleaseEvidence | null): string {
  const o = ev?.observations ?? []
  if (!o.length) return 'No observation period attested'
  const starts = o.map((x) => x.observation_period.start).sort(), ends = o.map((x) => x.observation_period.end).sort()
  return `${starts[0].slice(0, 10)} → ${ends[ends.length - 1].slice(0, 10)}`
}
export function unresolvedGaps(r: MissionResult, ev?: ReleaseEvidence | null): string[] {
  const g: string[] = []
  if (!ev) g.push('Release evidence sidecar unavailable — no measured-science claim can be shown.')
  for (const b of ev?.blocking_issues ?? []) g.push(`Blocking: ${b}`)
  for (const u of ev?.unknowns ?? []) g.push(u)
  for (const s of r.sites) if (s.missing.length) g.push(`${s.name}: missing ${s.missing.join(', ')}`)
  for (const x of ev?.rejected_candidates ?? []) g.push(`Rejected ${x.site_id}: ${x.reasons.join('; ')}`)
  return g
}
/** Measured results are shown as released only with an evidence sidecar whose gate did not BLOCK. */
export function isReleased(r: MissionResult, ev?: ReleaseEvidence | null) {
  return r.data_status === 'measured' && !!ev && ev.release_action !== 'BLOCK' && ev.strict_gate_status === 'PASS'
}
export function stability(r: MissionResult) {
  const { scenarios, top_portfolio_counts, infeasible_scenarios } = r.sensitivity
  const entries = Object.entries(top_portfolio_counts).sort((a, b) => b[1] - a[1])
  const top = entries[0]
  return { scenarios, infeasible: infeasible_scenarios, top: top ? { ids: top[0], count: top[1], share: scenarios ? top[1] / scenarios : 0 } : null, entries }
}
