import { type ReactNode } from 'react'
import { DEMO_MARK } from '@/lib/demo'

export const cx = (...a: Array<string | false | null | undefined>) => a.filter(Boolean).join(' ')

export function Panel({ title, eyebrow, action, children, className }: { title?: ReactNode; eyebrow?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx('rounded-md border border-line bg-panel', className)}>
      {(title || eyebrow || action) && (
        <header className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
          <div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}{title && <h2 className="text-lg leading-snug">{title}</h2>}</div>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

const tones = {
  ok: 'border-ok/50 text-ok', warn: 'border-warn/60 text-warn', bad: 'border-bad/60 text-bad',
  mute: 'border-line text-ivory-dim', ember: 'border-ember/70 text-ember',
} as const
export function Badge({ tone = 'mute', children, title }: { tone?: keyof typeof tones; children: ReactNode; title?: string }) {
  return <span title={title} className={cx('inline-block whitespace-nowrap rounded-full border px-2 py-0.5 text-[0.68rem] font-medium uppercase tracking-wider', tones[tone])}>{children}</span>
}

export function DemoBanner({ children }: { children?: ReactNode }) {
  return (
    <div role="note" data-testid="demo-banner" className="border-y border-warn/50 bg-warn/10 px-4 py-2 text-sm text-warn">
      <strong className="mr-2 tracking-wider">{DEMO_MARK}.</strong>{children}
    </div>
  )
}
export function Notice({ tone = 'warn', title, children }: { tone?: 'warn' | 'bad' | 'ok' | 'mute'; title: string; children?: ReactNode }) {
  return (
    <div role={tone === 'bad' ? 'alert' : 'note'} className={cx('rounded-md border px-4 py-3 text-sm', tone === 'bad' ? 'border-bad/50 bg-bad/10' : tone === 'ok' ? 'border-ok/40 bg-ok/10' : tone === 'mute' ? 'border-line bg-panel2' : 'border-warn/50 bg-warn/10')}>
      <div className="font-semibold">{title}</div>{children && <div className="mt-1 text-ivory-dim">{children}</div>}
    </div>
  )
}
export function Tabs<T extends string>({ tabs, value, onChange, label }: { tabs: Array<{ id: T; label: string }>; value: T; onChange: (t: T) => void; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="flex flex-wrap gap-1 rounded-full border border-line bg-panel p-1">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={cx('rounded-full px-3.5 py-1.5 text-sm transition', value === t.id ? 'bg-ember text-ink font-medium' : 'text-ivory-dim hover:text-ivory')}>{t.label}</button>
      ))}
    </div>
  )
}
export function Btn({ variant = 'ghost', className, ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' }) {
  return <button {...p} className={cx('rounded-full px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40', variant === 'primary' ? 'bg-ember text-ink hover:bg-ember/85' : 'border border-line text-ivory hover:border-ivory-dim', className)} />
}
export function PageHeader({ eyebrow, title, sub, right }: { eyebrow?: string; title: ReactNode; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>{eyebrow && <div className="eyebrow mb-2">{eyebrow}</div>}<h1 className="text-3xl leading-tight sm:text-4xl">{title}</h1>{sub && <p className="mt-2 max-w-3xl text-ivory-dim">{sub}</p>}</div>
      {right}
    </div>
  )
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-dashed border-line p-6 text-center text-sm text-mute">{children}</div>
}
export function Spinner({ label = 'Loading' }: { label?: string }) {
  return <div role="status" className="p-6 text-sm text-mute">{label}…</div>
}
export function Scroll({ children }: { children: ReactNode }) {
  return <div className="overflow-x-auto" tabIndex={0}>{children}</div>
}
/** Horizontal bar for a 0–1 index. Deliberately unlabelled as a percentage. */
export function Meter({ value, label }: { value: number | null; label?: string }) {
  const v = value == null ? 0 : Math.max(0, Math.min(1, value))
  return (
    <div className="flex items-center gap-2" role="img" aria-label={`${label ?? 'index'} ${value == null ? 'unavailable' : value.toFixed(3)} on a 0 to 1 scale`}>
      <div className="h-1.5 w-24 rounded bg-line"><div className="h-1.5 rounded bg-ember" style={{ width: `${v * 100}%` }} /></div>
      <span className="mono text-xs text-ivory-dim">{value == null ? '—' : value.toFixed(3)}</span>
    </div>
  )
}
