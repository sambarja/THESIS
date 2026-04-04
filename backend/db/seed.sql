-- ============================================================
-- THESIS: Fleet Monitoring System — Seed Data
-- Run AFTER schema.sql in Supabase SQL Editor
-- Passwords are bcrypt hashes of "password123" (10 rounds)
-- ============================================================

-- ── 1. TRUCKS (insert first — users FK references trucks) ────
INSERT INTO trucks (id, truck_code, plate_number, model, status, device_installed, notes)
VALUES
  ('11111111-0000-0000-0000-000000000001', 'TRK-001', 'ABC-1234', 'Isuzu Elf NHR 2020', 'active',      TRUE,  'Primary delivery truck — north route'),
  ('11111111-0000-0000-0000-000000000002', 'TRK-002', 'DEF-5678', 'Mitsubishi Fuso 2019', 'idle',        TRUE,  'Secondary unit — south route'),
  ('11111111-0000-0000-0000-000000000003', 'TRK-003', 'GHI-9012', 'Hino 300 Series 2021', 'maintenance', TRUE,  'Scheduled oil change due'),
  ('11111111-0000-0000-0000-000000000004', 'TRK-004', 'JKL-3456', 'Isuzu NLR 2022',       'low_fuel',    TRUE,  'East route unit')
ON CONFLICT (id) DO NOTHING;

-- ── 2. USERS ─────────────────────────────────────────────────
-- password_hash = bcrypt("password123", 10)
-- To generate your own: node -e "const b=require('bcryptjs');b.hash('password123',10).then(console.log)"
INSERT INTO users (id, full_name, email, password_hash, role, assigned_truck_id, is_active)
VALUES
  (
    '22222222-0000-0000-0000-000000000001',
    'Fleet Admin',
    'admin@fleetsgsa.com',
    '$2b$10$YourHashHere.ReplaceWithRealBcryptHashOfPassword123xxxxx',
    'admin',
    NULL,
    TRUE
  ),
  (
    '22222222-0000-0000-0000-000000000002',
    'Juan Dela Cruz',
    'juan@fleetsgsa.com',
    '$2b$10$YourHashHere.ReplaceWithRealBcryptHashOfPassword123xxxxx',
    'driver',
    '11111111-0000-0000-0000-000000000001',
    TRUE
  ),
  (
    '22222222-0000-0000-0000-000000000003',
    'Maria Santos',
    'maria@fleetsgsa.com',
    '$2b$10$YourHashHere.ReplaceWithRealBcryptHashOfPassword123xxxxx',
    'driver',
    '11111111-0000-0000-0000-000000000002',
    TRUE
  ),
  (
    '22222222-0000-0000-0000-000000000004',
    'Roberto Garcia',
    'roberto@fleetsgsa.com',
    '$2b$10$YourHashHere.ReplaceWithRealBcryptHashOfPassword123xxxxx',
    'driver',
    '11111111-0000-0000-0000-000000000003',
    TRUE
  ),
  (
    '22222222-0000-0000-0000-000000000005',
    'Ana Reyes',
    'ana@fleetsgsa.com',
    '$2b$10$YourHashHere.ReplaceWithRealBcryptHashOfPassword123xxxxx',
    'driver',
    '11111111-0000-0000-0000-000000000004',
    TRUE
  )
ON CONFLICT (id) DO NOTHING;

-- ── 3. TRIP SESSIONS ─────────────────────────────────────────
INSERT INTO trip_sessions (id, truck_id, driver_id, start_time, end_time, trip_status,
                           start_lat, start_lon, end_lat, end_lon, distance_km, operating_hours)
