import { useEffect, useState } from 'react'
import { getLegislation } from '../lib/data'
import type { LegislationItem } from '../data/seed'
import { Badge, Card, PageHeader } from '../components/ui'

export default function Legislacion() {
  const [items, setItems] = useState<LegislationItem[]>([])

  useEffect(() => {
    getLegislation().then(setItems)
  }, [])

  return (
    <div>
      <PageHeader
        kicker="España · Unión Europea"
        title="Legislación y gobierno"
        sub="Todo lo regulatorio que golpea al capital humano, con estado, plazo e impacto operativo. Fuentes oficiales: BOE y EUR-Lex — sin interpretación de terceros."
      />

      <div className="grid gap-3">
        {items.map((l) => (
          <Card key={l.id} className="p-5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-line bg-raise px-2.5 py-[3px] font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-2">
                {l.scope}
              </span>
              <Badge kind={l.status} />
              <span className="font-mono text-[11.5px] text-mut">{l.deadline}</span>
            </div>
            <b className="mt-2 block text-[15px] font-bold leading-snug">{l.title}</b>
            <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-2">{l.impact}</p>
            <p className="mt-2 text-[13px] leading-relaxed">
              <span className="font-bold text-brand">Afecta a: </span>
              <span className="text-ink-2">{l.affects}</span>
            </p>
            <a
              href={l.sourceUrl}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-block font-mono text-[11.5px] font-bold text-brand hover:underline"
            >
              Fuente: {l.source} ↗
            </a>
          </Card>
        ))}
      </div>

      <Card className="mt-4 border-dashed p-5">
        <b className="text-sm font-bold">Cómo se alimenta este módulo</b>
        <p className="mt-1 max-w-3xl text-[13px] leading-relaxed text-ink-2">
          El BOE y EUR-Lex publican APIs abiertas y gratuitas. El pipeline vigila los boletines a diario,
          filtra lo laboral, y la capa de IA lo traduce a impacto operativo ("qué tengo que hacer y para cuándo").
          En el plan Growth se añaden los convenios colectivos de tu sector y alertas por país para expansión internacional.
        </p>
      </Card>
    </div>
  )
}
