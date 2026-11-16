// Shared wire types come from the frozen contract (read-only).
export type {
  Health, MissionRequest, MissionResult, MissionAccepted, MissionStatus, ProgressEvent,
  Events, EvidenceObservation, AssetManifest, ReleaseEvidence, AlternativesRequest,
  DataCompareRequest, Error as ApiErrorBody,
} from '@contracts/types'
import type { MissionResult, MissionRequest } from '@contracts/types'

export type Body = 'Earth' | 'Moon' | 'Mars'
export type Site = MissionResult['sites'][number]
export type Portfolio = MissionResult['portfolios'][number]
export type Location = MissionRequest['mission']['scope']['locations'][number]

export const PHASES = ['P00','P10','P20','P30','P40','P50','P60','P70','P80','P90'] as const
export const PHASE_LABEL: Record<(typeof PHASES)[number], string> = {
  P00: 'Register & queue', P10: 'Acquire source assets', P20: 'Decode products',
  P30: 'Clean & mask', P40: 'Validate (QA gate)', P50: 'Characterize features',
  P60: 'Compare analogues', P70: 'Optimize portfolios', P80: 'Review', P90: 'Publish',
}
export const TERMINAL = ['completed', 'completed_with_limits', 'failed', 'cancelled']

// --- Data Explorer adapter types (G3 response schemas are NOT frozen; see UI_STATUS.md) ---
export type Stage = 'raw' | 'cleaned' | 'derived'
export interface DatasetSummary {
  dataset_id: string
  title: string
  source: string
  body: Body | 'Multi'
  domain: string
  resolution?: string | null
  temporal_coverage?: string | null
  records?: number | null
  qa_status?: string | null
  data_status: 'synthetic' | 'measured'
  description?: string
}
export interface DatasetRecords {
  stage: Stage
  columns: string[]
  rows: Array<Record<string, string | number | null>>
  sampled: boolean
  total?: number | null
  next_cursor?: string | null
}
export interface DatasetMetadata {
  dataset_id: string
  source: string
  product?: string
  version?: string
  license?: string
  crs?: string
  unit_notes?: string
  time_basis?: string
  qa?: string
  lineage: string[]
  transforms: string[]
  data_status: 'synthetic' | 'measured'
  extent?: { east_west_km: number; north_south_km: number; bbox_deg: number[]; method: string }
  distributions?: Record<string, FeatureDistribution>
  native_resolution_m?: number | null
  analysis_scale_m?: number | null
}
export interface FeatureDistribution { n?: number; min?: number; p10?: number; median?: number; mean?: number; p90?: number; max?: number; sd?: number }
export interface DatasetGrid {
  dataset_id: string
  body: string
  stage: 'cleaned'
  unit: string
  vertical_datum?: string | null
  cleaned_sha256: string
  native: { nrows: number; ncols: number; dlat: number; dlon: number; lat0: number; lon0: number; registration: string }
  display: { factor: number; nrows: number; ncols: number; values: Array<number | null>; first_center: [number, number]; step_deg: [number, number]; min: number | null; max: number | null; trimmed_native_rows: number; trimmed_native_cols: number }
  method: string
  transformations: string[]
  caveats: string[]
}
export interface CompareResult {
  columns: string[]
  rows: Array<{ key: string; left: Record<string, unknown> | null; right: Record<string, unknown> | null }>
}
