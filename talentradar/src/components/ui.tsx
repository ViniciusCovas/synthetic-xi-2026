import type { ReactNode } from 'react'

export function Kicker({ children }: { children: ReactNode }) {
  return (
    <p className="font-mono text-[11.5px] font-bold uppercase tracking-[0.13em] text-brand">
      {children}
    </p>
  )
}

export function PageHeader({ kicker, title, sub }: { kicker: string; title: string; sub?: string }) {
  return (
    <div className="mb-6">
      <Kicker>{kicker}</Kicker>
      <h1 className="mt-1 text-2xl font-extrabold tracking-tight">{title}</h1>
      {sub && <p className="mt-1 max-w-2xl text-sm text-ink-2">{sub}</p>}
    </div>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-ink/10 bg-card ${className}`}>{children}</div>
  )
}

export function ScoreBar({ value }: { value: number }) {
  const color = value >= 80 ? 'bg-seq-550' : value >= 55 ? 'bg-seq-400' : 'bg-seq-250'
  return (
    <div className="relative h-2.5 overflow-hidden rounded-full border border-line bg-paper">
      <div className={`absolute inset-y-0 left-0 rounded-full ${color}`} style={{ width: `${value}%` }} />
    </div>
  )
}

export function Delta({ value }: { value: number }) {
  if (value === 0) return <span className="font-mono text-xs text-mut">=</span>
  const up = value > 0
  return (
    <span className={`font-mono text-xs font-bold ${up ? 'text-crit' : 'text-ok'}`}>
      {up ? '▲' : '▼'} {Math.abs(value)}
    </span>
  )
}

const severityStyles: Record<string, { label: string; cls: string }> = {
  alta: { label: 'Presión alta', cls: 'bg-crit/10 text-crit' },
  media: { label: 'Vigilar', cls: 'bg-warn/15 text-[#a06f00]' },
  oportunidad: { label: 'Oportunidad', cls: 'bg-brand-soft text-brand-dark' },
  vigente: { label: 'Vigente', cls: 'bg-crit/10 text-crit' },
  transpuesta: { label: 'Transpuesta', cls: 'bg-warn/15 text-[#a06f00]' },
  'en tramitación': { label: 'En tramitación', cls: 'bg-seq-250/25 text-seq-550' },
  'plazo abierto': { label: 'Plazo abierto', cls: 'bg-brand-soft text-brand-dark' },
}

export function Badge({ kind }: { kind: string }) {
  const s = severityStyles[kind] ?? { label: kind, cls: 'bg-line text-ink-2' }
  return (
    <span className={`inline-block rounded px-2 py-0.5 font-mono text-[10.5px] font-bold uppercase tracking-wider ${s.cls}`}>
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
      <circle cx={last[0]} cy={last[1]} r="3.5" fill="#1c5cab" />
    </svg>
  )
}
