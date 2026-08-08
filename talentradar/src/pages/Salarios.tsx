import { useEffect, useState } from 'react'
import { getSalaryBands, market } from '../lib/data'
import type { SalaryBand } from '../data/seed'
import { Card, PageHeader } from '../components/ui'

const fmt = (n: number) => n.toLocaleString('es-ES') + ' €'

const tensionCls: Record<SalaryBand['tension'], string> = {
  alta: 'text-crit font-bold',
  media: 'text-warn font-semibold',
  estable: 'text-ink-2',
}

// Rango global del gráfico: 25k–95k
const MIN = 25000
const MAX = 95000
const pct = (v: number) => ((v - MIN) / (MAX - MIN)) * 100

export default function Salarios() {
  const [bands, setBands] = useState<SalaryBand[]>([])

  useEffect(() => {
    getSalaryBands().then(setBands)
  }, [])

  return (
    <div>
      <PageHeader
        kicker={`${market.name} · ${market.role} · bandas 2026`}
        title="Señal salarial"
        sub="Bandas de mercado compiladas de las guías salariales España 2026 (Hays, Michael Page, Manfred). Sube tus bandas internas para ver cada equipo pintado frente a mercado: verde en banda, rojo en zona de fuga."
      />

      <Card className="p-6">
        <div className="space-y-5">
          {bands.map((b) => (
            <div key={b.level}>
              <div className="mb-1.5 flex items-baseline justify-between gap-4">
                <b className="text-sm font-bold">{b.level}</b>
                <span className="font-mono text-[13px] tabular-nums text-ink-2">
                  {fmt(b.min)} – {fmt(b.max)}
                </span>
              </div>
              <div className="relative h-3 rounded-full border border-line bg-paper">
                <div
                  className="absolute inset-y-0 rounded-full bg-seq-250"
                  style={{ left: `${pct(b.min)}%`, width: `${pct(b.max) - pct(b.min)}%` }}
                />
              </div>
              <p className="mt-1.5 text-[12.5px] text-ink-2">
                <span className={`font-mono text-[11px] uppercase tracking-wider ${tensionCls[b.tension]}`}>
                  tensión {b.tension}
                </span>
                {' · '}
                {b.note}
              </p>
            </div>
          ))}
        </div>
        <div className="mt-5 flex justify-between border-t border-line pt-3 font-mono text-[11px] text-mut">
          <span>{fmt(MIN)}</span>
          <span>{fmt((MIN + MAX) / 2)}</span>
          <span>{fmt(MAX)}</span>
        </div>
      </Card>

      <Card className="mt-4 border-dashed p-5">
        <b className="text-sm font-bold">Compara tus bandas internas</b>
        <p className="mt-1 max-w-2xl text-[13px] text-ink-2">
          En el plan Growth, sube un CSV con tus bandas (o conecta tu HRIS) y esta pantalla
          muestra la desviación exacta de cada equipo frente a mercado — el dato que decide
          renovaciones antes de que lleguen las renuncias. Tus datos nunca salen de tu cuenta.
        </p>
        <button className="mt-3 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-paper opacity-60" disabled>
          Subir bandas internas (plan Growth)
        </button>
      </Card>
    </div>
  )
}
