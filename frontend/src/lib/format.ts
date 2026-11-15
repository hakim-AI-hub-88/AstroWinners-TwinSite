export const idx = (v: number | null | undefined, d = 3) => (v == null || Number.isNaN(v) ? '—' : v.toFixed(d))
export const money = (v: number | null | undefined) => (v == null ? 'not provided' : v.toLocaleString('en-US'))
export const days = (v: number | null | undefined) => (v == null ? 'not provided' : `${v} d`)
export const ts = (s?: string) => (s ? s.replace('T', ' ').replace(/\.\d+Z$|Z$/, ' UTC') : '—')
export const short = (s: string, n = 12) => (s.length > n ? `${s.slice(0, n)}…` : s)
export function download(name: string, content: string, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const a = document.createElement('a')
  a.href = url; a.download = name; a.click()
  URL.revokeObjectURL(url)
}
export function toCsv(cols: string[], rows: Array<Record<string, unknown>>) {
  const esc = (v: unknown) => { const s = v == null ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s }
  return [cols.join(','), ...rows.map((r) => cols.map((c) => esc(r[c])).join(','))].join('\n')
}
