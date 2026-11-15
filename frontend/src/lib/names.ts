import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getSciSites } from './api'
import type { MissionResult } from './types'

/**
 * Human names for site / location ids: result candidate names first, then stored scientific sites
 * (GET /v1/science/sites, shared ['sci-sites'] cache). Falls back to the id itself.
 */
export function useSiteNames(r: MissionResult | null | undefined): (id: string) => string {
  const sci = useQuery({ queryKey: ['sci-sites'], queryFn: getSciSites, retry: false, staleTime: 60_000 })
  return useMemo(() => {
    const m = new Map<string, string>()
    for (const s of sci.data?.sites ?? []) if (s.name) m.set(s.site_id, s.name)
    for (const s of r?.sites ?? []) if (s.name) m.set(s.id, s.name)
    return (id: string) => m.get(id) ?? id
  }, [sci.data, r])
}

/** The run's target locations (Moon/Mars first), as ids. */
export function targetIds(r: MissionResult): string[] {
  const ids = r.target_profiles.map((t) => t.location.id)
  for (const l of r.scope.locations) if (l.body !== 'Earth' && !ids.includes(l.id)) ids.push(l.id)
  return ids
}

/** "Earth analogs for Jezero crater" for match-* missions; otherwise "Mission <id>". */
export function missionTitle(r: MissionResult, name: (id: string) => string): string {
  if (r.mission_id.startsWith('match-')) {
    const t = targetIds(r)
    if (t.length) return `Earth analogs for ${t.map(name).join(', ')}`
  }
  return `Mission ${r.mission_id}`
}
