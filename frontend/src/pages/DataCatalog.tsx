import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Badge, Btn, DemoBanner, Empty, PageHeader, QueryError, Scroll, Spinner } from '@/components/ui'
import { getCatalog } from '@/lib/api'
import { ScienceGateway } from '@/components/ScienceGateway'

export default function DataCatalog() {
  const nav = useNavigate()
  const q = useQuery({ queryKey: ['catalog'], queryFn: getCatalog })
  const [text, setText] = useState(''), [body, setBody] = useState('all'), [domain, setDomain] = useState('all'), [picked, setPicked] = useState<string[]>([])
  const items = q.data?.data ?? []
  const domains = useMemo(() => [...new Set(items.map((d) => d.domain))], [items])
  const rows = items.filter((d) => (body === 'all' || d.body === body) && (domain === 'all' || d.domain === domain) && `${d.dataset_id} ${d.title} ${d.source}`.toLowerCase().includes(text.toLowerCase()))
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length >= 2 ? [p[1], id] : [...p, id]))
  return (
    <>
      {q.data?.demo && <DemoBanner>{q.data.note}</DemoBanner>}
      <div className="mx-auto max-w-7xl px-4 py-8">
        <PageHeader eyebrow="Data Explorer · read-only" title="Public datasets" sub="Approved, curated source records with their cleaned and derived stages. Nothing here can be edited or queried with free-form SQL." />
        <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_10rem_12rem_auto]">
          <div><label className="fld" htmlFor="q">Search</label><input id="q" placeholder="Dataset, title or source" value={text} onChange={(e) => setText(e.target.value)} /></div>
          <div><label className="fld" htmlFor="b">Body</label><select id="b" value={body} onChange={(e) => setBody(e.target.value)}><option value="all">All</option>{['Earth', 'Moon', 'Mars', 'Multi'].map((b) => <option key={b}>{b}</option>)}</select></div>
          <div><label className="fld" htmlFor="d">Domain</label><select id="d" value={domain} onChange={(e) => setDomain(e.target.value)}><option value="all">All</option>{domains.map((d) => <option key={d}>{d}</option>)}</select></div>
          <div className="flex items-end"><Btn variant="primary" disabled={picked.length !== 2} onClick={() => nav(`/data/${picked[0]}?tab=compare&with=${picked[1]}`)}>Compare selected ({picked.length}/2)</Btn></div>
        </div>
        {q.isLoading ? <Spinner /> : q.isError ? <QueryError error={q.error} what="the dataset catalog" /> : rows.length === 0 ? <Empty>No datasets match these filters.</Empty> : (
          <Scroll><table className="tbl rounded-md border border-line bg-panel">
            <caption className="sr-only">Dataset catalog</caption>
            <thead><tr><th><span className="sr-only">Select</span></th><th>Dataset ID</th><th>Name</th><th>Source</th><th>Body</th><th>Domain</th><th>Records</th><th>Resolution</th><th>Temporal</th><th>Status</th></tr></thead>
            <tbody>{rows.map((d) => (
              <tr key={d.dataset_id}>
                <td><input className="!w-4" type="checkbox" aria-label={`Select ${d.dataset_id} for compare`} checked={picked.includes(d.dataset_id)} onChange={() => toggle(d.dataset_id)} /></td>
                <td className="mono"><Link className="underline decoration-ember/60 underline-offset-4" to={`/data/${d.dataset_id}`}>{d.dataset_id}</Link></td>
                <td>{d.title}</td><td className="text-ivory-dim">{d.source}</td><td>{d.body}</td><td>{d.domain}</td><td className="mono">{d.records?.toLocaleString() ?? '—'}</td><td>{d.resolution ?? '—'}</td><td>{d.temporal_coverage ?? '—'}</td>
                <td><Badge tone={d.data_status === 'synthetic' ? 'warn' : d.qa_status === 'ACCEPT' ? 'ok' : 'mute'}>{d.data_status === 'synthetic' ? 'synthetic' : (d.qa_status ?? 'unknown')}</Badge></td>
              </tr>))}</tbody>
          </table></Scroll>)}
        {!q.data?.demo && <div className="mt-8"><ScienceGateway /></div>}
      </div>
    </>
  )
}
