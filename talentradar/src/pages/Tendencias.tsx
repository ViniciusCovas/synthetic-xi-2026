import { useEffect, useState } from 'react'
import { getTrendSeries, market } from '../lib/data'
import type { TrendPoint } from '../data/seed'
import { Card, PageHeader } from '../components/ui'

export default function Tendencias() {
  const [series, setSeries] = useState<TrendPoint[]>([])

  useEffect(() => {
    getTrendSeries().then(setSeries)
  }, [])

  if (series.length === 0) return null

  const max = Math.max(...series.map((s) => s.postings))
  const first = series[0].postings
  const last = series[series.length - 1].postings
  const growth = Math.round(((last - first) / first) * 100)

  return (
    <div>
      <PageHeader
        kicker={`${market.name} · ${market.role}`}
        title="Tendencia de vacantes"
        sub="Vacantes nuevas publicadas por semana en tu mercado y función. La aceleración sostenida anticipa presión salarial a 60–90 días."
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="p-5">
          <div className="text-3xl font-extrabold tracking-tight">{last}</div>
          <div className="mt-1 text-[13px] text-ink-2">vacantes nuevas esta semana</div>
        </Card>
        <Card className="p-5">
          <div className="text-3xl font-extrabold tracking-tight text-crit">+{growth}%</div>
          <div className="mt-1 text-[13px] text-ink-2">crecimiento en 8 semanas — el mercado se está calentando</div>
        </Card>
        <Card className="p-5">
          <div className="text-3xl font-extrabold tracking-tight">3</div>
          <div className="mt-1 text-[13px] text-ink-2">semanas consecutivas de subida</div>
        </Card>
      </div>

      <Card className="mt-4 p-6">
        <h3 className="text-sm font-bold">Vacantes nuevas por semana</h3>
        <div className="mt-5 flex items-end gap-2" style={{ height: 180 }}>
          {series.map((s) => (
            <div key={s.week} className="flex flex-1 flex-col items-center gap-2" title={`${s.week}: ${s.postings} vacantes`}>
              <span className="font-mono text-[11px] font-semibold tabular-nums text-ink-2">{s.postings}</span>
              <div
                className={`w-full max-w-[52px] rounded-t ${s === series[series.length - 1] ? 'bg-seq-550' : 'bg-seq-400'}`}
                style={{ height: `${(s.postings / max) * 130}px` }}
              />
              <span className="font-mono text-[10.5px] text-mut">{s.week}</span>
            </div>
          ))}
        </div>
        <p className="mt-4 border-t border-line pt-3 text-xs text-mut">
          Serie de demostración hasta que el pipeline de ingesta acumule histórico propio. En producción: TheirStack/Adzuna diario, normalizado con la taxonomía ESCO.
        </p>
      </Card>
    </div>
  )
}
