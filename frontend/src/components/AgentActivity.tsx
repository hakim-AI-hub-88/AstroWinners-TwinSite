import { useQuery } from '@tanstack/react-query'
import { Badge, Notice, Panel, Scroll } from '@/components/ui'
import { getAgents, type AgentRecord } from '@/lib/api'
import { isDemoRun } from '@/lib/demo'

const TONE: Record<AgentRecord['execution'], 'ok' | 'ember' | 'mute' | 'bad' | 'warn'> = {
  ai: 'ember', ai_cached: 'ember', deterministic: 'ok', skipped: 'mute', failed: 'bad', fallback: 'warn',
}
const LABEL: Record<AgentRecord['execution'], string> = {
  ai: 'AI · real call', ai_cached: 'AI · cached real call', deterministic: 'deterministic', skipped: 'skipped', failed: 'failed', fallback: 'Simple Analysis fallback',
}

/** Real agent activity from /v1/missions/{id}/agents. Shows only what the worker recorded. */
export function AgentActivity({ runId, live }: { runId: string; live: boolean }) {
  const q = useQuery({
    queryKey: ['agents', runId], queryFn: () => getAgents(runId), enabled: !isDemoRun(runId),
    refetchInterval: (query) => (live || !query.state.data?.records?.length) && query.state.data?.analysis_mode !== 'simple' ? 2000 : false,
  })
  if (isDemoRun(runId)) return null
  const t = q.data
  if (!t) return null
  if (t.analysis_mode === 'simple') {
    return <Panel eyebrow="Analysis mode" title="Simple Analysis"><p className="text-sm text-ivory-dim">This mission ran in Simple Analysis mode: deterministic science only, no AI agents were invoked.</p></Panel>
  }
  const narrative = t.records.find((r) => r.agent_id === 'A13' && r.output)?.output?.narrative as string | undefined
  const executed = t.ai_roles_executed ?? []
  return (
    <Panel eyebrow="AI-Powered Analysis · 13 agent roles" title="Agent activity"
      action={executed.length ? <Badge tone="ember">{executed.length} AI roles executed</Badge> : undefined}>
      {!t.records.length && <p className="text-sm text-mute">Agents run after the deterministic engine finishes. Waiting for real agent events…</p>}
      {t.ai_available === false && <Notice tone="warn" title="AI unavailable: Simple Analysis delivered">{t.fallback_reason ?? 'No free AI provider was available.'} All numbers, eligibility and the release gate come from the deterministic engine.</Notice>}
      {narrative && (
        <div className="mb-4 rounded-md border border-ember/40 bg-ink/40 p-3">
          <div className="mb-1 text-xs uppercase tracking-wide text-ember">A13 Report Writer · advisory, evidence-cited</div>
          <p className="whitespace-pre-line text-sm text-ivory">{narrative}</p>
        </div>
      )}
      {t.records.length > 0 && (
        <Scroll><table className="tbl">
          <caption className="sr-only">Agent execution records</caption>
          <thead><tr><th>Role</th><th>Execution</th><th>Provider / model</th><th>Summary</th></tr></thead>
          <tbody>{t.records.map((r) => (
            <tr key={r.agent_id}>
              <td className="whitespace-nowrap"><span className="mono text-ember">{r.agent_id}</span> {r.role}<div className="text-xs text-mute">{r.phase}</div></td>
              <td><Badge tone={TONE[r.execution]}>{LABEL[r.execution]}</Badge></td>
              <td className="mono text-xs">{r.inference?.provider ? `${r.inference.provider} / ${r.inference.model}${r.inference.cached ? '' : ` · ${r.inference.latency_ms} ms`}` : '—'}
                {r.inference && !r.inference.ok && r.inference.error && <div className="text-bad">{r.inference.error.slice(0, 140)}</div>}</td>
              <td className="text-sm text-ivory-dim">{r.summary}</td>
            </tr>))}</tbody>
        </table></Scroll>
      )}
      <p className="mt-3 text-xs text-mute">AI roles interpret, propose labelled scenarios, synthesise and review; every AI claim must cite evidence IDs. The deterministic engine owns all measurements, scores, eligibility and the release decision. This is not a scientific certification.</p>
    </Panel>
  )
}
