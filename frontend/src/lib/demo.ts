// DEMO / SYNTHETIC adapter. Every value here is read verbatim from contracts/examples (synthetic fixtures).
// Nothing here is NASA data. Used only when the live API is unreachable or for runIds starting "demo-".
import mission from '@contracts/examples/mission.synthetic.json'
import missionResult from '@contracts/examples/mission.result.synthetic.json'
import moon from '@contracts/examples/moon_mission.synthetic.json'
import moonResult from '@contracts/examples/moon_mission.result.synthetic.json'
import three from '@contracts/examples/three_body_mission.synthetic.json'
import threeResult from '@contracts/examples/three_body_mission.result.synthetic.json'
import zone from '@contracts/examples/zone_mission.synthetic.json'
import zoneResult from '@contracts/examples/zone_mission.result.synthetic.json'
import evidence from '@contracts/examples/release_evidence.synthetic.json'
import type {
  MissionRequest, MissionResult, ReleaseEvidence, ProgressEvent, MissionStatus,
  DatasetSummary, DatasetRecords, DatasetMetadata, Stage, CompareResult,
} from './types'
import { PHASES, PHASE_LABEL } from './types'

export const DEMO_MARK = 'DEMO / SYNTHETIC — frozen contract fixture, not NASA measurements'

interface Fixture { key: string; title: string; req: MissionRequest; res: MissionResult }
export const FIXTURES: Fixture[] = [
  { key: 'earth-moon', title: 'Earth ↔ Moon mobility (south pole)', req: moon as unknown as MissionRequest, res: moonResult as unknown as MissionResult },
  { key: 'earth-mars-moon', title: 'Earth ↔ Moon + Mars (three bodies)', req: three as unknown as MissionRequest, res: threeResult as unknown as MissionResult },
  { key: 'zones', title: 'Zone-based Earth ↔ Mars', req: zone as unknown as MissionRequest, res: zoneResult as unknown as MissionResult },
  { key: 'mobility', title: 'Mobility baseline (Earth shortlist)', req: mission as unknown as MissionRequest, res: missionResult as unknown as MissionResult },
]
export const isDemoRun = (runId: string) => runId.startsWith('demo-')
const fixtureOf = (runId: string) => FIXTURES.find((f) => runId === `demo-${f.key}`) ?? FIXTURES[0]
export const demoRunIdFor = (key: string) => `demo-${key}`

/** Which fixture best matches a user's target body choice (demo mode only). */
export function pickFixture(targets: string[]): Fixture {
  const t = new Set(targets)
  if (t.has('Moon') && t.has('Mars')) return FIXTURES[1]
  if (t.has('Mars')) return FIXTURES[2]
  return FIXTURES[0]
}

export function demoResult(runId: string): MissionResult { return fixtureOf(runId).res }
export function demoRequest(runId: string): MissionRequest { return fixtureOf(runId).req }
export function demoEvidence(runId: string): ReleaseEvidence {
  return { ...(evidence as unknown as ReleaseEvidence), run_id: runId }
}

// --- Labelled demo replay of the P00..P90 lifecycle (clock-driven, no percentages) ---
const STEP_MS = 650
const startKey = (runId: string) => `twinsite.demo.start.${runId}`
export function demoStart(runId: string) {
  try { if (!sessionStorage.getItem(startKey(runId))) sessionStorage.setItem(startKey(runId), String(Date.now())) } catch { /* ignore */ }
}
function elapsedSteps(runId: string) {
  // Deep-linking to a demo run with no recorded start shows the finished result (no replay).
  let t0: number | null = null
  try { const v = sessionStorage.getItem(startKey(runId)); t0 = v == null ? null : Number(v) } catch { /* ignore */ }
  return t0 == null ? 10_000 : Math.floor((Date.now() - t0) / STEP_MS)
}
export function demoEvents(runId: string, after: number): ProgressEvent[] {
  const n = Math.min(elapsedSteps(runId) + 1, PHASES.length * 2)
  const all: ProgressEvent[] = []
  let seq = 0
  const base = new Date('2026-11-15T01:45:00Z').getTime()
  PHASES.forEach((p, i) => {
    const mk = (state: ProgressEvent['state'], summary: string): ProgressEvent => ({
      schema_version: '1.0', mission_id: runId, task_id: `${p.toLowerCase()}-demo`, attempt_id: 'attempt-0',
      sequence: ++seq, timestamp: new Date(base + seq * 4000).toISOString(), phase: p, state,
      completed_units: state === 'succeeded' ? 1 : 0, total_units: state === 'succeeded' ? 1 : null,
      summary: `[DEMO REPLAY] ${PHASE_LABEL[p]} — ${summary}`, trace_id: 'trace-demo', artifact_ids: [],
    })
    all.push(mk('running', 'started'))
    all.push(mk('succeeded', 'finished (synthetic fixture)'))
    void i
  })
  return all.slice(0, n).filter((e) => e.sequence > after)
}
export function demoStatus(runId: string): MissionStatus {
  const total = PHASES.length * 2
  const steps = elapsedSteps(runId) + 1
  const done = steps >= total
  const evs = demoEvents(runId, 0)
  const last = evs[evs.length - 1]
  const order = ['queued','acquiring','decoding','cleaning','validating','characterizing','analyzing','optimizing','reviewing','publishing'] as const
  const idxPhase = last ? PHASES.indexOf(last.phase) : 0
  return {
    schema_version: '1.0', run_id: runId, id: runId,
    status: done ? 'completed_with_limits' : order[Math.max(0, idxPhase)],
    attempt: 0, input_sha256: demoResult(runId).input_sha256, source_snapshot_id: 'synthetic-fixture-v1', error: null,
  }
}

