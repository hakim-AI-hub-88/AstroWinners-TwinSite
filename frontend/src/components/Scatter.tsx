import type { Portfolio } from '@/lib/types'

/** Cost vs objective. Points with no user-provided cost sit in a separate "cost not provided" lane. */
export function TradeoffChart({ items, names, selected, onSelect }: { items: Portfolio[]; names: Record<string, string>; selected: number | null; onSelect: (i: number) => void }) {
  const W = 640, H = 300, L = 56, R = 24, T = 16, B = 44, gapLane = 70
  const costs = items.map((p) => p.cost).filter((c): c is number => c != null)
  const hasNull = items.some((p) => p.cost == null)
  const cMin = costs.length ? Math.min(...costs) : 0, cMax = costs.length ? Math.max(...costs) : 1
  const objs = items.map((p) => p.objective), oMin = Math.min(...objs, 0), oMax = Math.max(...objs, 0.01)
  const plotW = W - L - R - (hasNull ? gapLane : 0)
  const x = (p: Portfolio) => (p.cost == null ? W - R - gapLane / 2 : L + (cMax === cMin ? plotW / 2 : ((p.cost - cMin) / (cMax - cMin)) * plotW))
  const y = (v: number) => T + (1 - (v - oMin) / (oMax - oMin || 1)) * (H - T - B)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Scatter chart of portfolio objective against cost" className="w-full">
      <line x1={L} y1={H - B} x2={W - R} y2={H - B} stroke="#2c2824" /><line x1={L} y1={T} x2={L} y2={H - B} stroke="#2c2824" />
      {[0, 0.5, 1].map((t) => { const v = oMin + t * (oMax - oMin); return <g key={t}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="#2c2824" strokeDasharray="3 4" /><text x={L - 8} y={y(v) + 4} fill="#8a8274" fontSize="10" textAnchor="end">{v.toFixed(2)}</text></g> })}
      <text x={(L + W - R - (hasNull ? gapLane : 0)) / 2} y={H - 8} fill="#8a8274" fontSize="11" textAnchor="middle">Cost (user-provided units)</text>
      <text transform={`translate(14 ${(T + H - B) / 2}) rotate(-90)`} fill="#8a8274" fontSize="11" textAnchor="middle">Objective</text>
      {costs.length > 0 && [cMin, cMax].map((c, i) => <text key={i} x={L + (cMax === cMin ? plotW / 2 : i * plotW)} y={H - B + 16} fill="#8a8274" fontSize="10" textAnchor="middle">{c}</text>)}
      {hasNull && <text x={W - R - gapLane / 2} y={H - B + 16} fill="#8a8274" fontSize="10" textAnchor="middle">no cost</text>}
      {items.map((p, i) => (
        <g key={i} tabIndex={0} role="button" aria-label={`${p.site_ids.map((s) => names[s] ?? s).join(' + ')}: objective ${p.objective.toFixed(3)}, cost ${p.cost ?? 'not provided'}`} onClick={() => onSelect(i)} onKeyDown={(e) => e.key === 'Enter' && onSelect(i)} style={{ cursor: 'pointer' }}>
          <circle cx={x(p)} cy={y(p.objective)} r={selected === i ? 9 : 6.5} fill={p.kind === 'combined' ? '#c8642b' : 'none'} stroke={p.kind === 'combined' ? '#c8642b' : '#efe7d6'} strokeWidth="1.6" />
          <title>{p.site_ids.join(' + ')} · {p.kind}</title>
        </g>
      ))}
    </svg>
  )
}
