// Datos de arranque de TalentRadar.
// Origen: extracción real del 8 de agosto de 2026 (vacantes Indeed Madrid,
// resultados fiscales FY2025 publicados, guías salariales España 2026).
// Las series semanales marcadas como "demo" son ilustrativas hasta que el
// pipeline de ingesta acumule histórico propio.

export interface Company {
  id: string
  name: string
  sector: string
  score: number
  delta: number
  openings: number
  lastPosting: string
  financialSignal: boolean
  why: string
}

export interface Alert {
  id: string
  severity: 'alta' | 'media' | 'oportunidad'
  title: string
  body: string
  action: string
  date: string
}

export interface SalaryBand {
  level: string
  min: number
  max: number
  tension: 'alta' | 'media' | 'estable'
  note: string
}

export interface SkillDemand {
  skill: string
  count: number
  trend: number
  companies: string[]
}

export interface LegislationItem {
  id: string
  scope: 'UE' | 'España'
  title: string
  status: 'vigente' | 'transpuesta' | 'en tramitación' | 'plazo abierto'
  deadline: string
  impact: string
  affects: string
  source: string
  sourceUrl: string
}

export interface TrendPoint {
  week: string
  postings: number
}

export const market = {
  name: 'Madrid',
  role: 'Ingeniería de software',
  updated: '8 ago 2026',
}

export const companies: Company[] = [
  {
    id: 'affirm',
    name: 'Affirm',
    sector: 'Fintech',
    score: 87,
    delta: +9,
    openings: 2,
    lastPosting: '2026-08-05',
    financialSignal: true,
    why: 'Ingresos FY25 +38,8% ($3.220M), primer ejercicio rentable. Vacante publicada hace 3 días. Señal financiera y de mercado alineadas: contratación agresiva este trimestre.',
  },
  {
    id: 'knowmad',
    name: 'knowmad mood',
    sector: 'Consultoría tech',
    score: 70,
    delta: +6,
    openings: 1,
    lastPosting: '2026-08-05',
    financialSignal: false,
    why: 'Java + inglés, 100% teletrabajo, publicada hace 3 días. El remoto total multiplica su alcance: compite contra todo empleador presencial de Madrid.',
  },
  {
    id: 'siemens',
    name: 'Siemens',
    sector: 'Industrial',
    score: 66,
    delta: 0,
    openings: 2,
    lastPosting: '2026-07-10',
    financialSignal: false,
    why: 'Dos posiciones de nicho (CFD, tracción ferroviaria) activas desde julio en Tres Cantos. Contratación sostenida, no explosiva.',
  },
  {
    id: 'equinix',
    name: 'Equinix',
    sector: 'Data centers',
    score: 63,
    delta: +2,
    openings: 1,
    lastPosting: '2026-07-21',
    financialSignal: false,
    why: 'Staff Software Engineer activa desde el 21 de julio. Posición senior única: caza selectiva de talento, no expansión de plantilla.',
  },
  {
    id: 'accenture',
    name: 'Accenture',
    sector: 'Consultoría',
    score: 61,
    delta: -3,
    openings: 1,
    lastPosting: '2026-05-05',
    financialSignal: true,
    why: 'Ingresos FY25 $69.700M (+7%). Su vacante de microservicios lleva desde mayo: volumen constante, sin aceleración nueva.',
  },
  {
    id: 'gmv',
    name: 'GMV',
    sector: 'Aeroespacial',
    score: 48,
    delta: -4,
    openings: 2,
    lastPosting: '2026-04-30',
    financialSignal: false,
    why: 'Anuncios de febrero y abril sin cerrar. Presión baja — pero procesos lentos generan candidatos senior frustrados y abordables.',
  },
]

export const alerts: Alert[] = [
  {
    id: 'a1',
    severity: 'alta',
    title: 'Fintech americana en expansión recluta ingeniería en Madrid',
    body: 'Affirm (+38,8% ingresos, primer año rentable) publicó su segunda vacante hace 3 días. Las fintech en expansión pagan por encima de banda local.',
    action: 'Revisar la banda de tus seniors de backend esta semana: coste de ajustar vs. coste de reemplazar (50–200% del salario anual).',
    date: '2026-08-08',
  },
  {
    id: 'a2',
    severity: 'media',
    title: 'El teletrabajo 100% vuelve a usarse como arma salarial encubierta',
    body: 'Oferta Java 100% remota activa desde Madrid. Tu gente puede cambiar de empleador sin cambiar de ciudad.',
    action: 'Definir la política de flexibilidad en frío, antes de negociarla en caliente en una renuncia.',
    date: '2026-08-08',
  },
  {
    id: 'a3',
    severity: 'oportunidad',
    title: 'Ventana de captación en el polo aeroespacial de Tres Cantos',
    body: 'Vacantes de ingeniería sin cubrir desde febrero: candidatos senior frustrados y abordables en perfiles de sistemas críticos.',
    action: 'Mensaje directo del hiring manager (no de un recruiter externo) a 3–4 perfiles de la zona.',
    date: '2026-08-07',
  },
]

