# TalentRadar

Inteligencia predictiva de talento para RRHH: presión de contratación, tendencias de
vacantes, señal salarial, skills demandadas y legislación laboral — en un panel.

Stack: **Vite + React + TypeScript + Tailwind + Supabase** (el mismo que usa Lovable,
para que el código resulte familiar).

## Arrancar en local

```bash
cd talentradar
npm install
npm run dev
```

Sin configurar nada, la app arranca en **modo demo** con los datos de la extracción
real del 8 de agosto de 2026 (Madrid, ingeniería de software).

## Conectar Supabase

1. Crea un proyecto en [supabase.com](https://supabase.com) (plan gratuito sobra para empezar).
2. En el SQL Editor, ejecuta `supabase/schema.sql`.
3. Crea `talentradar/.env`:

```
VITE_SUPABASE_URL=https://TU-PROYECTO.supabase.co
VITE_SUPABASE_ANON_KEY=TU_ANON_KEY
```

4. Reinicia `npm run dev`. La barra lateral pasa de "Modo demo" a "Supabase conectado".
   Cualquier tabla vacía cae de vuelta a los datos demo, así que puedes migrar módulo a módulo.

## Deploy en Cloudflare Pages

1. En el dashboard de Cloudflare: **Workers & Pages → Create → Pages → Connect to Git**
   y elige este repositorio.
2. Configuración de build:
   - Root directory: `talentradar`
   - Build command: `npm run build`
   - Output directory: `dist`
3. Variables de entorno (Settings → Environment variables): las dos `VITE_SUPABASE_*` de arriba.
4. Cada push a la rama desplegada publica automáticamente. Dominio propio gratis en el mismo panel.

## Arquitectura de datos

```
FUENTES ──────► INGESTA ─────► NORMALIZACIÓN ────► SCORE ────► APP / INFORME
vacantes         1×/día         taxonomía ESCO     índice 0-100   este frontend
finanzas         (workers)      (función↔skills)   + anomalías    + email semanal
BOE/EUR-Lex
```

La capa de datos vive en `src/lib/data.ts`: cada página pide ahí y no sabe si detrás
hay Supabase o el seed local. Los workers de ingesta (fase siguiente) escriben en las
mismas tablas del esquema.

### Fuentes por módulo

| Módulo | Gratis (hoy) | De pago (cuando haya ingresos) |
|---|---|---|
| Radar / Tendencias | Adzuna (1.000 calls/mes), portales públicos | TheirStack $49/mes, Coresignal $49–1.500/mes |
| Salarios | Guías 2026 (Hays, Michael Page, Manfred), salarios publicados en vacantes | Figures €2.500/año, Levels.fyi ~$800/mes |
| Competencia (skills) | Taxonomía ESCO (28 idiomas, API abierta) | Lightcast |
| Legislación | BOE API + EUR-Lex API (abiertas) | — |
| Finanzas de empleadores | SEC EDGAR, resultados publicados | Octagon y similares |
| HRIS del cliente (fase 3) | — | Merge.dev $0,50–3/cuenta/mes |

## Índice de presión

`0,4 × recencia de vacantes + 0,3 × crecimiento de ingresos YoY + 0,3 × densidad de vacantes` → 0–100.
Transparente y descomponible: cada score muestra sus señales en la propia UI.
