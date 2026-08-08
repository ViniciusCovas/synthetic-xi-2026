import { supabase } from './supabase'
import * as seed from '../data/seed'
import type {
  Alert,
  Company,
  LegislationItem,
  SalaryBand,
  SkillDemand,
  TrendPoint,
} from '../data/seed'

// Capa de datos única: cada página pide aquí, sin saber si detrás hay
// Supabase o los datos de arranque. Cuando Supabase esté configurado,
// cualquier tabla vacía cae de vuelta al arranque para no romper la demo.

async function fromTable<T>(table: string, fallback: T[], orderBy?: { column: string; ascending: boolean }): Promise<T[]> {
  if (!supabase) return fallback
  let query = supabase.from(table).select('*')
  if (orderBy) query = query.order(orderBy.column, { ascending: orderBy.ascending })
  const { data, error } = await query
  if (error || !data || data.length === 0) return fallback
  return data as T[]
}

export const getCompanies = () =>
  fromTable<Company>('companies', seed.companies, { column: 'score', ascending: false })

export const getAlerts = () =>
  fromTable<Alert>('alerts', seed.alerts, { column: 'date', ascending: false })

export const getSalaryBands = () => fromTable<SalaryBand>('salary_bands', seed.salaryBands)

export const getSkillsDemand = () =>
  fromTable<SkillDemand>('skills_demand', seed.skillsDemand, { column: 'count', ascending: false })

export const getLegislation = () => fromTable<LegislationItem>('legislation', seed.legislation)

export const getTrendSeries = () => fromTable<TrendPoint>('trend_series', seed.trendSeries)

export const market = seed.market
