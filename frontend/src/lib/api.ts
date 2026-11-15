import type {
  Health, MissionRequest, MissionResult, MissionAccepted, MissionStatus, ProgressEvent, ReleaseEvidence,
  DatasetSummary, DatasetRecords, DatasetMetadata, DatasetGrid, CompareResult, Stage, AlternativesRequest,
} from './types'
import * as demo from './demo'

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/v1'
export const FORCE_DEMO = import.meta.env.VITE_FORCE_DEMO === '1'

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public field?: string | null) { super(message) }
}

async function http<T>(path: string, init?: RequestInit, as: 'json' | 'text' = 'json'): Promise<T> {
  let res: Response
  try { res = await fetch(`${BASE}${path}`, init) } catch { throw new ApiError(0, 'network', 'API unreachable') }
  if (!res.ok) {
    let code = `http_${res.status}`, msg = res.statusText, field: string | null = null, envelope = false
    try { const b = await res.json(); envelope = !!b.error?.code; code = b.error?.code ?? code; msg = b.error?.message ?? msg; field = b.error?.field ?? null } catch { /* non-JSON */ }
    // The TwinSite API always answers errors with a JSON envelope. A bare 5xx comes from the
    // dev/reverse proxy when the backend is down, so it is reported as unreachable.
    if (!envelope && res.status >= 500) throw new ApiError(0, 'network', `API unreachable (proxy returned ${res.status})`)
    throw new ApiError(res.status, code, msg, field)
  }
  return (as === 'json' ? res.json() : res.text()) as Promise<T>
}

export const getHealth = () => (FORCE_DEMO ? Promise.reject(new ApiError(0, 'forced_demo', 'VITE_FORCE_DEMO=1')) : http<Health>('/health'))

