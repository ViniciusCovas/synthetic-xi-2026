-- Esquema TalentRadar para Supabase
-- Ejecutar en el SQL Editor de Supabase (o via `supabase db push`).
-- Los nombres de columna coinciden con los tipos de src/data/seed.ts,
-- de modo que la capa de datos (src/lib/data.ts) lee las tablas tal cual.

create table if not exists companies (
  id text primary key,
  name text not null,
  sector text not null,
  score int not null check (score between 0 and 100),
  delta int not null default 0,
  openings int not null default 0,
  "lastPosting" date,
  "financialSignal" boolean not null default false,
  why text not null default '',
  updated_at timestamptz not null default now()
);

create table if not exists alerts (
  id text primary key,
  severity text not null check (severity in ('alta', 'media', 'oportunidad')),
  title text not null,
  body text not null,
  action text not null,
  date date not null default current_date
);

create table if not exists salary_bands (
  level text primary key,
  min int not null,
  max int not null,
  tension text not null check (tension in ('alta', 'media', 'estable')),
  note text not null default ''
);

create table if not exists skills_demand (
  skill text primary key,
  count int not null,
  trend int not null default 0,
  companies text[] not null default '{}'
);

create table if not exists legislation (
  id text primary key,
  scope text not null,
  title text not null,
  status text not null check (status in ('vigente', 'transpuesta', 'en tramitación', 'plazo abierto')),
  deadline text not null,
  impact text not null,
  affects text not null,
  source text not null,
  "sourceUrl" text not null
);

create table if not exists trend_series (
  week text primary key,
  postings int not null
);

-- Lectura pública anónima (la app usa la anon key); escritura solo service_role.
-- Cuando haya clientes con login, cambiar a políticas por organización.
alter table companies enable row level security;
alter table alerts enable row level security;
alter table salary_bands enable row level security;
alter table skills_demand enable row level security;
alter table legislation enable row level security;
alter table trend_series enable row level security;

create policy "lectura publica" on companies for select using (true);
create policy "lectura publica" on alerts for select using (true);
create policy "lectura publica" on salary_bands for select using (true);
create policy "lectura publica" on skills_demand for select using (true);
create policy "lectura publica" on legislation for select using (true);
create policy "lectura publica" on trend_series for select using (true);
