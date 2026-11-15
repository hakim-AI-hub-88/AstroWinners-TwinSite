import type { ReactNode } from 'react'
import type { ReleaseGateState } from '@/lib/release'

/**
 * Shared presentation of the release gate. When ranks/scores are hidden it shows why and an explicit reveal button;
 * once revealed it labels everything below as unreleased diagnostic values with a way to hide them again.
 * Renders nothing for released or synthetic runs.
 */
export function ReleaseGateNotice({ gate, what = 'ranks and scores' }: { gate: ReleaseGateState; what?: string }) {
  if (!gate.gated) return null
  return (
    <div role="alert" data-testid="release-gate" className="rounded-md border border-bad/50 bg-bad/10 px-4 py-3 text-sm">
      <div className="break-words font-semibold">{gate.label}</div>
      <div className="mt-1 text-ivory-dim">
        {gate.hide
          ? <>This measured run has not passed the release gate, so its {what} are withheld and nothing is presented as a finding. <button type="button" className="underline hover:text-ivory" onClick={() => gate.setReveal(true)}>Show unreleased diagnostic values</button></>
          : <>DIAGNOSTIC — the {what} shown are not released. Do not cite. <button type="button" className="underline hover:text-ivory" onClick={() => gate.setReveal(false)}>Hide unreleased values</button></>}
      </div>
    </div>
  )
}

/** Renders `children` only when allowed; otherwise the gate notice alone. */
export function Gated({ gate, what, children }: { gate: ReleaseGateState; what?: string; children: ReactNode }) {
  return <>{gate.gated && <div className="mb-4"><ReleaseGateNotice gate={gate} what={what} /></div>}{!gate.hide && children}</>
}
