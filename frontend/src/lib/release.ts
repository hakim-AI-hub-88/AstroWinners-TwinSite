import { useCallback, useSyncExternalStore } from 'react'
import { isReleased } from './analysis'
import type { MissionResult, ReleaseEvidence } from './types'

// Which runs the user has explicitly chosen to see unreleased diagnostic values for.
// In-memory only: the choice is shared across screens of this tab and is forgotten on reload.
const revealed = new Set<string>()
const subs = new Set<() => void>()
const subscribe = (f: () => void) => { subs.add(f); return () => { subs.delete(f) } }
export function setRevealed(runId: string, on: boolean) {
  if (on) revealed.add(runId); else revealed.delete(runId)
  subs.forEach((f) => f())
}

/** "Unreleased diagnostic values (release gate: BLOCK — ISSUE_A, ISSUE_B)" */
export function gateLabel(ev: ReleaseEvidence | null | undefined): string {
  const action = ev ? ev.release_action : 'evidence missing'
  const issues = ev?.blocking_issues?.length ? ` — ${ev.blocking_issues.join(', ')}` : ''
  return `Unreleased diagnostic values (release gate: ${action}${issues})`
}

export interface ReleaseGateState {
  /** Measured, evidence present, release gate not BLOCK and strict gate PASS. */
  released: boolean
  synthetic: boolean
  /** Measured run whose ranks and scores are not released (BLOCK, failed strict gate or evidence missing). */
  gated: boolean
  /** Ranks and scores must not be shown right now. */
  hide: boolean
  /** The user explicitly revealed the unreleased diagnostic values. */
  revealed: boolean
  setReveal: (on: boolean) => void
  label: string
}

/**
 * The single release-gate rule used by every screen (Analysis, Portfolios, Report, Explorer).
 * Synthetic runs are already labelled as demo data everywhere, so they are not hidden; measured runs that did not
 * pass the release gate keep their ranks and scores behind an explicit reveal. Data is never removed, only gated.
 */
export function useReleaseGate(runId: string, r: MissionResult | null | undefined, ev: ReleaseEvidence | null | undefined): ReleaseGateState {
  const on = useSyncExternalStore(subscribe, () => revealed.has(runId), () => false)
  const setReveal = useCallback((v: boolean) => setRevealed(runId, v), [runId])
  const synthetic = r?.data_status === 'synthetic'
  const released = !!r && isReleased(r, ev ?? null)
  const gated = !!r && !synthetic && !released
  return { released, synthetic, gated, hide: gated && !on, revealed: gated && on, setReveal, label: gateLabel(ev) }
}
