import { useEffect, useState } from 'react'
import { getAlerts, getCompanies, market } from '../lib/data'
import type { Alert, Company } from '../data/seed'
import { Badge, Card, Delta, PageHeader, ScoreBar } from '../components/ui'

export default function Radar() {
  const [companies, setCompanies] = useState<Company[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])

  useEffect(() => {
    getCompanies().then(setCompanies)
    getAlerts().then(setAlerts)
  }, [])

  return (
    <div>
      <PageHeader
        kicker={`${market.name} · ${market.role} · actualizado ${market.updated}`}
        title="Radar de presión de contratación"
        sub="Quién está compitiendo por tu talento esta semana, ordenado por el índice 0–100. Cada score se descompone en sus señales: nada de cajas negras."
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-2.5">
          {companies.map((c) => (
            <Card key={c.id} className="p-4">
              <div className="grid grid-cols-[minmax(110px,170px)_1fr_auto_auto] items-center gap-4">
                <div>
                  <b className="block text-[15px] font-bold">{c.name}</b>
                  <span className="text-xs text-mut">
                    {c.sector} · {c.openings} vacante{c.openings !== 1 ? 's' : ''}
                  </span>
                  {c.financialSignal && (
                    <span className="mt-1 block">
                      <span className="rounded bg-brand-soft px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider text-brand-dark">
                        señal financiera
                      </span>
                    </span>
                  )}
                </div>
                <ScoreBar value={c.score} />
                <Delta value={c.delta} />
                <span className="w-10 text-right font-mono text-xl font-bold tabular-nums">{c.score}</span>
              </div>
              <p className="mt-2.5 text-[13px] leading-relaxed text-ink-2">{c.why}</p>
            </Card>
          ))}
        </div>

        <div className="space-y-2.5">
          <h2 className="font-mono text-[11.5px] font-bold uppercase tracking-[0.13em] text-mut">
            Alertas de la semana
          </h2>
          {alerts.map((a) => (
            <Card key={a.id} className="p-4">
              <Badge kind={a.severity} />
              <b className="mt-2 block text-sm font-bold leading-snug">{a.title}</b>
              <p className="mt-1 text-[13px] leading-relaxed text-ink-2">{a.body}</p>
              <p className="mt-2 text-[13px] leading-relaxed">
                <span className="font-bold text-brand">→ </span>
                {a.action}
              </p>
            </Card>
          ))}
        </div>
      </div>
    </div>
  )
}
