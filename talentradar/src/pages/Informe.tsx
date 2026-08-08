import { market } from '../lib/data'
import { Card, PageHeader } from '../components/ui'

export default function Informe() {
  return (
    <div>
      <PageHeader
        kicker={`Edición Nº 001 · Semana 32 · ${market.updated}`}
        title="Informe semanal"
        sub="Cada lunes a las 8:00, la síntesis ejecutiva de todos los módulos en dos páginas: lo que pasó, lo que viene, y las tres acciones de la semana."
      />

      <Card className="p-6">
        <div className="border-b-2 border-ink pb-4">
          <span className="font-mono text-[11px] font-bold uppercase tracking-[0.12em] text-brand">
            ● TalentRadar · Radar de Talento
          </span>
          <h2 className="mt-2 text-xl font-extrabold tracking-tight">
            En 60 segundos — {market.name}, {market.role}
          </h2>
        </div>

        <div className="mt-4 space-y-3">
          <div className="rounded-lg border-l-4 border-crit bg-paper p-4">
            <span className="font-mono text-[10.5px] font-bold uppercase tracking-wider text-crit">Presión al alza</span>
            <p className="mt-1 text-sm leading-relaxed text-ink-2">
              <b className="text-ink">Affirm</b> (+38,8% de ingresos, primer año rentable) publicó su segunda vacante
              de ingeniería en Madrid hace 3 días. Presión directa sobre tu retención senior.
            </p>
          </div>
          <div className="rounded-lg border-l-4 border-warn bg-paper p-4">
            <span className="font-mono text-[10.5px] font-bold uppercase tracking-wider text-[#a06f00]">Vigilar</span>
            <p className="mt-1 text-sm leading-relaxed text-ink-2">
              El teletrabajo 100% vuelve como arma salarial encubierta: tu gente puede cambiar de
              empleador sin cambiar de sofá.
            </p>
          </div>
          <div className="rounded-lg border-l-4 border-brand bg-paper p-4">
            <span className="font-mono text-[10.5px] font-bold uppercase tracking-wider text-brand-dark">Oportunidad</span>
            <p className="mt-1 text-sm leading-relaxed text-ink-2">
              Anuncios envejecidos en Tres Cantos: candidatos senior de sistemas críticos,
              frustrados y abordables.
            </p>
          </div>
        </div>

        <p className="mt-5 border-t border-line pt-4 text-xs text-mut">
          El informe completo incluye el radar de presión, la señal salarial y las tres acciones
          recomendadas — generado automáticamente desde los datos de la semana y revisado antes del envío.
          Este es el formato exacto que reciben los clientes piloto por email.
        </p>
      </Card>

      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <Card className="p-5">
          <div className="font-mono text-[11px] font-bold uppercase tracking-wider text-mut">Radar</div>
          <div className="mt-1 text-2xl font-extrabold">€390<span className="text-sm font-semibold text-ink-2">/mes</span></div>
          <p className="mt-1 text-[12.5px] text-ink-2">1 mercado · 3 funciones · 10 competidores · informe semanal</p>
        </Card>
        <Card className="border-brand p-5 ring-1 ring-brand">
          <div className="font-mono text-[11px] font-bold uppercase tracking-wider text-brand">Growth</div>
          <div className="mt-1 text-2xl font-extrabold">€1.900<span className="text-sm font-semibold text-ink-2">/mes</span></div>
          <p className="mt-1 text-[12.5px] text-ink-2">Multi-mercado · competidores ilimitados · bandas internas vs. mercado</p>
        </Card>
        <Card className="p-5">
          <div className="font-mono text-[11px] font-bold uppercase tracking-wider text-mut">Enterprise</div>
          <div className="mt-1 text-2xl font-extrabold">€4<span className="text-sm font-semibold text-ink-2">/empleado/mes</span></div>
          <p className="mt-1 text-[12.5px] text-ink-2">HRIS conectado · riesgo de fuga por equipo · módulo pay gap UE</p>
        </Card>
      </div>
    </div>
  )
}
