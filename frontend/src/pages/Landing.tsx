import { Link } from 'react-router-dom'
import { Btn } from '@/components/ui'

const WORKFLOW = [
  ['01', 'Define', 'Choose a Moon or Mars target region, the terrain features that matter and your own weights.'],
  ['02', 'Acquire', 'Public NASA products are pinned into an immutable, checksummed source snapshot.'],
  ['03', 'Clean & validate', 'Units, coordinate systems and masks are checked by a strict QA gate before anything is scored.'],
  ['04', 'Compare', 'A deterministic engine scores Earth analogue sites against each target feature by feature.'],
  ['05', 'Decide', 'Portfolios trade science value against the cost and effort you supply, with alternatives on demand.'],
]
export default function Landing() {
  return (
    <div>
      <section className="relative overflow-hidden border-b border-line">
        <div aria-hidden className="pointer-events-none absolute -right-40 -top-40 h-[34rem] w-[34rem] rounded-full" style={{ background: 'radial-gradient(circle at 35% 35%, #c8642b 0%, #8f4720 38%, #1b1815 72%, transparent 74%)', opacity: 0.55 }} />
        <div className="relative mx-auto max-w-7xl px-4 py-20 sm:py-28">
          <div className="eyebrow mb-4">NASA Space Apps Challenge · Planetary analogue discovery</div>
          <h1 className="max-w-3xl text-5xl leading-[1.05] sm:text-6xl">Find the places on Earth that behave like the Moon and Mars.</h1>
          <p className="mt-6 max-w-2xl text-lg text-ivory-dim">TwinSite compares terrestrial sites with lunar and Martian targets using public NASA data, then ranks them with a transparent, deterministic engine. No black-box scores; every number traces back to a source.</p>
          <div className="mt-8 flex flex-wrap gap-3"><Link to="/workspace"><Btn variant="primary" className="px-6 py-3">Start a mission →</Btn></Link><Link to="/explorer"><Btn className="px-6 py-3">Open the map</Btn></Link><Link to="/docs"><Btn className="px-6 py-3">Read the method</Btn></Link></div>
        </div>
      </section>

      <Section id="problem" eyebrow="The problem" title="Rehearsing for other worlds requires the right place on this one.">
        <div className="grid gap-6 md:grid-cols-2 text-ivory-dim">
          <p>Rover tests, instrument checks and crew training are run at Earth sites chosen because they resemble a target: slope, roughness, dryness, mineralogy. Choosing among thousands of candidates is mostly done by hand and by reputation.</p>
          <p>TwinSite makes that choice inspectable. It turns a target region and your priorities into a ranked shortlist, shows which measurements back each ranking, and says plainly where data is missing instead of guessing.</p>
        </div>
      </Section>

      <Section id="workflow" eyebrow="Workflow" title="From mission setup to a source-backed report">
        <ol className="grid gap-4 md:grid-cols-5">{WORKFLOW.map(([n, t, d]) => <li key={n} className="rounded-md border border-line bg-panel p-4"><div className="mono text-ember">{n}</div><h3 className="mt-2 text-lg">{t}</h3><p className="mt-1 text-sm text-ivory-dim">{d}</p></li>)}</ol>
      </Section>

      <Section id="evidence" eyebrow="NASA evidence" title="Measurements, not model guesses">
        <div className="grid gap-4 md:grid-cols-3">
          {[['Provenance on every value', 'Source product, granule, checksum, CRS, resolution, observation period, QA flag and processing version travel with each measurement.'], ['Strict release gate', 'Synthetic data, missing required measurements, invalid units or failed QA block release. Blocked runs never publish recommendations.'], ['Coverage is not zero', 'Missing data lowers evidence coverage and widens utility bounds; it is never silently treated as a bad score.']].map(([t, d]) => <div key={t} className="rounded-md border border-line bg-panel p-5"><h3 className="text-lg">{t}</h3><p className="mt-2 text-sm text-ivory-dim">{d}</p></div>)}
        </div>
        <p className="mt-4 text-sm text-mute">Datasets are surfaced read-only in the <Link className="underline" to="/data">Data Explorer</Link>, including raw, cleaned and derived stages.</p>
      </Section>

      <Section id="architecture" eyebrow="Architecture" title="Deterministic core, thin interface">
        <div className="grid gap-4 md:grid-cols-4">{[['Data lane', 'Pins and checksums public NASA assets.'], ['Science engine', 'Decodes, cleans, scores. No AI in the measurement path.'], ['API', 'Idempotent jobs, real event stream, evidence sidecar.'], ['This UI', 'Reads results and evidence; runs only on explicit request.']].map(([t, d]) => <div key={t} className="rounded-md border border-line bg-panel p-4"><div className="eyebrow">{t}</div><p className="mt-2 text-sm text-ivory-dim">{d}</p></div>)}</div>
        <p className="mt-4 text-sm text-ivory-dim">The whole demo runs end-to-end with AI disabled. Uploads are disabled; there are no accounts or settings.</p>
      </Section>

      <Section id="usage" eyebrow="Usage" title="Three screens to a result">
        <ol className="list-decimal space-y-2 pl-5 text-ivory-dim"><li><Link className="underline" to="/workspace">Workspace</Link> — set targets, features, thresholds and any cost/effort you want considered, then press Run.</li><li><Link className="underline" to="/workspace">Progress</Link> — watch real P00–P90 pipeline events as they commit.</li><li>Analysis, Portfolios and Report — ranked candidates, trade-offs, and a printable source-backed report.</li></ol>
      </Section>

      <Section id="team" eyebrow="Team" title="Built for the NASA Space Apps Challenge">
        <p className="max-w-2xl text-ivory-dim">TwinSite is a Space Apps Challenge 2026 entry. Team and credits are listed here at submission; datasets belong to their NASA data providers and are used under their published terms.</p>
      </Section>
    </div>
  )
}
function Section({ id, eyebrow, title, children }: { id: string; eyebrow: string; title: string; children: React.ReactNode }) {
  return <section id={id} className="border-b border-line"><div className="mx-auto max-w-7xl px-4 py-14"><div className="eyebrow mb-2">{eyebrow}</div><h2 className="mb-6 max-w-3xl text-3xl">{title}</h2>{children}</div></section>
}
