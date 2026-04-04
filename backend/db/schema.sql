-- ============================================================
-- THESIS: Fleet Monitoring System — Supabase SQL Schema
-- Run this entire script in the Supabase SQL Editor
-- (Database → SQL Editor → New Query → Paste → Run)
-- ============================================================

-- ── 1. USERS ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  full_name        TEXT NOT NULL,
  email            TEXT UNIQUE NOT NULL,
  password_hash    TEXT NOT NULL,
  role             TEXT NOT NULL CHECK (role IN ('admin', 'driver')),
  assigned_truck_id UUID,               -- FK added after trucks table exists
  is_active        BOOLEAN DEFAULT TRUE,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── 2. TRUCKS ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trucks (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  truck_code       TEXT UNIQUE NOT NULL,   -- e.g. TRK-001
  plate_number     TEXT UNIQUE NOT NULL,
  model            TEXT,
  status           TEXT DEFAULT 'idle'
                   CHECK (status IN ('active','idle','maintenance','anomaly','rest_alert','low_fuel','offline')),
  device_installed BOOLEAN DEFAULT FALSE,
  notes            TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Add FK from users → trucks (after both tables exist)
ALTER TABLE users
  ADD CONSTRAINT fk_users_truck
  FOREIGN KEY (assigned_truck_id) REFERENCES trucks(id)
  ON DELETE SET NULL;

-- ── 3. TRIP SESSIONS ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trip_sessions (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  truck_id         UUID NOT NULL REFERENCES trucks(id) ON DELETE CASCADE,
  driver_id        UUID NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
  start_time       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  end_time         TIMESTAMPTZ,
  trip_status      TEXT DEFAULT 'active'
                   CHECK (trip_status IN ('active','ended','paused')),
  start_lat        DOUBLE PRECISION,
  start_lon        DOUBLE PRECISION,
  end_lat          DOUBLE PRECISION,
  end_lon          DOUBLE PRECISION,
  distance_km      DOUBLE PRECISION DEFAULT 0,
  operating_hours  DOUBLE PRECISION DEFAULT 0,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── 4. TELEMETRY LOGS ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS telemetry_logs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  truck_id        UUID NOT NULL REFERENCES trucks(id) ON DELETE CASCADE,
  driver_id       UUID          REFERENCES users(id)  ON DELETE SET NULL,
  trip_id         UUID          REFERENCES trip_sessions(id) ON DELETE SET NULL,
  timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  fuel_level      DOUBLE PRECISION,          -- % (ECU-derived)
  lat             DOUBLE PRECISION,
  lon             DOUBLE PRECISION,
  speed           DOUBLE PRECISION,          -- km/h
  odometer_km     DOUBLE PRECISION,
  engine_status   TEXT DEFAULT 'on'
                  CHECK (engine_status IN ('on','off','idle')),
  anomaly_flag    BOOLEAN DEFAULT FALSE,
  anomaly_score   DOUBLE PRECISION,
  model_source    TEXT,                      -- 'isolation_forest' | 'matrix_profile' | 'combined'
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── 5. ALERTS ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alerts (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  truck_id    UUID NOT NULL REFERENCES trucks(id) ON DELETE CASCADE,
  driver_id   UUID          REFERENCES users(id)  ON DELETE SET NULL,
  trip_id     UUID          REFERENCES trip_sessions(id) ON DELETE SET NULL,
  timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  alert_type  TEXT NOT NULL,   -- 'fuel_anomaly' | 'overspeed' | 'rest_alert' | 'maintenance' | 'low_fuel'
  message     TEXT NOT NULL,
  severity    TEXT NOT NULL CHECK (severity IN ('low','medium','high')),
  is_resolved BOOLEAN DEFAULT FALSE,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── 6. LATENCY LOGS (SO2-c — transmission latency tracking) ──
CREATE TABLE IF NOT EXISTS latency_logs (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  truck_id    UUID REFERENCES trucks(id) ON DELETE SET NULL,
  sent_at     TIMESTAMPTZ,
  received_at TIMESTAMPTZ,
  latency_ms  INTEGER,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── INDEXES for common query patterns ────────────────────────
CREATE INDEX IF NOT EXISTS idx_telemetry_truck_time  ON telemetry_logs (truck_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_trip        ON telemetry_logs (trip_id);
CREATE INDEX IF NOT EXISTS idx_alerts_truck          ON alerts (truck_id, is_resolved);
CREATE INDEX IF NOT EXISTS idx_trips_truck_status    ON trip_sessions (truck_id, trip_status);
CREATE INDEX IF NOT EXISTS idx_latency_received      ON latency_logs (received_at DESC);
