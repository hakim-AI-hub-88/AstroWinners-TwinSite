import type { Body } from './types'

/** Pixels a pointer may travel between down and up and still count as a click (not a drag). */
export const CLICK_TOLERANCE_PX = 4

/** Tracks one pointer gesture: a click is a single-pointer press/release that moved less than the tolerance in total. */
export class ClickTracker {
  private start: { x: number; y: number } | null = null
  private travelled = 0
  private multi = false
  private last: { x: number; y: number } | null = null
  down(x: number, y: number, pointers: number) {
    if (pointers > 1) { this.multi = true; return }
    this.start = { x, y }; this.last = { x, y }; this.travelled = 0; this.multi = false
  }
  move(x: number, y: number) {
    if (!this.last) return
    this.travelled += Math.hypot(x - this.last.x, y - this.last.y)
    this.last = { x, y }
  }
  /** Returns true when the gesture that just ended was a click. */
  up(x: number, y: number, tolerance = CLICK_TOLERANCE_PX): boolean {
    if (!this.start) return false
    this.move(x, y)
    const ok = !this.multi && this.travelled < tolerance
    this.start = null; this.last = null
    return ok
  }
}

/** Round to 4 decimals (~11 m on Earth) for display and requests. */
export const round4 = (v: number) => Math.round(v * 1e4) / 1e4

/** ~1 degree bounding box centred on a point, kept inside the body's lon/lat range. */
export function boxAround(lon: number, lat: number, size = 1): [number, number, number, number] {
  const h = size / 2
  const cLon = Math.min(180 - h, Math.max(-180 + h, lon)), cLat = Math.min(90 - h, Math.max(-90 + h, lat))
  return [round4(cLon - h), round4(cLat - h), round4(cLon + h), round4(cLat + h)]
}

export interface PickedSite { body: Body; lon: number; lat: number; name: string }
export const pointName = (body: Body, lon: number, lat: number) => `${body} point ${lat.toFixed(3)}, ${lon.toFixed(3)}`
