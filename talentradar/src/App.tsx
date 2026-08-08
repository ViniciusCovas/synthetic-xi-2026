import { useState } from 'react'
import Radar from './pages/Radar'
import Tendencias from './pages/Tendencias'
import Salarios from './pages/Salarios'
import Competencia from './pages/Competencia'
import Legislacion from './pages/Legislacion'
import Informe from './pages/Informe'
import { isLiveMode } from './lib/supabase'
import { market } from './lib/data'

type PageId = 'radar' | 'tendencias' | 'salarios' | 'competencia' | 'legislacion' | 'informe'

interface NavItem {
  id: PageId
  label: string
  component: () => JSX.Element | null
}

const nav: { section: string; items: NavItem[] }[] = [
  {
    section: 'Mercado',
    items: [
      { id: 'radar', label: 'Radar', component: Radar },
      { id: 'tendencias', label: 'Tendencias', component: Tendencias },
      { id: 'salarios', label: 'Salarios', component: Salarios },
      { id: 'competencia', label: 'Competencia', component: Competencia },
    ],
  },
  {
    section: 'Entorno',
    items: [{ id: 'legislacion', label: 'Legislación', component: Legislacion }],
  },
  {
    section: 'Entrega',
    items: [{ id: 'informe', label: 'Informe semanal', component: Informe }],
  },
]

const allItems = nav.flatMap((s) => s.items)

export default function App() {
  const [active, setActive] = useState<PageId>('radar')
  const Page = allItems.find((p) => p.id === active)!.component

  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-10 hidden w-[220px] flex-col border-r border-line bg-paper/80 backdrop-blur md:flex">
        <div className="flex items-center gap-2.5 px-5 pb-5 pt-6">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand opacity-40 motion-reduce:hidden" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-brand" />
          </span>
          <span className="font-mono text-[12.5px] font-semibold uppercase tracking-[0.18em] text-ink">
            TalentRadar
          </span>
        </div>

        <nav className="flex-1 space-y-6 px-3 pt-2">
          {nav.map((group) => (
            <div key={group.section}>
              <div className="px-3 pb-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-mut">
                {group.section}
              </div>
              <div className="space-y-px">
                {group.items.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => setActive(p.id)}
                    className={`group relative flex w-full items-center rounded-md px-3 py-[7px] text-left text-[13.5px] transition-colors ${
                      active === p.id
                        ? 'bg-raise font-semibold text-ink'
                        : 'font-medium text-ink-2 hover:bg-raise/60 hover:text-ink'
                    }`}
                  >
                    <span
                      className={`absolute left-0 h-4 w-[2px] rounded-full transition-opacity ${
                        active === p.id ? 'bg-brand opacity-100' : 'opacity-0'
                      }`}
                    />
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="border-t border-line px-5 py-4">
          <div className="flex items-center gap-2">
            <span className={`h-1.5 w-1.5 rounded-full ${isLiveMode ? 'bg-ok' : 'bg-warn'}`} />
            <span className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-ink-2">
              {isLiveMode ? 'Supabase · live' : 'Modo demo'}
            </span>
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-mut">
            Indeed · guías 2026 · EDGAR · BOE/EUR-Lex
          </p>
        </div>
      </aside>

      <div className="min-w-0 flex-1 md:pl-[220px]">
        <header className="sticky top-0 z-10 border-b border-line bg-paper/80 backdrop-blur">
          <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-6 py-3 lg:px-10">
            <div className="flex items-baseline gap-3">
              <span className="text-[13.5px] font-semibold">{market.name}</span>
              <span className="text-mut">·</span>
              <span className="text-[13.5px] text-ink-2">{market.role}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="hidden font-mono text-[11px] text-mut sm:block">
                actualizado {market.updated}
              </span>
              <span className="rounded-full border border-brand/40 bg-brand-soft px-2.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-brand-dark">
                beta privada
              </span>
            </div>
          </div>
        </header>

        <main className="px-6 py-8 lg:px-10">
          <div className="mx-auto max-w-5xl">
            <Page />
          </div>
        </main>
      </div>
    </div>
  )
}
