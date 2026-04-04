-- ============================================================
-- THESIS: Archive retention + trip summaries migration
-- Run after the base schema to add long-term telemetry retention.
-- ============================================================

CREATE TABLE IF NOT EXISTS archived_telemetry_logs (
  id              UUID PRIMARY KEY,
  truck_id        UUID REFERENCES trucks(id) ON DELETE SET NULL,
  driver_id       UUID REFERENCES users(id)  ON DELETE SET NULL,
  trip_id         UUID REFERENCES trip_sessions(id) ON DELETE SET NULL,
  trip_status     TEXT DEFAULT 'ended',
  timestamp       TIMESTAMPTZ NOT NULL,
  fuel_level      DOUBLE PRECISION,
  lat             DOUBLE PRECISION,
  lon             DOUBLE PRECISION,
  speed           DOUBLE PRECISION,
  odometer_km     DOUBLE PRECISION,
  engine_status   TEXT,
  anomaly_flag    BOOLEAN DEFAULT FALSE,
  anomaly_score   DOUBLE PRECISION,
  model_source    TEXT,
  truck_code      TEXT,
  driver_name     TEXT,
  archive_reason  TEXT,
  archived_at     TIMESTAMPTZ DEFAULT NOW(),
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trip_summaries (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  trip_id                UUID UNIQUE NOT NULL REFERENCES trip_sessions(id) ON DELETE CASCADE,
  truck_id               UUID REFERENCES trucks(id) ON DELETE SET NULL,
  driver_id              UUID REFERENCES users(id)  ON DELETE SET NULL,
  trip_status            TEXT NOT NULL DEFAULT 'ended',
  start_time             TIMESTAMPTZ NOT NULL,
  end_time               TIMESTAMPTZ,
  total_distance_km      DOUBLE PRECISION DEFAULT 0,
  total_operating_hours  DOUBLE PRECISION DEFAULT 0,
  total_alerts           INTEGER DEFAULT 0,
  total_anomalies        INTEGER DEFAULT 0,
  average_fuel_level     DOUBLE PRECISION,
  start_fuel_level       DOUBLE PRECISION,
  final_fuel_level       DOUBLE PRECISION,
  log_count              INTEGER DEFAULT 0,
  truck_code             TEXT,
  plate_number           TEXT,
  driver_name            TEXT,
  created_at             TIMESTAMPTZ DEFAULT NOW(),
  updated_at             TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_archived_telemetry_trip       ON archived_telemetry_logs (trip_id);
CREATE INDEX IF NOT EXISTS idx_archived_telemetry_time       ON archived_telemetry_logs (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_archived_telemetry_truck_time ON archived_telemetry_logs (truck_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trips_end_time                ON trip_sessions (end_time);
CREATE INDEX IF NOT EXISTS idx_trip_summaries_time           ON trip_summaries (end_time DESC, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_trip_summaries_truck          ON trip_summaries (truck_id, end_time DESC);

CREATE OR REPLACE FUNCTION public.refresh_trip_summary(p_trip_id UUID)
RETURNS trip_summaries
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_summary trip_summaries;
BEGIN
  INSERT INTO trip_summaries (
    trip_id,
    truck_id,
    driver_id,
    trip_status,
    start_time,
    end_time,
    total_distance_km,
    total_operating_hours,
    total_alerts,
    total_anomalies,
    average_fuel_level,
    start_fuel_level,
    final_fuel_level,
    log_count,
    truck_code,
    plate_number,
    driver_name,
    updated_at
  )
  SELECT
    trip.id,
    trip.truck_id,
    trip.driver_id,
    trip.trip_status,
    trip.start_time,
    trip.end_time,
    COALESCE(trip.distance_km, 0),
    COALESCE(trip.operating_hours, 0),
    COALESCE(alert_stats.total_alerts, 0),
    COALESCE(log_stats.total_anomalies, 0),
    log_stats.average_fuel_level,
    log_stats.start_fuel_level,
    log_stats.final_fuel_level,
    COALESCE(log_stats.log_count, 0),
    truck.truck_code,
    truck.plate_number,
    driver.full_name,
    NOW()
  FROM trip_sessions trip
  LEFT JOIN trucks truck ON truck.id = trip.truck_id
  LEFT JOIN users driver ON driver.id = trip.driver_id
  LEFT JOIN LATERAL (
    SELECT COUNT(*) AS total_alerts
    FROM alerts
    WHERE trip_id = trip.id
  ) alert_stats ON TRUE
  LEFT JOIN LATERAL (
    SELECT
      COUNT(*) AS log_count,
      COUNT(*) FILTER (WHERE anomaly_flag IS TRUE) AS total_anomalies,
      ROUND(AVG(fuel_level)::numeric, 2)::double precision AS average_fuel_level,
      (ARRAY_AGG(fuel_level ORDER BY timestamp ASC) FILTER (WHERE fuel_level IS NOT NULL))[1] AS start_fuel_level,
      (ARRAY_AGG(fuel_level ORDER BY timestamp DESC) FILTER (WHERE fuel_level IS NOT NULL))[1] AS final_fuel_level
    FROM (
      SELECT timestamp, fuel_level, anomaly_flag
      FROM telemetry_logs
      WHERE trip_id = trip.id
      UNION ALL
      SELECT timestamp, fuel_level, anomaly_flag
      FROM archived_telemetry_logs
      WHERE trip_id = trip.id
    ) all_logs
  ) log_stats ON TRUE
  WHERE trip.id = p_trip_id
  ON CONFLICT (trip_id) DO UPDATE SET
    truck_id = EXCLUDED.truck_id,
    driver_id = EXCLUDED.driver_id,
    trip_status = EXCLUDED.trip_status,
    start_time = EXCLUDED.start_time,
    end_time = EXCLUDED.end_time,
    total_distance_km = EXCLUDED.total_distance_km,
    total_operating_hours = EXCLUDED.total_operating_hours,
    total_alerts = EXCLUDED.total_alerts,
    total_anomalies = EXCLUDED.total_anomalies,
    average_fuel_level = EXCLUDED.average_fuel_level,
    start_fuel_level = EXCLUDED.start_fuel_level,
    final_fuel_level = EXCLUDED.final_fuel_level,
    log_count = EXCLUDED.log_count,
    truck_code = EXCLUDED.truck_code,
    plate_number = EXCLUDED.plate_number,
    driver_name = EXCLUDED.driver_name,
    updated_at = NOW()
  RETURNING * INTO v_summary;

  RETURN v_summary;
END;
$$;

CREATE OR REPLACE FUNCTION public.archive_ended_trip_logs(
  p_retention_days INTEGER DEFAULT 30,
  p_max_trips INTEGER DEFAULT 50,
  p_dry_run BOOLEAN DEFAULT FALSE
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_cutoff TIMESTAMPTZ := NOW() - MAKE_INTERVAL(days => GREATEST(COALESCE(p_retention_days, 30), 0));
  v_trip RECORD;
  v_trip_logs INTEGER;
  v_archived_trips INTEGER := 0;
  v_archived_logs INTEGER := 0;
  v_summaries_upserted INTEGER := 0;
  v_trips_considered INTEGER := 0;
BEGIN
  FOR v_trip IN
    SELECT trip.id
    FROM trip_sessions trip
    WHERE trip.trip_status = 'ended'
      AND trip.end_time IS NOT NULL
      AND trip.end_time <= v_cutoff
      AND EXISTS (
        SELECT 1
        FROM telemetry_logs live_logs
        WHERE live_logs.trip_id = trip.id
      )
    ORDER BY trip.end_time ASC
    LIMIT GREATEST(COALESCE(p_max_trips, 50), 1)
  LOOP
    v_trips_considered := v_trips_considered + 1;

    PERFORM refresh_trip_summary(v_trip.id);
    v_summaries_upserted := v_summaries_upserted + 1;

    SELECT COUNT(*)
    INTO v_trip_logs
    FROM telemetry_logs
    WHERE trip_id = v_trip.id;

    IF v_trip_logs > 0 THEN
      v_archived_trips := v_archived_trips + 1;
      v_archived_logs := v_archived_logs + v_trip_logs;
    END IF;

    IF NOT p_dry_run AND v_trip_logs > 0 THEN
      INSERT INTO archived_telemetry_logs (
        id,
        truck_id,
        driver_id,
        trip_id,
        trip_status,
        timestamp,
        fuel_level,
        lat,
        lon,
        speed,
        odometer_km,
        engine_status,
        anomaly_flag,
        anomaly_score,
        model_source,
        truck_code,
        driver_name,
        archive_reason,
        archived_at,
        created_at
      )
      SELECT
        live_logs.id,
        live_logs.truck_id,
        live_logs.driver_id,
        live_logs.trip_id,
        'ended',
        live_logs.timestamp,
        live_logs.fuel_level,
        live_logs.lat,
        live_logs.lon,
        live_logs.speed,
        live_logs.odometer_km,
        live_logs.engine_status,
        live_logs.anomaly_flag,
        live_logs.anomaly_score,
        live_logs.model_source,
        truck.truck_code,
        driver.full_name,
        FORMAT('retention_%sd', GREATEST(COALESCE(p_retention_days, 30), 0)),
        NOW(),
        live_logs.created_at
      FROM telemetry_logs live_logs
      LEFT JOIN trucks truck ON truck.id = live_logs.truck_id
      LEFT JOIN users driver ON driver.id = live_logs.driver_id
      WHERE live_logs.trip_id = v_trip.id
      ON CONFLICT (id) DO UPDATE SET
        truck_id = EXCLUDED.truck_id,
        driver_id = EXCLUDED.driver_id,
        trip_id = EXCLUDED.trip_id,
        trip_status = EXCLUDED.trip_status,
        timestamp = EXCLUDED.timestamp,
        fuel_level = EXCLUDED.fuel_level,
        lat = EXCLUDED.lat,
        lon = EXCLUDED.lon,
        speed = EXCLUDED.speed,
        odometer_km = EXCLUDED.odometer_km,
        engine_status = EXCLUDED.engine_status,
        anomaly_flag = EXCLUDED.anomaly_flag,
        anomaly_score = EXCLUDED.anomaly_score,
        model_source = EXCLUDED.model_source,
        truck_code = EXCLUDED.truck_code,
        driver_name = EXCLUDED.driver_name,
        archive_reason = EXCLUDED.archive_reason,
        archived_at = EXCLUDED.archived_at,
        created_at = EXCLUDED.created_at;

      DELETE FROM telemetry_logs
      WHERE trip_id = v_trip.id;
    END IF;
  END LOOP;

  RETURN JSONB_BUILD_OBJECT(
    'retention_days', GREATEST(COALESCE(p_retention_days, 30), 0),
    'cutoff', v_cutoff,
    'dry_run', p_dry_run,
    'archived_trips', v_archived_trips,
    'archived_logs', v_archived_logs,
    'summaries_upserted', v_summaries_upserted,
    'trips_considered', v_trips_considered
  );
END;
$$;