export const salaryBands: SalaryBand[] = [
  { level: 'Junior (0–2 años)', min: 28000, max: 38000, tension: 'estable', note: 'La demanda se concentra en perfiles con experiencia' },
  { level: 'Mid (2–5 años)', min: 38000, max: 52000, tension: 'media', note: 'El remoto 100% amplía las opciones de salida de este nivel' },
  { level: 'Senior (5+ años)', min: 52000, max: 70000, tension: 'alta', note: 'Los perfiles de datos con experiencia ya rompen los 60.000 € (+10K en dos años)' },
  { level: 'Staff / Lead', min: 70000, max: 90000, tension: 'alta', note: 'El nivel que cazan Equinix y las fintech internacionales, con paquetes fuera de banda local' },
]

export const skillsDemand: SkillDemand[] = [
  { skill: 'Java', count: 14, trend: +3, companies: ['knowmad mood', 'Accenture', 'GMV'] },
  { skill: 'Microservicios', count: 11, trend: +2, companies: ['Accenture', 'Affirm'] },
  { skill: 'Cloud (AWS/Azure)', count: 10, trend: +4, companies: ['Equinix', 'Affirm', 'Accenture'] },
  { skill: 'Fullstack (React/Node)', count: 8, trend: +1, companies: ['Affirm'] },
  { skill: 'Inglés C1', count: 8, trend: +2, companies: ['knowmad mood', 'Affirm', 'Equinix'] },
  { skill: 'Python / datos', count: 7, trend: +3, companies: ['Siemens', 'GMV'] },
  { skill: 'CFD / simulación', count: 2, trend: 0, companies: ['Siemens'] },
  { skill: 'Sistemas críticos / defensa', count: 2, trend: -1, companies: ['GMV'] },
]

export const legislation: LegislationItem[] = [
  {
    id: 'l1',
    scope: 'UE',
    title: 'Directiva (UE) 2023/970 — Transparencia salarial',
    status: 'transpuesta',
    deadline: 'Primer informe de brecha: junio 2027 (empresas 150+)',
    impact: 'Obligación de publicar rangos salariales en ofertas, prohibición de preguntar salario previo, informe de brecha de género. Sanciones por incumplimiento.',
    affects: 'Toda empresa 100+ empleados (calendario escalonado). Presupuesto obligatorio, no discrecional.',
    source: 'EUR-Lex',
    sourceUrl: 'https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX%3A32023L0970',
  },
  {
    id: 'l2',
    scope: 'España',
    title: 'Reducción de jornada a 37,5 horas',
    status: 'en tramitación',
    deadline: 'Tramitación parlamentaria en curso',
    impact: 'Reducción de jornada máxima legal sin reducción salarial. Impacto directo en costes laborales, turnos y planificación de plantilla.',
    affects: 'Todas las empresas. Sectores con turnos y atención continua, los más expuestos.',
    source: 'BOE / Congreso',
    sourceUrl: 'https://www.boe.es',
  },
  {
    id: 'l3',
    scope: 'España',
    title: 'SMI 2026 y registro horario digital reforzado',
    status: 'vigente',
    deadline: 'Aplicación inmediata',
    impact: 'Nueva subida del salario mínimo y endurecimiento del control de jornada con registro digital accesible a la Inspección.',
    affects: 'Bandas salariales de entrada y compliance de jornada en toda la plantilla.',
    source: 'BOE',
    sourceUrl: 'https://www.boe.es',
  },
  {
    id: 'l4',
    scope: 'UE',
    title: 'Ley de IA (AI Act) — obligaciones para RRHH',
    status: 'plazo abierto',
    deadline: 'Sistemas de alto riesgo: agosto 2026–2027',
    impact: 'Los sistemas de IA usados en selección, evaluación y promoción se consideran de alto riesgo: exigen supervisión humana, documentación y auditoría.',
    affects: 'Cualquier empresa que use IA en reclutamiento o evaluación de desempeño.',
    source: 'EUR-Lex',
    sourceUrl: 'https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX%3A32024R1689',
  },
]

// Serie semanal de vacantes nuevas (demo hasta acumular histórico propio)
export const trendSeries: TrendPoint[] = [
  { week: 'S25', postings: 41 },
  { week: 'S26', postings: 44 },
  { week: 'S27', postings: 39 },
  { week: 'S28', postings: 47 },
  { week: 'S29', postings: 52 },
  { week: 'S30', postings: 49 },
  { week: 'S31', postings: 58 },
  { week: 'S32', postings: 63 },
]
