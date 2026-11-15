import { useParams } from 'react-router-dom'
import { Badge, DemoBanner, Notice, PageHeader, Panel, Spinner } from '@/components/ui'
import { EventLog, PhaseTimeline, phaseLabel, splitAgentPhase } from '@/components/Progress'
import { useEvents, useStatus } from '@/lib/hooks'
import { TERMINAL } from '@/lib/types'
import { isDemoRun } from '@/lib/demo'
import { short } from '@/lib/format'

export default function Activity() {
  const { runId = '' } = useParams()
  const status = useStatus(runId)
  const terminal = !!status.data && TERMINAL.includes(status.data.status)
  const { events, error } = useEvents(runId, !terminal)
  if (status.isLoading) return <Spinner />
  if (status.isError) return <div className="mx-auto max-w-3xl px-4 py-10"><Notice tone="bad" title="Run not found">{(status.error as Error).message}</Notice></div>
  const s = status.data!
  const warnings = events.filter((e) => ['retry_wait', 'failed', 'quarantined'].includes(e.state))
  return (
    <>
      {isDemoRun(runId) && <DemoBanner>Lifecycle events are a labelled replay of the P00–P90 phases.</DemoBanner>}
      <div className="mx-auto max-w-7xl px-4 py-8">
        <PageHeader eyebrow="Activity" title="Pipeline timeline" sub="Real committed events from the job worker, phase P00 to P90. Totals are shown only when the worker knows them." />
        <div className="mb-5 flex flex-wrap items-center gap-3 text-sm"><Badge tone={s.status === 'failed' ? 'bad' : terminal ? 'ok' : 'ember'}>{s.status.replace(/_/g, ' ')}</Badge>
          <span className="text-mute">attempt {s.attempt}</span><span className="text-mute">input <span className="mono">{short(s.input_sha256, 16)}</span></span><span className="text-mute">snapshot <span className="mono">{s.source_snapshot_id ?? 'not yet bound'}</span></span></div>
        {s.error && <div className="mb-5"><Notice tone="bad" title="Run error">{s.error}</Notice></div>}
        {error && <div className="mb-5"><Notice title="Event polling issue">{error}</Notice></div>}
        <div className="grid gap-5 lg:grid-cols-[22rem_1fr]">
          <Panel eyebrow="P00 – P90" title="Phases"><PhaseTimeline events={events} /></Panel>
          <div className="space-y-5">
            {warnings.length > 0 && <Panel eyebrow="Warnings" title="Retries, failures, quarantines"><ul className="space-y-1 text-sm">{warnings.map((w) => <li key={w.sequence}><Badge tone="warn">{w.state}</Badge> <span className="mono">{phaseLabel(w)}</span> {splitAgentPhase(w.summary).text}</li>)}</ul></Panel>}
            <Panel eyebrow="History" title="All events"><EventLog events={events} /></Panel>
          </div>
        </div>
      </div>
    </>
  )
}
