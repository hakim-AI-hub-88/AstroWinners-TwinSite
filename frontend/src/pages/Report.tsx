import { Link, useParams } from 'react-router-dom'
import { Btn, DemoBanner, Empty, Notice, PageHeader, Panel, Scroll, Spinner } from '@/components/ui'
import { useEvidence, useResult, useStatus } from '@/lib/hooks'
import { isDemoRun } from '@/lib/demo'
import { reportUrl } from '@/lib/api'
import { isReleased, rankSites, timeBasis, unresolvedGaps } from '@/lib/analysis'
import { download, idx, short, toCsv } from '@/lib/format'

export default function Report() {
  const { runId = '' } = useParams()
  const status = useStatus(runId)
  const ok = status.data?.status === 'completed' || status.data?.status === 'completed_with_limits'
  const result = useResult(runId, ok)
  const evidence = useEvidence(runId, ok)
  if (status.isLoading || (ok && result.isLoading)) return <Spinner />
  if (!ok || !result.data) return <div className="mx-auto max-w-3xl px-4 py-10"><Notice title="Report available after completion">Status: {status.data?.status ?? 'unknown'}. <Link className="underline" to={`/analysis/${runId}`}>View progress</Link></Notice></div>
  const r = result.data, ev = evidence.data ?? null
  const demo = isDemoRun(runId), released = isReleased(r, ev), synthetic = r.data_status === 'synthetic'
  const ranked = rankSites(r.sites).filter((s) => s.rank)
  const csv = () => download(`${runId}-ranking.csv`, toCsv(['rank', 'site', 'body', 'observed_similarity', 'lower_utility', 'upper_utility', 'coverage', 'access'], ranked.map((s) => ({ rank: s.rank, site: s.name, body: s.body, observed_similarity: s.observed_similarity, lower_utility: s.lower_utility, upper_utility: s.upper_utility, coverage: s.coverage, access: s.access }))), 'text/csv')
  return (
    <>
      {(demo || synthetic) && <DemoBanner>This report is built from synthetic fixture values and is not a scientific finding.</DemoBanner>}
      <div className="mx-auto max-w-4xl px-4 py-8 print:text-black">
        <PageHeader eyebrow="Source-backed report" title={`Mission ${r.mission_id}`} sub={<>Run <span className="mono">{runId}</span> · algorithm {r.algorithm_version} · input <span className="mono">{short(r.input_sha256, 16)}</span></>}
          right={<div className="flex flex-wrap gap-2 print:hidden"><Btn onClick={() => download(`${runId}-result.json`, JSON.stringify(r, null, 2))}>Result JSON</Btn><Btn disabled={!ev} onClick={() => download(`${runId}-evidence.json`, JSON.stringify(ev, null, 2))}>Evidence JSON</Btn><Btn onClick={csv}>Ranking CSV</Btn><Btn variant="primary" onClick={() => window.print()}>Print / PDF</Btn></div>} />
        <div className="space-y-5">
          {!ev ? <Notice tone="bad" title="Evidence unavailable">No sidecar — findings below are not approved for citation.</Notice>
            : <Notice tone={released ? 'ok' : 'bad'} title={`Release: ${ev.release_action} · strict gate ${ev.strict_gate_status}`}>{ev.blocking_issues.length ? `Blocking issues: ${ev.blocking_issues.join(', ')}` : 'No blocking issues.'} Time basis: {timeBasis(ev)}.</Notice>}
          <Panel eyebrow="Findings" title="Ranked analogue candidates">
            {ranked.length === 0 ? <Empty>No eligible candidates.</Empty> : <ol className="space-y-2 text-sm">{ranked.map((s) => <li key={s.id}><strong>#{s.rank} {s.name}</strong> ({s.body}) — observed similarity index {idx(s.observed_similarity)}, coverage {idx(s.coverage)}, bounds {idx(s.lower_utility)}–{idx(s.upper_utility)}.</li>)}</ol>}
            <p className="mt-3 text-xs text-mute">Index values are unitless 0–1 scores from the deterministic engine, not probabilities.</p>
          </Panel>
          <Panel eyebrow="Sources" title="Evidence and provenance">
            {ev && ev.assets.length ? <Scroll><table className="tbl"><thead><tr><th>Asset</th><th>Product / version</th><th>Body</th><th>CRS</th><th>Retrieved</th><th>SHA-256</th><th>Source</th></tr></thead>
              <tbody>{ev.assets.map((a) => <tr key={a.asset_id}><td className="mono">{a.asset_id}</td><td>{a.product_id} <span className="mono text-xs text-mute">{a.product_version}</span></td><td>{a.body}</td><td className="mono text-xs">{a.crs}</td><td className="mono text-xs">{a.retrieved_at.slice(0, 10)}</td><td className="mono text-xs">{short(a.sha256, 12)}</td><td><a className="underline" href={a.source_url} target="_blank" rel="noreferrer">link</a></td></tr>)}</tbody></table></Scroll>
              : <Empty>No source assets are attested for this run{synthetic ? ' (synthetic fixture)' : ''}.</Empty>}
            {ev && <p className="mt-3 text-xs text-mute">Snapshot <span className="mono">{ev.source_snapshot_id}</span> · {ev.observations.length} attested observations · {ev.required_evidence_ids.length} required evidence IDs.</p>}
          </Panel>
          <Panel eyebrow="Assumptions & gaps" title="What this report does not establish">
            <ul className="list-disc space-y-1 pl-5 text-sm text-ivory-dim">{[...(ev?.assumptions ?? []), ...unresolvedGaps(r, ev), ...r.limitations].map((g, i) => <li key={i}>{g}</li>)}</ul></Panel>
          {!demo && <Panel eyebrow="Server report" title="Backend-rendered HTML"><iframe title="Server report" sandbox="" src={reportUrl(runId)} className="h-[32rem] w-full rounded border border-line bg-white" /><a className="mt-2 inline-block text-sm underline" href={reportUrl(runId)} target="_blank" rel="noreferrer">Open in new tab</a></Panel>}
        </div>
      </div>
    </>
  )
}