VALUES
  -- Active trip: TRK-001 / Juan
  (
    '33333333-0000-0000-0000-000000000001',
    '11111111-0000-0000-0000-000000000001',
    '22222222-0000-0000-0000-000000000002',
    NOW() - INTERVAL '3 hours',
    NULL,
    'active',
    14.5995, 120.9842,
    NULL, NULL,
    87.4, 3.0
  ),
  -- Ended trip: TRK-002 / Maria (yesterday)
  (
    '33333333-0000-0000-0000-000000000002',
    '11111111-0000-0000-0000-000000000002',
    '22222222-0000-0000-0000-000000000003',
    NOW() - INTERVAL '1 day 5 hours',
    NOW() - INTERVAL '1 day 1 hour',
    'ended',
    14.5995, 120.9842,
    14.0800, 121.1800,
    214.6, 4.0
  ),
  -- Ended trip: TRK-004 / Ana (2 days ago)
  (
    '33333333-0000-0000-0000-000000000003',
    '11111111-0000-0000-0000-000000000004',
    '22222222-0000-0000-0000-000000000005',
    NOW() - INTERVAL '2 days 4 hours',
    NOW() - INTERVAL '2 days 30 minutes',
    'ended',
    14.5995, 120.9842,
    14.5300, 121.2000,
    112.3, 3.5
  )
ON CONFLICT (id) DO NOTHING;

-- ── 4. TELEMETRY LOGS (active trip TRK-001 — last 8 readings) ─
INSERT INTO telemetry_logs (truck_id, driver_id, trip_id, timestamp,
                            fuel_level, lat, lon, speed, odometer_km,
                            engine_status, anomaly_flag, anomaly_score, model_source)
VALUES
  ('11111111-0000-0000-0000-000000000001','22222222-0000-0000-0000-000000000002','33333333-0000-0000-0000-000000000001', NOW()-INTERVAL '3 hours',   92.0, 14.5995, 120.9842,  0.0, 45210.0, 'on', FALSE, NULL, NULL),
  ('11111111-0000-0000-0000-000000000001','22222222-0000-0000-0000-000000000002','33333333-0000-0000-0000-000000000001', NOW()-INTERVAL '2.5 hours', 90.2, 14.6200, 120.9750, 72.0, 45246.2, 'on', FALSE, NULL, NULL),
  ('11111111-0000-0000-0000-000000000001','22222222-0000-0000-0000-000000000002','33333333-0000-0000-0000-000000000001', NOW()-INTERVAL '2 hours',   88.5, 14.6500, 120.9650, 68.0, 45282.4, 'on', FALSE, NULL, NULL),
  ('11111111-0000-0000-0000-000000000001','22222222-0000-0000-0000-000000000002','33333333-0000-0000-0000-000000000001', NOW()-INTERVAL '1.5 hours', 86.1, 14.6900, 120.9500, 75.0, 45318.6, 'on', FALSE, NULL, NULL),
  ('11111111-0000-0000-0000-000000000001','22222222-0000-0000-0000-000000000002','33333333-0000-0000-0000-000000000001', NOW()-INTERVAL '1 hour',    83.3, 14.7200, 120.9350, 80.0, 45354.8, 'on', FALSE, NULL, NULL),
  ('11111111-0000-0000-0000-000000000001','22222222-0000-0000-0000-000000000002','33333333-0000-0000-0000-000000000001', NOW()-INTERVAL '45 minutes',79.8, 14.7500, 120.9200, 78.0, 45391.0, 'on', FALSE, NULL, NULL),
  -- Anomaly reading — sudden fuel drop (simulated theft/leak)
  ('11111111-0000-0000-0000-000000000001','22222222-0000-0000-0000-000000000002','33333333-0000-0000-0000-000000000001', NOW()-INTERVAL '30 minutes',64.2, 14.7800, 120.9100,  0.0, 45391.0, 'on', TRUE,  0.87, 'isolation_forest'),
  -- Recovery
  ('11111111-0000-0000-0000-000000000001','22222222-0000-0000-0000-000000000002','33333333-0000-0000-0000-000000000001', NOW()-INTERVAL '5 minutes', 63.5, 14.7900, 120.9050, 55.0, 45397.4, 'on', FALSE, NULL, NULL);

