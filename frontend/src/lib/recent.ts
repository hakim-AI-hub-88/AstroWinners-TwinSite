// Remembers run IDs the user started in this browser (no server list endpoint exists in the v1 contract).
export interface RecentRun { runId: string; title: string; body: string; demo: boolean; at: number }
const K = 'twinsite.recent.runs'
export function loadRecent(): RecentRun[] {
  try { return JSON.parse(localStorage.getItem(K) ?? '[]') } catch { return [] }
}
export function rememberRun(r: RecentRun) {
  try { localStorage.setItem(K, JSON.stringify([r, ...loadRecent().filter((x) => x.runId !== r.runId)].slice(0, 8))) } catch { /* ignore */ }
}
