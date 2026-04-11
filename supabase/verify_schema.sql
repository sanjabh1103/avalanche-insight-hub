-- Avalanche Insight Hub schema verification
-- Run in Supabase SQL Editor after applying migrations.

select
  current_database() as database_name,
  current_schema() as current_schema,
  version() as postgres_version;

select extname
from pg_extension
where extname in ('postgis', 'pgcrypto')
order by extname;

select typname
from pg_type
where typnamespace = 'public'::regnamespace
  and typname in ('event_type', 'report_status', 'job_type', 'job_status')
order by typname;

select tablename
from pg_tables
where schemaname = 'public'
  and tablename in (
    'avalanche_events',
    'forecasts',
    'field_reports',
    'compute_jobs',
    'system_config',
    'model_status',
    'mountain_terrain'
  )
order by tablename;

select
  schemaname,
  tablename,
  rowsecurity
from pg_tables
join pg_class on pg_class.relname = tablename
where schemaname = 'public'
  and tablename in (
    'avalanche_events',
    'forecasts',
    'field_reports',
    'compute_jobs',
    'system_config',
    'model_status',
    'mountain_terrain'
  )
order by tablename;

select
  tablename,
  policyname,
  permissive,
  roles,
  cmd,
  qual,
  with_check
from pg_policies
where schemaname = 'public'
  and tablename in (
    'avalanche_events',
    'forecasts',
    'field_reports',
    'compute_jobs',
    'system_config',
    'model_status',
    'mountain_terrain'
  )
order by tablename, policyname;

select *
from public.system_config
limit 5;

select *
from public.model_status
limit 5;
