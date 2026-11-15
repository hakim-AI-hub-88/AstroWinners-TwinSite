import type { EvidenceObservation } from './types'
import { toCsv } from './format'

export const OBS_CSV_COLUMNS = [
  'evidence_id', 'site_id', 'body', 'feature_id', 'value', 'unit', 'qa_status', 'period_start', 'period_end',
  'spatial_resolution_m', 'analysis_scale_m', 'valid_coverage_fraction', 'uncertainty_kind', 'uncertainty_low', 'uncertainty_high',
  'uncertainty_sd', 'quality_flags', 'bbox', 'crs', 'source_product', 'source_granule_id', 'source_url', 'source_checksum', 'source_asset_ids',
] as const

/** Flatten evidence observations (nested period, geometry, uncertainty, lists) into CSV rows. */
export function observationRows(obs: EvidenceObservation[]): Array<Record<string, unknown>> {
  return obs.map((o) => ({
    evidence_id: o.evidence_id, site_id: o.site_id, body: o.body, feature_id: o.feature_id, value: o.value, unit: o.unit, qa_status: o.qa_status,
    period_start: o.observation_period?.start, period_end: o.observation_period?.end,
    spatial_resolution_m: o.spatial_resolution_m, analysis_scale_m: o.analysis_scale_m, valid_coverage_fraction: o.valid_coverage_fraction,
    uncertainty_kind: o.uncertainty?.kind, uncertainty_low: o.uncertainty?.low, uncertainty_high: o.uncertainty?.high, uncertainty_sd: o.uncertainty?.standard_deviation,
    quality_flags: (o.quality_flags ?? []).join(';'), bbox: (o.geometry?.coordinates ?? []).join(';'), crs: o.geometry?.crs,
    source_product: o.source_product, source_granule_id: o.source_granule_id, source_url: o.source_url, source_checksum: o.source_checksum,
    source_asset_ids: (o.source_asset_ids ?? []).join(';'),
  }))
}
export const observationsCsv = (obs: EvidenceObservation[]) => toCsv([...OBS_CSV_COLUMNS], observationRows(obs))

/** Only http(s) URLs are rendered as links. */
export const safeHref = (u: string | null | undefined) => (u && /^https?:\/\//i.test(u) ? u : null)
