-- ============================================================
-- Optional Supabase scheduler setup for telemetry retention
-- Requires pg_cron to be enabled in your Supabase project.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Remove the previous job if it already exists.
SELECT cron.unschedule(jobid)
FROM cron.job
WHERE jobname = 'telemetry_archive_daily';

-- Run every day at 02:15 UTC.
SELECT cron.schedule(
  'telemetry_archive_daily',
  '15 2 * * *',
  $$SELECT public.archive_ended_trip_logs(30, 100, FALSE);$$
);