-- Recent telemetry for TRK-002 (ended trip)
INSERT INTO telemetry_logs (truck_id, driver_id, trip_id, timestamp,
                            fuel_level, lat, lon, speed, odometer_km, engine_status)
VALUES
  ('11111111-0000-0000-0000-000000000002','22222222-0000-0000-0000-000000000003','33333333-0000-0000-0000-000000000002', NOW()-INTERVAL '1 day 5 hours', 88.0, 14.5995, 120.9842, 0.0,  32100.0, 'on'),
  ('11111111-0000-0000-0000-000000000002','22222222-0000-0000-0000-000000000003','33333333-0000-0000-0000-000000000002', NOW()-INTERVAL '1 day 4 hours', 84.5, 14.5000, 121.0200, 70.0, 32150.0, 'on'),
  ('11111111-0000-0000-0000-000000000002','22222222-0000-0000-0000-000000000003','33333333-0000-0000-0000-000000000002', NOW()-INTERVAL '1 day 3 hours', 80.1, 14.3500, 121.0800, 75.0, 32250.0, 'on'),
  ('11111111-0000-0000-0000-000000000002','22222222-0000-0000-0000-000000000003','33333333-0000-0000-0000-000000000002', NOW()-INTERVAL '1 day 2 hours', 76.3, 14.2000, 121.1400, 72.0, 32350.0, 'on'),
  ('11111111-0000-0000-0000-000000000002','22222222-0000-0000-0000-000000000003','33333333-0000-0000-0000-000000000002', NOW()-INTERVAL '1 day 1 hour',  73.0, 14.0800, 121.1800, 68.0, 32314.6, 'on');

-- ── 5. ALERTS ────────────────────────────────────────────────
INSERT INTO alerts (truck_id, driver_id, trip_id, timestamp, alert_type, message, severity, is_resolved)
VALUES
  -- Fuel anomaly on TRK-001 (matches anomaly telemetry above)
  (
    '11111111-0000-0000-0000-000000000001',
    '22222222-0000-0000-0000-000000000002',
    '33333333-0000-0000-0000-000000000001',
    NOW()-INTERVAL '30 minutes',
    'fuel_anomaly',
    'Sudden fuel drop of 15.6% detected while vehicle was stationary. Possible siphoning or sensor fault.',
    'high',
    FALSE
  ),
  -- Overspeed on TRK-002 (ended trip)
  (
    '11111111-0000-0000-0000-000000000002',
    '22222222-0000-0000-0000-000000000003',
    '33333333-0000-0000-0000-000000000002',
    NOW()-INTERVAL '1 day 3.5 hours',
    'overspeed',
    'Speed of 112 km/h exceeded the 100 km/h threshold for 4 minutes.',
    'medium',
    TRUE
  ),
  -- Maintenance on TRK-003 (no active trip)
  (
    '11111111-0000-0000-0000-000000000003',
    '22222222-0000-0000-0000-000000000004',
    NULL,
    NOW()-INTERVAL '2 days',
    'maintenance',
    'Cumulative distance of 5,000 km reached. Oil change and preventive maintenance required.',
    'high',
    FALSE
  ),
  -- Low fuel on TRK-004
  (
    '11111111-0000-0000-0000-000000000004',
    '22222222-0000-0000-0000-000000000005',
    '33333333-0000-0000-0000-000000000003',
    NOW()-INTERVAL '2 days 1 hour',
    'low_fuel',
    'Fuel level dropped below 20%. Refueling recommended before next trip.',
    'medium',
    TRUE
  ),
  -- Rest alert on TRK-001 (active trip, driver on road 3+ hours)
  (
    '11111111-0000-0000-0000-000000000001',
    '22222222-0000-0000-0000-000000000002',
    '33333333-0000-0000-0000-000000000001',
    NOW()-INTERVAL '15 minutes',
    'rest_alert',
    'Driver Juan Dela Cruz has been operating for 2 hours 45 minutes. Rest break recommended.',
    'low',
    FALSE
  );
