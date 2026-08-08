import { useState } from 'react'
import Radar from './pages/Radar'
import Tendencias from './pages/Tendencias'
import Salarios from './pages/Salarios'
import Competencia from './pages/Competencia'
import Legislacion from './pages/Legislacion'
import Informe from './pages/Informe'
import { isLiveMode } from './lib/supabase'

const pages = [
  { id: 'radar', label: 'Radar', icon: '◉', component: Radar },
  { id: 'tendencias', label: 'Tendencias', icon: '▲', component: Tendencias },
  { id: 'salarios', label: 'Salarios', icon: '€', component: Salarios },
  { id: 'competencia', label: 'Competencia', icon: '⚔', component: Competencia },
  { id: 'legislacion', label: 'Legislación', icon: '§', component: Legislacion },
  { id: 'informe', label: 'Informe semanal', icon: '✉', component: Informe },
] as const

type PageId = (typeof pages)[number]['id']

export default function App() {
  const [active, setActive] = useState<PageId>('radar')
  const Page = pages.find((p) => p.id === active)!.component

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 shrink-0 flex-col border-r border-line bg-card">
        <div className="flex items-center gap-2.5 border-b border-line px-5 py-5">
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand opacity-40 motion-reduce:hidden" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-brand" />
          </span>
          <span className="font-mono text-[13px] font-bold uppercase tracking-[0.14em] text-brand">
            TalentRadar
          </span>
        </div>
        <nav className="flex-1 space-y-0.5 p-3">
          {pages.map((p) => (
            <button
              key={p.id}
              onClick={() => setActive(p.id)}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                active === p.id
                  ? 'bg-brand-soft font-bold text-brand-dark'
                  : 'font-medium text-ink-2 hover:bg-paper'
              }`}
            >
              <span className="w-4 text-center font-mono text-xs" aria-hidden>{p.icon}</span>
              {p.label}
            </button>
          ))}
        </nav>
        <div className="border-t border-line px-5 py-4">
          <span
            className={`rounded px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider ${
              isLiveMode ? 'bg-brand-soft text-brand-dark' : 'bg-warn/15 text-[#a06f00]'
            }`}
          >
            {isLiveMode ? 'Supabase conectado' : 'Modo demo'}
          </span>
          <p className="mt-2 text-[11px] leading-relaxed text-mut">
            Datos: Indeed, guías salariales 2026, resultados fiscales públicos, BOE/EUR-Lex.
          </p>
        </div>
      </aside>

      <main className="min-w-0 flex-1 px-6 py-8 lg:px-10">
        <div className="mx-auto max-w-5xl">
          <Page />
        </div>
      </main>
    </div>
  )
}
