import { PHASES, PHASE_LABEL, type ProgressEvent } from '@/lib/types'
import { Badge, Empty } from './ui'
import { ts } from '@/lib/format'

const tone = { queued: 'mute', running: 'ember', retry_wait: 'warn', succeeded: 'ok', failed: 'bad', cancelled: 'mute', quarantined: 'warn' } as const

export function PhaseTimeline({ events }: { events: ProgressEvent[] }) {
  const latest = new Map<string, ProgressEvent>()
  for (const e of events) latest.set(e.phase, e)
  return (
    <ol className="space-y-0" aria-label="Pipeline phases">
      {PHASES.map((p) => {
        const e = latest.get(p)
        return (
          <li key={p} className="flex items-start gap-3 border-b border-line py-2.5 last:border-0">
            <span className={`mono mt-0.5 w-10 text-xs ${e ? 'text-ember' : 'text-mute'}`}>{p}</span>
            <div className="flex-1">
              <div className="text-sm">{PHASE_LABEL[p]}</div>
              <div className="text-xs text-mute">{e ? <>{e.summary}{e.total_units != null && <> · {e.completed_units}/{e.total_units} units</>}</> : 'Waiting — no event emitted yet'}</div>
            </div>
            {e ? <Badge tone={tone[e.state]}>{e.state.replace('_', ' ')}</Badge> : <Badge>pending</Badge>}
          </li>
        )
      })}
    </ol>
  )
}
export function EventLog({ events }: { events: ProgressEvent[] }) {
  if (!events.length) return <Empty>No events emitted yet. Only real committed events appear here — no estimated progress.</Empty>
  return (
    <div className="overflow-x-auto" tabIndex={0}><table className="tbl">
      <thead><tr><th>#</th><th>Time</th><th>Phase</th><th>State</th><th>Task / attempt</th><th>Summary</th></tr></thead>
      <tbody>{[...events].reverse().map((e) => (
        <tr key={e.sequence}><td className="mono">{e.sequence}</td><td className="mono whitespace-nowrap text-xs">{ts(e.timestamp)}</td><td className="mono">{e.phase}</td>
          <td><Badge tone={tone[e.state]}>{e.state.replace('_', ' ')}</Badge></td><td className="mono text-xs text-ivory-dim">{e.task_id}<br />{e.attempt_id}</td>
          <td>{e.summary}{e.artifact_ids.length > 0 && <div className="mono text-xs text-mute">artifacts: {e.artifact_ids.join(', ')}</div>}</td></tr>))}</tbody>
    </table></div>
  )
}
