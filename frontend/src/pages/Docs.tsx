import { Link } from 'react-router-dom'
import { PageHeader, Panel } from '@/components/ui'

const REFS = [
  ['NASA GIBS — Blue Marble Shaded Relief', 'https://nasa-gibs.github.io/gibs-api-docs/'],
  ['NASA Planetary Data System (PDS)', 'https://pds.nasa.gov/'],
  ['LRO LOLA lunar elevation', 'https://pds-geosciences.wustl.edu/missions/lro/lola.htm'],
  ['MGS MOLA Mars elevation', 'https://pds-geosciences.wustl.edu/missions/mgs/mola.html'],
  ['SRTM global elevation (USGS)', 'https://www.usgs.gov/centers/eros/science/usgs-eros-archive-digital-elevation-shuttle-radar-topography-mission-srtm-1'],
  ['NASA Earthdata', 'https://www.earthdata.nasa.gov/'],
]
export default function Docs() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <PageHeader eyebrow="Docs" title="Method, products and restrictions" sub="How TwinSite scores analogues, what it will and won't claim, and where the data comes from." />
      <div className="space-y-5">
        <Panel eyebrow="Method" title="Similarity, coverage and bounds">
          <div className="space-y-3 text-sm text-ivory-dim">
            <p><strong className="text-ivory">Feature similarity.</strong> For each feature, similarity falls from 1 (identical) to 0 as the candidate–target difference reaches the user-set tolerance. It is a unitless index, not a probability.</p>
            <p><strong className="text-ivory">Weights.</strong> Weights are the scientist’s priorities. Target bodies receive equal total weight, split across their reference locations.</p>
            <p><strong className="text-ivory">Coverage and bounds.</strong> Coverage is the weight of features that have attested measurements. Missing features lower coverage and widen the lower/upper utility bounds; they never count as zero similarity.</p>
            <p><strong className="text-ivory">Portfolios.</strong> Up to three sites are chosen to maximise coverage of the target dimensions, minus a redundancy penalty and a cost penalty, within the budget and effort limits you provided. TwinSite never estimates cost or effort.</p>
            <p><strong className="text-ivory">Stability.</strong> Weights are perturbed across seeded scenarios; the share of scenarios in which a portfolio stays on top is reported.</p>
            <p><strong className="text-ivory">Confidence</strong> is reported as three separate readings — QA, coverage, stability — never one blended score.</p>
          </div>
        </Panel>
        <Panel eyebrow="Evidence" title="Release rules">
          <ul className="list-disc space-y-1 pl-5 text-sm text-ivory-dim"><li>Every observation carries source product, granule, checksum, CRS, resolution, period, QA verdict and processing version.</li><li>Synthetic data is always labelled and always blocked from scientific release.</li><li>A missing evidence sidecar means evidence is unavailable, never implicit approval.</li><li>Assumptions and model estimates cannot satisfy required measured features.</li></ul>
        </Panel>
        <Panel eyebrow="Software" title="Restrictions"><ul className="list-disc space-y-1 pl-5 text-sm text-ivory-dim"><li>AI never produces core measurements, weights, eligibility or portfolios; the demo runs with AI disabled.</li><li>No accounts, roles or settings. Uploads are disabled.</li><li>Datasets are public and read-only; queries are server-controlled with no free-form SQL.</li><li>A job starts only when you press Run. Page loads never start work.</li></ul></Panel>
        <Panel eyebrow="Interface" title="Where things are"><ul className="grid gap-1 text-sm sm:grid-cols-2"><li><Link className="underline" to="/workspace">Workspace</Link> — define and run</li><li><Link className="underline" to="/explorer">Explorer</Link> — maps and globe</li><li><Link className="underline" to="/data">Data Explorer</Link> — datasets, raw → derived</li><li><Link className="underline" to="/">Overview</Link> — mission and team</li></ul></Panel>
        <Panel eyebrow="References" title="Data sources"><ul className="space-y-1 text-sm">{REFS.map(([t, u]) => <li key={u}><a className="underline decoration-ember/60 underline-offset-4 hover:text-ember" href={u} target="_blank" rel="noreferrer">{t}</a></li>)}</ul></Panel>
      </div>
    </div>
  )
}