export async function postMission(req: MissionRequest, key: string): Promise<MissionAccepted> {
  return http<MissionAccepted>(`/missions?analysis_mode=${getAnalysisMode()}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: JSON.stringify(req),
  })
}
export const getStatus = (id: string): Promise<MissionStatus> => demo.isDemoRun(id) ? Promise.resolve(demo.demoStatus(id)) : http(`/missions/${id}`)
export const getEvents = (id: string, after: number): Promise<ProgressEvent[]> =>
  demo.isDemoRun(id) ? Promise.resolve(demo.demoEvents(id, after)) : http(`/missions/${id}/events?after=${after}`)
export const getResult = (id: string): Promise<MissionResult> => demo.isDemoRun(id) ? Promise.resolve(demo.demoResult(id)) : http(`/missions/${id}/result`)
export const getEvidence = (id: string): Promise<ReleaseEvidence> => demo.isDemoRun(id) ? Promise.resolve(demo.demoEvidence(id)) : http(`/missions/${id}/evidence`)
export const getReportHtml = (id: string): Promise<string> => demo.isDemoRun(id) ? Promise.reject(new ApiError(0, 'demo', 'demo')) : http(`/missions/${id}/report`, undefined, 'text')
export const reportUrl = (id: string) => `${BASE}/missions/${id}/report`
export const postAlternatives = (id: string, body: AlternativesRequest, key: string): Promise<MissionAccepted> =>
  http(`/missions/${id}/portfolios/alternatives`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: JSON.stringify(body) })

// --- G3 data endpoints: reserved, response schemas not frozen. Adapters are tolerant. ---
export interface Sourced<T> { data: T; demo: boolean; note?: string }
async function withDemo<T>(live: () => Promise<T>, fallback: () => T): Promise<Sourced<T>> {
  if (FORCE_DEMO) return { data: fallback(), demo: true, note: 'Demo mode forced (VITE_FORCE_DEMO=1).' }
  try { return { data: await live(), demo: false } } catch (e) {
    const err = e as ApiError
    // Only an unreachable API or an unimplemented endpoint may fall back to labelled demo data.
    // Real 4xx/5xx responses are errors and must never be masked by synthetic tables.
    if (!(err instanceof ApiError) || (err.status !== 0 && err.status !== 501)) throw e
    const why = err.status === 501 ? 'endpoint returned 501 (not implemented)' : err.status === 0 ? 'API unreachable' : `endpoint returned ${err.status}`
    return { data: fallback(), demo: true, note: `Live data endpoint unavailable — ${why}. Showing DEMO tables derived from synthetic fixtures.` }
  }
}
export const getCatalog = () => withDemo<DatasetSummary[]>(async () => {
  const r = await http<{ datasets?: Array<Record<string, unknown>>; items?: Array<Record<string, unknown>> } | Array<Record<string, unknown>>>('/data/catalog?limit=100')
  const raw = Array.isArray(r) ? r : (r.items ?? r.datasets ?? [])
  // Catalog response schema is not frozen (C3 proposal uses `provider`, no domain); normalise defensively.
  return raw.map((d) => ({
    dataset_id: String(d.dataset_id), title: String(d.title ?? d.dataset_id), source: String(d.source ?? d.provider ?? 'unknown'),
    body: (d.body ?? 'Multi') as DatasetSummary['body'], domain: String(d.domain ?? 'unspecified'),
    resolution: (d.resolution as string) ?? (d.resolution_m != null ? `${d.resolution_m} m` : null), temporal_coverage: (d.temporal_coverage as string) ?? null,
    records: (d.records as number) ?? null, qa_status: (d.qa_status as string) ?? null, data_status: (d.data_status === 'synthetic' ? 'synthetic' : 'measured') as 'synthetic' | 'measured',
  }))
}, demo.demoCatalog)
export const getRecords = (id: string, stage: Stage, limit = 100) => withDemo<DatasetRecords>(
  () => http(`/data/${encodeURIComponent(id)}/records?stage=${stage}&limit=${limit}`), () => demo.demoRecords(id, stage))
export const getMetadata = (id: string) => withDemo<DatasetMetadata>(() => http(`/data/${encodeURIComponent(id)}/metadata`), () => demo.demoMetadata(id))
export const postCompare = (l: string, r: string, stage: Stage, columns: string[], lIds: string[], rIds: string[]) =>
  withDemo<CompareResult>(() => http('/data/compare', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ schema_version: '1.0', left_dataset_id: l, right_dataset_id: r, left_record_ids: lIds, right_record_ids: rIds, columns, stage }),
  }), () => demo.demoCompare(l, r, stage, columns))

export const postPublishedMission = () => http<MissionAccepted>(`/missions/measured?analysis_mode=${getAnalysisMode()}`, {
  method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
  body: JSON.stringify({ schema_version: '1.0', dataset_id: 'zagora-gale-v1' }),
})

// Cleaned grid: real data only. There is no demo fallback for raster views.
export const getGrid = (id: string) => http<DatasetGrid>(`/data/${encodeURIComponent(id)}/grid`)

// ---------------------------------------------------------------- AI-Powered Analysis (default) / Simple Analysis
export type AnalysisMode = 'ai' | 'simple'
const MODE_KEY = 'twinsite.analysisMode'
export function getAnalysisMode(): AnalysisMode {
  try { return localStorage.getItem(MODE_KEY) === 'simple' ? 'simple' : 'ai' } catch { return 'ai' }
}
export function setAnalysisMode(m: AnalysisMode) { try { localStorage.setItem(MODE_KEY, m) } catch { /* per-viewer convenience only */ } }

export interface AgentInference { ok: boolean; provider: string | null; model: string | null; cached: boolean; latency_ms: number; error: string | null; attempts: Array<Record<string, unknown>> }
export interface AgentRecord { agent_id: string; role: string; phase: string; execution: 'ai' | 'ai_cached' | 'deterministic' | 'skipped' | 'failed' | 'fallback'; purpose: string; summary: string; output?: Record<string, unknown> | null; inference?: AgentInference }
export interface AgentTrace { run_id: string; analysis_mode: AnalysisMode; ai_available?: boolean; fallback_reason?: string | null; ai_roles_executed?: string[]; ai_calls_attempted?: number; records: AgentRecord[]; pending?: boolean }
export const getAgents = (id: string): Promise<AgentTrace> => http(`/missions/${id}/agents`)
export const getAiStatus = (): Promise<{ ai_enabled: boolean; providers: { enabled: boolean; disabled_reason: string | null; providers: Array<{ id: string; name: string; state: string; accounts: number; quota_groups: number; verified_models: string[]; calls_today: number; data_policy: string }> } }> => http('/ai/status')

// ---------------------------------------------------------------- Scientific Data Gateway (read-only + bounded Earth site acquisition)
export interface SciSite { site_id: string; name: string; body: string; lon: number | null; lat: number | null; observation_count: number }
export interface SciObs { evidence_id: string; site_id: string; body: string; domain: string; quantity: string; value: number | null; unit: string | null; kind: string; statistic: string | null; temporal_support: string | null; spatial_support: string | null; qa_status: string; quality_flags: string[] | null; uncertainty: { low?: number | null; high?: number | null; basis?: string } | null; missing_reason: string | null; source_id: string; product_id: string; asset_id: string | null; comparability: string | null }
export interface CoverageRow { domain: string; body: string; sources: string[]; real_data_status: string; validation: string; simple_analysis: boolean; ai_agents: boolean; data_explorer: boolean; observations_persisted: number; limitations: string }
export const getSciSites = (): Promise<{ sites: SciSite[] }> => http('/science/sites')
export const getSciObservations = (sites: string[], limit = 200): Promise<{ total: number; observations: SciObs[] }> =>
  http(`/science/observations?${sites.map((s) => `site=${encodeURIComponent(s)}`).join('&')}&limit=${limit}`)
export const getCoverage = (): Promise<{ rows: CoverageRow[] }> => http('/science/coverage')
export const postSciSite = (name: string, longitude: number, latitude: number): Promise<{ site_id: string; observations: number }> =>
  http('/science/sites', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, longitude, latitude }) })
export const sciAssetUrl = (assetId: string) => `${BASE}/science/assets/${assetId}`
export interface Place { name: string; admin1?: string | null; country?: string | null; feature_code?: string | null; latitude: number; longitude: number; elevation_m?: number | null }
export const searchPlaces = (q: string): Promise<{ places: Place[]; attribution: string }> => http(`/science/places?q=${encodeURIComponent(q)}`)
