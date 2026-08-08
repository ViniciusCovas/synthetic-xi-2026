import type { ReactNode } from 'react'

export function Kicker({ children }: { children: ReactNode }) {
  return (
    <p className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.16em] text-brand-dark">
      {children}
    </p>
  )
}

export function PageHeader({ kicker, title, sub }: { kicker: string; title: string; sub?: string }) {
  return (
    <div className="mb-7">
      <Kicker>{kicker}</Kicker>
      <h1 className="mt-1.5 text-[26px] font-bold leading-tight">{title}</h1>
      {sub && <p className="mt-2 max-w-2xl text-[13.5px] leading-relaxed text-ink-2">{sub}</p>}
    </div>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-line bg-card ${className}`}>{children}</div>
  )
}

export function ScoreBar({ value }: { value: number }) {
  const color = value >= 80 ? 'bg-crit' : value >= 55 ? 'bg-seq-400' : 'bg-seq-250/70'
  return (
    <div className="relative h-[5px] overflow-hidden rounded-full bg-raise">
      <div
        className={`absolute inset-y-0 left-0 rounded-full ${color}`}
        style={{ width: `${value}%` }}
      />
    </div>
  )
}

export function Delta({ value }: { value: number }) {
  if (value === 0) return <span className="font-mono text-[11px] text-mut">—</span>
  const up = value > 0
  return (
    <span className={`font-mono text-[11px] font-semibold ${up ? 'text-crit' : 'text-ok'}`}>
      {up ? '↑' : '↓'}{Math.abs(value)}
    </span>
  )
}

const severityStyles: Record<string, { label: string; cls: string }> = {
  alta: { label: 'Presión alta', cls: 'text-crit border-crit/30 bg-crit/10' },
  media: { label: 'Vigilar', cls: 'text-warn border-warn/30 bg-warn/10' },
  oportunidad: { label: 'Oportunidad', cls: 'text-brand-dark border-brand/30 bg-brand-soft' },
  vigente: { label: 'Vigente', cls: 'text-crit border-crit/30 bg-crit/10' },
  transpuesta: { label: 'Transpuesta', cls: 'text-warn border-warn/30 bg-warn/10' },
  'en tramitación': { label: 'En tramitación', cls: 'text-seq-550 border-seq-400/30 bg-seq-400/10' },
  'plazo abierto': { label: 'Plazo abierto', cls: 'text-brand-dark border-brand/30 bg-brand-soft' },
}

export function Badge({ kind }: { kind: string }) {
  const s = severityStyles[kind] ?? { label: kind, cls: 'text-ink-2 border-line bg-raise' }
  return (
    <span
      className={`inline-block rounded-full border px-2.5 py-[3px] font-mono text-[10px] font-semibold uppercase tracking-[0.08em] ${s.cls}`}
    >
      {s.label}
    </span>
  )
}

export function Sparkline({ points, width = 220, height = 48 }: { points: number[]; width?: number; height?: number }) {
  const min = Math.min(...points)
  const max = Math.max(...points)
  const range = max - min || 1
  const step = width / (points.length - 1)
  const coords = points.map((p, i) => `${i * step},${height - 6 - ((p - min) / range) * (height - 12)}`)
  const last = coords[coords.length - 1].split(',').map(Number)
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} className="overflow-visible">
      <polyline points={coords.join(' ')} fill="none" stroke="#3987e5" strokeWidth="2" strokeLinejoin="round" />
      <circle cx={last[0]} cy={last[1]} r="3.5" fill="#5598e7" />
    </svg>
  )
}
