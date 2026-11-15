import type { Footprint, Pin } from '@/components/PlanetMap'
import type { SciSite } from './api'
import { rankSites } from './analysis'
import type { Body, MissionResult } from './types'

/** Target / search footprints for one body: scope locations plus any target-profile location not already in scope. */
export function footprintsFor(r: MissionResult | undefined | null, body: Body): Footprint[] {
  const fps: Footprint[] = []
  if (!r) return fps
  for (const l of r.scope.locations) if (l.body === body) fps.push({ id: l.id, label: l.id, bbox: l.bbox, kind: l.kind })
  for (const t of r.target_profiles) if (t.location.body === body && !fps.some((f) => f.id === t.location.id)) fps.push({ id: t.location.id, label: `${t.location.id} (target)`, bbox: t.location.bbox, kind: t.location.kind })
  return fps
}

/** Candidate pins on one body. With `withRank: false` the rank is hidden (release gate withholds the ranking). */
export function candidatePins(r: MissionResult | undefined | null, body: Body, withRank = true): Pin[] {
  if (!r) return []
  return rankSites(r.sites).filter((s) => s.body === body)
    .map((s) => ({ id: s.id, label: s.name, lon: s.longitude, lat: s.latitude, rank: withRank ? s.rank : null, eligible: withRank ? s.eligible : undefined, kind: 'candidate' as const }))
}

/** Stored scientific sites on one body, as non-ranked pins. Ids are prefixed so they never collide with candidates. */
export function storedSitePins(sites: SciSite[] | undefined, body: Body): Pin[] {
  return (sites ?? []).filter((s) => s.body === body && s.lon != null && s.lat != null)
    .map((s) => ({ id: `sci:${s.site_id}`, label: `${s.name} (${s.observation_count} obs)`, lon: s.lon!, lat: s.lat!, kind: 'stored' as const }))
}

/** Bodies that carry target footprints in a result, Moon/Mars first. */
export function targetBodies(r: MissionResult): Body[] {
  const set = new Set<Body>()
  for (const t of r.target_profiles) set.add(t.location.body as Body)
  for (const l of r.scope.locations) if (l.body !== 'Earth') set.add(l.body as Body)
  const order: Body[] = ['Moon', 'Mars', 'Earth']
  return order.filter((b) => set.has(b))
}
