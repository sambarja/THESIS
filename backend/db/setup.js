/**
 * THESIS Fleet — One-shot setup: schema + seed
 * Run this ONCE after unpausing your Supabase project.
 *
 * Usage (from THESIS/backend):
 *   node db/setup.js
 *
 * Requires .env to have SUPABASE_URL and SUPABASE_SERVICE_KEY
 * (Service role key — get it from: Supabase → Project Settings → API → service_role)
 *
 * If you only have the anon key, add the service key:
 *   echo SUPABASE_SERVICE_KEY=your_service_key_here >> .env
 */

require('dotenv').config({ path: require('path').join(__dirname, '../.env') });
const { createClient } = require('@supabase/supabase-js');
const bcrypt           = require('bcryptjs');
const fs               = require('fs');
const path             = require('path');

// Use service key for DDL (schema creation) — falls back to anon key if not set
const key = process.env.SUPABASE_SERVICE_KEY || process.env.SUPABASE_KEY;
const supabase = createClient(process.env.SUPABASE_URL, key);

// ─── Step 1: Verify connection ───────────────────────────────
async function checkConnection() {
  console.log(`\nConnecting to: ${process.env.SUPABASE_URL}`);
  try {
    const res = await fetch(`${process.env.SUPABASE_URL}/rest/v1/`, {
      headers: { apikey: key, Authorization: `Bearer ${key}` },
    });
    if (!res.ok && res.status !== 200) {
      throw new Error(`HTTP ${res.status}`);
    }
    console.log('✓ Supabase reachable\n');
  } catch (err) {
    console.error('✗ Cannot reach Supabase:', err.message);
    console.error('\nFix: Go to supabase.com → your project → click "Restore project"');
    process.exit(1);
  }
}

