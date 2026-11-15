import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import EarthMap from '@/components/EarthMap'
import { Btn } from '@/components/ui'
import { searchPlaces, type Place } from '@/lib/api'

type Picked = { lon: number; lat: number; name: string }

/** Worldwide place-name search (GET /v1/science/places). Choosing a result calls `onPick`. */
export function PlaceSearch({ onPick, compact = false }: { onPick: (v: Picked) => void; compact?: boolean }) {
  const [q, setQ] = useState(''), [submitted, setSubmitted] = useState('')
  const places = useQuery({ queryKey: ['places', submitted], queryFn: () => searchPlaces(submitted), enabled: submitted.length >= 2, retry: false })
  const label = (p: Place) => [p.name, p.admin1, p.country].filter(Boolean).join(', ')
  return (
    <div className="space-y-2">
      <form className="flex gap-2" role="search" onSubmit={(e) => { e.preventDefault(); setSubmitted(q.trim()) }}>
        <input aria-label="Search any place on Earth" placeholder={compact ? 'Search a place on Earth' : 'Search any place on Earth (e.g. Atacama, Devon Island, Rio Tinto)'} value={q} onChange={(e) => setQ(e.target.value)} />
        <Btn variant="primary" disabled={q.trim().length < 2}>Search</Btn>
      </form>
      {places.isFetching && <p className="text-xs text-mute">Searching…</p>}
      {places.isError && <p className="text-xs text-bad">Place search unavailable: {(places.error as Error).message}. You can still click the map.</p>}
      {places.data && (places.data.places.length ? (
        <ul className="max-h-48 overflow-auto rounded-md border border-line text-sm">
          {places.data.places.map((p) => (
            <li key={`${p.latitude},${p.longitude}`}>
              <button type="button" className="w-full px-3 py-2 text-left hover:bg-ember/10" onClick={() => onPick({ lon: p.longitude, lat: p.latitude, name: label(p) })}>
                {label(p)} <span className="mono text-xs text-mute">{p.latitude.toFixed(3)}, {p.longitude.toFixed(3)}</span>
              </button>
            </li>))}
        </ul>) : <p className="text-xs text-mute">No places found.</p>)}
      {places.data && <p className="text-[10px] text-mute">{places.data.attribution}</p>}
    </div>
  )
}

/** Pick any Earth location: search a worldwide place list, or click the 2D map / 3D globe. */
export function LocationPicker({ value, onChange }: { value: Picked | null; onChange: (v: Picked) => void }) {
  const [globe, setGlobe] = useState(false)
  const pins = value ? [{ id: 'picked', label: value.name, lon: value.lon, lat: value.lat, rank: 1 }] : []
  return (
    <div className="space-y-3">
      <PlaceSearch onPick={onChange} />
      <div className="flex items-center justify-between text-xs text-mute">
        <span>Or click anywhere on the {globe ? '3D globe' : '2D map'} to pick a point.</span>
        <div role="radiogroup" aria-label="Map view" className="flex gap-1">
          {([false, true] as const).map((g) => (
            <button key={String(g)} type="button" role="radio" aria-checked={globe === g} onClick={() => setGlobe(g)}
              className={`rounded-full border px-3 py-1 ${globe === g ? 'border-ember text-ember' : 'border-line'}`}>{g ? '3D globe' : '2D map'}</button>))}
        </div>
      </div>
      <EarthMap pins={pins} footprints={[]} globe={globe} layers={{ pins: true, footprints: false, basemap: true }}
        onPick={(lon, lat) => onChange({ lon, lat, name: `Point ${lat.toFixed(3)}, ${lon.toFixed(3)}` })} />
    </div>
  )
}
