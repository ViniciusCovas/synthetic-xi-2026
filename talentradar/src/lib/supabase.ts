import { createClient, type SupabaseClient } from '@supabase/supabase-js'

// La app funciona en dos modos:
//  - Sin variables de entorno: modo demo con datos de arranque locales.
//  - Con VITE_SUPABASE_URL y VITE_SUPABASE_ANON_KEY: lee de Supabase
//    (esquema en supabase/schema.sql).
const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

export const supabase: SupabaseClient | null =
  url && anonKey ? createClient(url, anonKey) : null

export const isLiveMode = supabase !== null