// ─── Step 2: Run schema SQL via Management API ───────────────
async function runSchema() {
  console.log('Running schema SQL...');

  // Try using the pg-based direct connection via Supabase Management API
  const projectRef = process.env.SUPABASE_URL.match(/https:\/\/([^.]+)\.supabase\.co/)?.[1];
  const pat = process.env.SUPABASE_PAT; // personal access token (optional)

  if (pat && projectRef) {
    // Use Management API to run SQL (most reliable)
    const schemaSql = fs.readFileSync(path.join(__dirname, 'schema.sql'), 'utf8');
    const statements = schemaSql
      .split(/;(?:\s*\n)/)
      .map(s => s.trim())
      .filter(s => s.length > 3 && !s.startsWith('--'));

    let failed = 0;
    for (const stmt of statements) {
      const res = await fetch(
        `https://api.supabase.com/v1/projects/${projectRef}/database/query`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${pat}`,
          },
          body: JSON.stringify({ query: stmt + ';' }),
        }
      );
      if (!res.ok) {
        const body = await res.text();
        // Ignore "already exists" errors
        if (!body.includes('already exists')) {
          console.warn(`  WARN: ${body.slice(0, 120)}`);
          failed++;
        }
      }
    }
    console.log(failed === 0 ? '✓ Schema applied\n' : `⚠ Schema applied with ${failed} warning(s)\n`);
    return;
  }

  // Fallback: try to verify tables exist by querying them
  console.log('  (No SUPABASE_PAT — checking if tables already exist...)');
  const tables = ['trucks', 'users', 'trip_sessions', 'telemetry_logs', 'alerts'];
  const missing = [];

  for (const t of tables) {
    const { error } = await supabase.from(t).select('id').limit(1);
    if (error && error.code === '42P01') missing.push(t);  // 42P01 = undefined_table
  }

  if (missing.length > 0) {
    console.error(`\n✗ Missing tables: ${missing.join(', ')}`);
    console.error('\nTo create them, do ONE of the following:\n');
    console.error('Option A (easiest):');
    console.error('  1. Open supabase.com → SQL Editor → New Query');
    console.error('  2. Paste the contents of: THESIS/backend/db/schema.sql');
    console.error('  3. Click Run, then re-run this script\n');
    console.error('Option B (automated):');
    console.error('  1. Get your personal access token: supabase.com → Account → Access Tokens');
    console.error('  2. Add to .env:  SUPABASE_PAT=your_token_here');
    console.error('  3. Re-run this script\n');
    process.exit(1);
  }

  console.log('✓ All tables exist\n');
}

// ─── Step 3: Seed data ────────────────────────────────────────
async function seedData() {
  console.log('Seeding data...');
  const hash = await bcrypt.hash('password123', 10);

  // Trucks
  const { error: tErr } = await supabase.from('trucks').upsert([
    { id: '11111111-0000-0000-0000-000000000001', truck_code: 'TRK-001', plate_number: 'ABC-1234', model: 'Isuzu Elf NHR 2020',    status: 'active',      device_installed: true,  notes: 'Primary delivery truck — north route' },
    { id: '11111111-0000-0000-0000-000000000002', truck_code: 'TRK-002', plate_number: 'DEF-5678', model: 'Mitsubishi Fuso 2019',   status: 'idle',        device_installed: true,  notes: 'Secondary unit — south route' },
    { id: '11111111-0000-0000-0000-000000000003', truck_code: 'TRK-003', plate_number: 'GHI-9012', model: 'Hino 300 Series 2021',   status: 'maintenance', device_installed: true,  notes: 'Scheduled oil change due' },
    { id: '11111111-0000-0000-0000-000000000004', truck_code: 'TRK-004', plate_number: 'JKL-3456', model: 'Isuzu NLR 2022',         status: 'low_fuel',    device_installed: true,  notes: 'East route unit' },
  ], { onConflict: 'id' });
  if (tErr) { console.error('Trucks:', tErr.message); process.exit(1); }
  console.log('  ✓ Trucks (4)');

  // Users
  const { error: uErr } = await supabase.from('users').upsert([
    { id: '22222222-0000-0000-0000-000000000001', full_name: 'Fleet Admin',    email: 'admin@fleetsgsa.com',   password_hash: hash, role: 'admin',  assigned_truck_id: null,                                   is_active: true },
    { id: '22222222-0000-0000-0000-000000000002', full_name: 'Juan Dela Cruz', email: 'juan@fleetsgsa.com',    password_hash: hash, role: 'driver', assigned_truck_id: '11111111-0000-0000-0000-000000000001', is_active: true },
    { id: '22222222-0000-0000-0000-000000000003', full_name: 'Maria Santos',   email: 'maria@fleetsgsa.com',   password_hash: hash, role: 'driver', assigned_truck_id: '11111111-0000-0000-0000-000000000002', is_active: true },
    { id: '22222222-0000-0000-0000-000000000004', full_name: 'Roberto Garcia', email: 'roberto@fleetsgsa.com', password_hash: hash, role: 'driver', assigned_truck_id: '11111111-0000-0000-0000-000000000003', is_active: true },
    { id: '22222222-0000-0000-0000-000000000005', full_name: 'Ana Reyes',      email: 'ana@fleetsgsa.com',     password_hash: hash, role: 'driver', assigned_truck_id: '11111111-0000-0000-0000-000000000004', is_active: true },
  ], { onConflict: 'id' });
  if (uErr) { console.error('Users:', uErr.message); process.exit(1); }
  console.log('  ✓ Users (1 admin + 4 drivers)');

  // Trip sessions
  const now = new Date();
  const ago  = (h, d = 0) => new Date(now - d * 86400000 - h * 3600000).toISOString();

  const { error: trErr } = await supabase.from('trip_sessions').upsert([
    { id: '33333333-0000-0000-0000-000000000001', truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', start_time: ago(3),    end_time: null,    trip_status: 'active', start_lat: 14.5995, start_lon: 120.9842, distance_km: 87.4,  operating_hours: 3.0 },
    { id: '33333333-0000-0000-0000-000000000002', truck_id: '11111111-0000-0000-0000-000000000002', driver_id: '22222222-0000-0000-0000-000000000003', start_time: ago(5, 1), end_time: ago(1, 1), trip_status: 'ended', start_lat: 14.5995, start_lon: 120.9842, end_lat: 14.0800, end_lon: 121.1800, distance_km: 214.6, operating_hours: 4.0 },
    { id: '33333333-0000-0000-0000-000000000003', truck_id: '11111111-0000-0000-0000-000000000004', driver_id: '22222222-0000-0000-0000-000000000005', start_time: ago(4, 2), end_time: new Date(now - 2*86400000 - 30*60000).toISOString(), trip_status: 'ended', start_lat: 14.5995, start_lon: 120.9842, end_lat: 14.5300, end_lon: 121.2000, distance_km: 112.3, operating_hours: 3.5 },
  ], { onConflict: 'id' });
  if (trErr) { console.error('Trips:', trErr.message); process.exit(1); }
  console.log('  ✓ Trip sessions (1 active + 2 ended)');

  // Telemetry logs
  const min = (m) => new Date(now - m * 60000).toISOString();
  const { error: telErr } = await supabase.from('telemetry_logs').insert([
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: ago(3),    fuel_level: 92.0, lat: 14.5995, lon: 120.9842, speed:  0.0, odometer_km: 45210.0, engine_status: 'on', anomaly_flag: false },
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: ago(2.5),  fuel_level: 90.2, lat: 14.6200, lon: 120.9750, speed: 72.0, odometer_km: 45246.2, engine_status: 'on', anomaly_flag: false },
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: ago(2),    fuel_level: 88.5, lat: 14.6500, lon: 120.9650, speed: 68.0, odometer_km: 45282.4, engine_status: 'on', anomaly_flag: false },
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: ago(1.5),  fuel_level: 86.1, lat: 14.6900, lon: 120.9500, speed: 75.0, odometer_km: 45318.6, engine_status: 'on', anomaly_flag: false },
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: ago(1),    fuel_level: 83.3, lat: 14.7200, lon: 120.9350, speed: 80.0, odometer_km: 45354.8, engine_status: 'on', anomaly_flag: false },
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: min(45),   fuel_level: 79.8, lat: 14.7500, lon: 120.9200, speed: 78.0, odometer_km: 45391.0, engine_status: 'on', anomaly_flag: false },
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: min(30),   fuel_level: 64.2, lat: 14.7800, lon: 120.9100, speed:  0.0, odometer_km: 45391.0, engine_status: 'on', anomaly_flag: true,  anomaly_score: 0.87, model_source: 'isolation_forest' },
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: min(5),    fuel_level: 63.5, lat: 14.7900, lon: 120.9050, speed: 55.0, odometer_km: 45397.4, engine_status: 'on', anomaly_flag: false },
    { truck_id: '11111111-0000-0000-0000-000000000002', driver_id: '22222222-0000-0000-0000-000000000003', trip_id: '33333333-0000-0000-0000-000000000002', timestamp: ago(5, 1), fuel_level: 88.0, lat: 14.5995, lon: 120.9842, speed:  0.0, odometer_km: 32100.0, engine_status: 'on' },
    { truck_id: '11111111-0000-0000-0000-000000000002', driver_id: '22222222-0000-0000-0000-000000000003', trip_id: '33333333-0000-0000-0000-000000000002', timestamp: ago(4, 1), fuel_level: 84.5, lat: 14.5000, lon: 121.0200, speed: 70.0, odometer_km: 32150.0, engine_status: 'on' },
    { truck_id: '11111111-0000-0000-0000-000000000002', driver_id: '22222222-0000-0000-0000-000000000003', trip_id: '33333333-0000-0000-0000-000000000002', timestamp: ago(3, 1), fuel_level: 80.1, lat: 14.3500, lon: 121.0800, speed: 75.0, odometer_km: 32250.0, engine_status: 'on' },
    { truck_id: '11111111-0000-0000-0000-000000000002', driver_id: '22222222-0000-0000-0000-000000000003', trip_id: '33333333-0000-0000-0000-000000000002', timestamp: ago(2, 1), fuel_level: 76.3, lat: 14.2000, lon: 121.1400, speed: 72.0, odometer_km: 32350.0, engine_status: 'on' },
    { truck_id: '11111111-0000-0000-0000-000000000002', driver_id: '22222222-0000-0000-0000-000000000003', trip_id: '33333333-0000-0000-0000-000000000002', timestamp: ago(1, 1), fuel_level: 73.0, lat: 14.0800, lon: 121.1800, speed: 68.0, odometer_km: 32314.6, engine_status: 'on' },
  ]);
  if (telErr) { console.error('Telemetry:', telErr.message); process.exit(1); }
  console.log('  ✓ Telemetry logs (13 records)');

  // Alerts
  const { error: aErr } = await supabase.from('alerts').insert([
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: min(30),   alert_type: 'fuel_anomaly', severity: 'high',   is_resolved: false, message: 'Sudden fuel drop of 15.6% while stationary. Possible siphoning.' },
    { truck_id: '11111111-0000-0000-0000-000000000002', driver_id: '22222222-0000-0000-0000-000000000003', trip_id: '33333333-0000-0000-0000-000000000002', timestamp: ago(3.5,1), alert_type: 'overspeed',    severity: 'medium', is_resolved: true,  message: 'Speed of 112 km/h exceeded 100 km/h threshold for 4 minutes.' },
    { truck_id: '11111111-0000-0000-0000-000000000003', driver_id: '22222222-0000-0000-0000-000000000004', trip_id: null,                                   timestamp: ago(0, 2),  alert_type: 'maintenance',  severity: 'high',   is_resolved: false, message: 'Cumulative distance of 5,000 km reached. Oil change required.' },
    { truck_id: '11111111-0000-0000-0000-000000000004', driver_id: '22222222-0000-0000-0000-000000000005', trip_id: '33333333-0000-0000-0000-000000000003', timestamp: ago(1, 2),  alert_type: 'low_fuel',     severity: 'medium', is_resolved: true,  message: 'Fuel level dropped below 20%. Refueling recommended.' },
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: min(15),   alert_type: 'rest_alert',   severity: 'low',    is_resolved: false, message: 'Driver Juan Dela Cruz has been operating 2h 45m. Rest break recommended.' },
  ]);
  if (aErr) { console.error('Alerts:', aErr.message); process.exit(1); }
  console.log('  ✓ Alerts (5 records)');

  console.log('\n✓ Seed complete!');
  console.log('\nTest credentials:');
  console.log('  Admin:  admin@fleetsgsa.com / password123');
  console.log('  Driver: juan@fleetsgsa.com  / password123');
}

async function main() {
  await checkConnection();
  await runSchema();
  await seedData();
  console.log('\nAll done. Start the backend: node server.js');
}

main().catch(err => { console.error(err); process.exit(1); });