// --- Demo Data Explorer: tables derived from fixtures ---
type Row = Record<string, string | number | null>
function rawRows(f: Fixture): Row[] {
  const rows: Row[] = []
  for (const s of f.req.sites) for (const [feat, o] of Object.entries(s.observations)) {
    rows.push({ record_id: `${s.id}/${feat}`, body: s.body, site_id: s.id, site: s.name ?? s.id, feature: feat,
      raw_value: o.value, unit: o.unit, source_id: o.source_id,
      missing_sentinel: o.missing_sentinel ?? null, missing_reason: o.missing_reason ?? null })
  }
  for (const t of f.req.target_profiles) for (const [feat, o] of Object.entries(t.observations)) {
    rows.push({ record_id: `${t.location.id}/${feat}`, body: t.body, site_id: t.location.id, site: `${t.body} target`, feature: feat,
      raw_value: o.value, unit: o.unit, source_id: o.source_id,
      missing_sentinel: o.missing_sentinel ?? null, missing_reason: o.missing_reason ?? null })
  }
  return rows
}
function cleanedRows(f: Fixture): Row[] {
  const tx = new Map(f.res.transformations.map((t) => [`${t.site_id}/${t.feature}`, t.rule]))
  return rawRows(f).map((r) => {
    const sentinel = r.missing_sentinel != null && r.raw_value === r.missing_sentinel
    return {
      record_id: r.record_id, body: r.body, site_id: r.site_id, feature: r.feature,
      value: sentinel ? null : r.raw_value, unit: r.unit, source_id: r.source_id,
      transformation: tx.get(String(r.record_id)) ?? (sentinel ? 'missing sentinel → null' : r.raw_value == null ? 'none (value missing at source; kept null)' : 'none (passed through)'),
    }
  })
}
function derivedRows(f: Fixture): Row[] {
  const rows: Row[] = []
  for (const s of f.res.sites) for (const [k, c] of Object.entries(s.contributions)) {
    rows.push({ record_id: `${s.id}/${k}`, site_id: s.id, comparison: k, value: c.value, target_value: c.target_value, unit: c.unit,
      similarity: Number(c.similarity.toFixed(4)), weighted_contribution: Number(c.weighted_contribution.toFixed(4)),
      source_id: c.source_id, target_source_id: c.target_source_id })
  }
  return rows
}
const DATASETS = FIXTURES.map((f) => ({ id: `demo-ds-${f.key}`, f }))
export const demoCatalog = (): DatasetSummary[] => DATASETS.map(({ id, f }) => ({
  dataset_id: id, title: `Observations — ${f.title}`, source: 'contracts/examples (synthetic)', body: f.res.scope.locations.length ? 'Multi' : 'Earth',
  domain: 'Terrain features', resolution: 'n/a (synthetic)', temporal_coverage: 'n/a (synthetic)',
  records: rawRows(f).length, qa_status: 'SYNTHETIC', data_status: 'synthetic',
  description: 'Rows flattened from the frozen synthetic mission request; cleaned/derived stages come from the matching synthetic result.',
}))
export function demoRecords(id: string, stage: Stage): DatasetRecords {
  const f = DATASETS.find((d) => d.id === id)?.f ?? FIXTURES[0]
  const rows = stage === 'raw' ? rawRows(f) : stage === 'cleaned' ? cleanedRows(f) : derivedRows(f)
  return { stage, columns: Object.keys(rows[0] ?? {}), rows, sampled: false, total: rows.length }
}
export function demoMetadata(id: string): DatasetMetadata {
  const f = DATASETS.find((d) => d.id === id)?.f ?? FIXTURES[0]
  return {
    dataset_id: id, source: 'contracts/examples (synthetic fixture)', product: f.req.mission.id, version: f.res.algorithm_version,
    license: 'n/a — synthetic', crs: [...new Set(f.req.sites.map((s) => s.coordinate_system))].join(', '),
    unit_notes: 'Units as declared per observation; no conversion applied.', time_basis: 'none — synthetic values carry no observation period',
    qa: 'SYNTHETIC_ONLY (release BLOCK)', data_status: 'synthetic',
    lineage: [`input_sha256 ${f.res.input_sha256}`, `cleaned_sha256 ${f.res.cleaned_sha256}`],
    transforms: f.res.transformations.length ? f.res.transformations.map((t) => `${t.site_id}/${t.feature}: ${t.rule}`) : ['No transformations applied.'],
  }
}
export function demoCompare(leftId: string, rightId: string, stage: Stage, columns: string[]): CompareResult {
  const L = demoRecords(leftId, stage).rows, R = demoRecords(rightId, stage).rows
  const rm = new Map(R.map((r) => [String(r.record_id), r])), lm = new Map(L.map((r) => [String(r.record_id), r]))
  const keys = [...new Set([...L.map((r) => String(r.record_id)), ...R.map((r) => String(r.record_id))])]
  const pick = (r: Row | undefined) => (r ? Object.fromEntries(columns.map((c) => [c, r[c] ?? null])) : null)
  return { columns, rows: keys.map((k) => ({ key: k, left: pick(lm.get(k)), right: pick(rm.get(k)) })) }
}
