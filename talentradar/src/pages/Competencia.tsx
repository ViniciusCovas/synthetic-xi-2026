import { useEffect, useState } from 'react'
import { getSkillsDemand, market } from '../lib/data'
import type { SkillDemand } from '../data/seed'
import { Card, PageHeader } from '../components/ui'

export default function Competencia() {
  const [skills, setSkills] = useState<SkillDemand[]>([])

  useEffect(() => {
    getSkillsDemand().then(setSkills)
  }, [])

  const max = skills.length ? Math.max(...skills.map((s) => s.count)) : 1

  return (
    <div>
      <PageHeader
        kicker={`${market.name} · ${market.role}`}
        title="Qué pide la competencia"
        sub="Skills extraídas de las vacantes vivas de tu mercado, ordenadas por frecuencia. Es el espejo de lo que aparecerá en los CVs dentro de 6 meses — y tu guía de upskilling y de redacción de ofertas."
      />

      <Card className="p-6">
        <div className="space-y-4">
          {skills.map((s) => (
            <div key={s.skill} className="grid grid-cols-[minmax(130px,200px)_1fr_auto] items-center gap-4">
              <div>
                <b className="block text-sm font-bold">{s.skill}</b>
                <span className="text-[11.5px] text-mut">{s.companies.join(' · ')}</span>
              </div>
              <div className="relative h-2.5 rounded-full border border-line bg-paper">
                <div
                  className="absolute inset-y-0 left-0 rounded-full bg-seq-400"
                  style={{ width: `${(s.count / max) * 100}%` }}
                />
              </div>
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-base font-bold tabular-nums">{s.count}</span>
                <span className={`font-mono text-[11px] font-bold ${s.trend > 0 ? 'text-crit' : s.trend < 0 ? 'text-ok' : 'text-mut'}`}>
                  {s.trend > 0 ? `▲${s.trend}` : s.trend < 0 ? `▼${Math.abs(s.trend)}` : '='}
                </span>
              </div>
            </div>
          ))}
        </div>
        <p className="mt-5 border-t border-line pt-3 text-xs text-mut">
          ▲ = menciones en subida vs. las 4 semanas anteriores. La subida de una skill anticipa
          su encarecimiento: cloud e inglés C1 son hoy las señales más calientes de este mercado.
        </p>
      </Card>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Card className="p-5">
          <b className="text-sm font-bold">Para atraer</b>
          <p className="mt-1 text-[13px] leading-relaxed text-ink-2">
            Tus ofertas compiten contra estas keywords. Si tu anuncio de backend no menciona
            cloud ni teletrabajo, está perdiendo contra el 70% del mercado antes de la primera entrevista.
          </p>
        </Card>
        <Card className="p-5">
          <b className="text-sm font-bold">Para retener</b>
          <p className="mt-1 text-[13px] leading-relaxed text-ink-2">
            Las skills en subida son las que te van a intentar comprar fuera. Plan de upskilling
            interno en cloud = retención más barata que contraofertar en caliente.
          </p>
        </Card>
      </div>
    </div>
  )
}
