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
}
export interface CompareResult {
  columns: string[]
  rows: Array<{ key: string; left: Record<string, unknown> | null; right: Record<string, unknown> | null }>
}
