/**
 * THESIS Fleet — Supabase Seed Script
 * ------------------------------------
 * Generates proper bcrypt hashes and inserts all sample data.
 *
 * Usage (from THESIS/backend directory):
 *   node db/seed.js
 *
 * Requirements: .env must have SUPABASE_URL and SUPABASE_KEY
 */

require('dotenv').config({ path: require('path').join(__dirname, '../.env') });
const { createClient } = require('@supabase/supabase-js');
const bcrypt = require('bcryptjs');

const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_KEY);

async function seed() {
  console.log('Starting seed...\n');

  // ── 1. Hash passwords ──────────────────────────────────────
  const hash = await bcrypt.hash('password123', 10);
  console.log('Password hash generated.');

  // ── 2. Trucks ──────────────────────────────────────────────
  const { data: trucks, error: truckErr } = await supabase
    .from('trucks')
    .upsert([
      { id: '11111111-0000-0000-0000-000000000001', truck_code: 'TRK-001', plate_number: 'ABC-1234', model: 'Isuzu Elf NHR 2020',      status: 'active',      device_installed: true,  notes: 'Primary delivery truck — north route' },
      { id: '11111111-0000-0000-0000-000000000002', truck_code: 'TRK-002', plate_number: 'DEF-5678', model: 'Mitsubishi Fuso 2019',     status: 'idle',        device_installed: true,  notes: 'Secondary unit — south route' },
      { id: '11111111-0000-0000-0000-000000000003', truck_code: 'TRK-003', plate_number: 'GHI-9012', model: 'Hino 300 Series 2021',     status: 'maintenance', device_installed: true,  notes: 'Scheduled oil change due' },
      { id: '11111111-0000-0000-0000-000000000004', truck_code: 'TRK-004', plate_number: 'JKL-3456', model: 'Isuzu NLR 2022',           status: 'low_fuel',    device_installed: true,  notes: 'East route unit' },
    ], { onConflict: 'id' })
    .select('id, truck_code');

  if (truckErr) { console.error('Trucks error:', truckErr.message); process.exit(1); }
  console.log('Trucks seeded:', trucks.map(t => t.truck_code).join(', '));

  // ── 3. Users ───────────────────────────────────────────────
  const { data: users, error: userErr } = await supabase
    .from('users')
    .upsert([
      { id: '22222222-0000-0000-0000-000000000001', full_name: 'Fleet Admin',    email: 'admin@fleetsgsa.com',   password_hash: hash, role: 'admin',  assigned_truck_id: null,                                   is_active: true },
      { id: '22222222-0000-0000-0000-000000000002', full_name: 'Juan Dela Cruz', email: 'juan@fleetsgsa.com',    password_hash: hash, role: 'driver', assigned_truck_id: '11111111-0000-0000-0000-000000000001', is_active: true },
      { id: '22222222-0000-0000-0000-000000000003', full_name: 'Maria Santos',   email: 'maria@fleetsgsa.com',   password_hash: hash, role: 'driver', assigned_truck_id: '11111111-0000-0000-0000-000000000002', is_active: true },
      { id: '22222222-0000-0000-0000-000000000004', full_name: 'Roberto Garcia', email: 'roberto@fleetsgsa.com', password_hash: hash, role: 'driver', assigned_truck_id: '11111111-0000-0000-0000-000000000003', is_active: true },
      { id: '22222222-0000-0000-0000-000000000005', full_name: 'Ana Reyes',      email: 'ana@fleetsgsa.com',     password_hash: hash, role: 'driver', assigned_truck_id: '11111111-0000-0000-0000-000000000004', is_active: true },
    ], { onConflict: 'id' })
    .select('id, full_name, role');

  if (userErr) { console.error('Users error:', userErr.message); process.exit(1); }
  console.log('Users seeded:', users.map(u => `${u.full_name} (${u.role})`).join(', '));

  // ── 4. Trip Sessions ───────────────────────────────────────
  const now = new Date();
  const hoursAgo  = (h)  => new Date(now - h * 3600000).toISOString();
  const daysAgo   = (d, h = 0) => new Date(now - d * 86400000 - h * 3600000).toISOString();

  const { data: trips, error: tripErr } = await supabase
    .from('trip_sessions')
    .upsert([
      {
        id: '33333333-0000-0000-0000-000000000001',
        truck_id: '11111111-0000-0000-0000-000000000001',
        driver_id: '22222222-0000-0000-0000-000000000002',
        start_time: hoursAgo(3), end_time: null, trip_status: 'active',
        start_lat: 14.5995, start_lon: 120.9842,
        distance_km: 87.4, operating_hours: 3.0,
      },
      {
        id: '33333333-0000-0000-0000-000000000002',
        truck_id: '11111111-0000-0000-0000-000000000002',
        driver_id: '22222222-0000-0000-0000-000000000003',
        start_time: daysAgo(1, 5), end_time: daysAgo(1, 1), trip_status: 'ended',
        start_lat: 14.5995, start_lon: 120.9842,
        end_lat: 14.0800, end_lon: 121.1800,
        distance_km: 214.6, operating_hours: 4.0,
      },
      {
        id: '33333333-0000-0000-0000-000000000003',
        truck_id: '11111111-0000-0000-0000-000000000004',
        driver_id: '22222222-0000-0000-0000-000000000005',
        start_time: daysAgo(2, 4), end_time: new Date(now - 2 * 86400000 - 30 * 60000).toISOString(),
        trip_status: 'ended',
        start_lat: 14.5995, start_lon: 120.9842,
        end_lat: 14.5300, end_lon: 121.2000,
        distance_km: 112.3, operating_hours: 3.5,
      },
    ], { onConflict: 'id' })
    .select('id, trip_status');

  if (tripErr) { console.error('Trips error:', tripErr.message); process.exit(1); }
  console.log('Trips seeded:', trips.map(t => t.trip_status).join(', '));

  // ── 5. Telemetry Logs ──────────────────────────────────────
  const mins = (m) => new Date(now - m * 60000).toISOString();
  const hrMin = (h, m) => new Date(now - h * 3600000 - m * 60000).toISOString();

  const telemetry = [
    // TRK-001 active trip (8 readings)
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: hrMin(3,0),  fuel_level: 92.0, lat: 14.5995, lon: 120.9842, speed:  0.0, odometer_km: 45210.0, engine_status: 'on',  anomaly_flag: false },
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: hrMin(2,30), fuel_level: 90.2, lat: 14.6200, lon: 120.9750, speed: 72.0, odometer_km: 45246.2, engine_status: 'on',  anomaly_flag: false },
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: hrMin(2,0),  fuel_level: 88.5, lat: 14.6500, lon: 120.9650, speed: 68.0, odometer_km: 45282.4, engine_status: 'on',  anomaly_flag: false },
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: hrMin(1,30), fuel_level: 86.1, lat: 14.6900, lon: 120.9500, speed: 75.0, odometer_km: 45318.6, engine_status: 'on',  anomaly_flag: false },
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: hrMin(1,0),  fuel_level: 83.3, lat: 14.7200, lon: 120.9350, speed: 80.0, odometer_km: 45354.8, engine_status: 'on',  anomaly_flag: false },
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: mins(45),    fuel_level: 79.8, lat: 14.7500, lon: 120.9200, speed: 78.0, odometer_km: 45391.0, engine_status: 'on',  anomaly_flag: false },
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: mins(30),    fuel_level: 64.2, lat: 14.7800, lon: 120.9100, speed:  0.0, odometer_km: 45391.0, engine_status: 'on',  anomaly_flag: true,  anomaly_score: 0.87, model_source: 'isolation_forest' },
    { truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002', trip_id: '33333333-0000-0000-0000-000000000001', timestamp: mins(5),     fuel_level: 63.5, lat: 14.7900, lon: 120.9050, speed: 55.0, odometer_km: 45397.4, engine_status: 'on',  anomaly_flag: false },
    // TRK-002 ended trip
    { truck_id: '11111111-0000-0000-0000-000000000002', driver_id: '22222222-0000-0000-0000-000000000003', trip_id: '33333333-0000-0000-0000-000000000002', timestamp: daysAgo(1,5), fuel_level: 88.0, lat: 14.5995, lon: 120.9842, speed:  0.0, odometer_km: 32100.0, engine_status: 'on' },
    { truck_id: '11111111-0000-0000-0000-000000000002', driver_id: '22222222-0000-0000-0000-000000000003', trip_id: '33333333-0000-0000-0000-000000000002', timestamp: daysAgo(1,4), fuel_level: 84.5, lat: 14.5000, lon: 121.0200, speed: 70.0, odometer_km: 32150.0, engine_status: 'on' },
    { truck_id: '11111111-0000-0000-0000-000000000002', driver_id: '22222222-0000-0000-0000-000000000003', trip_id: '33333333-0000-0000-0000-000000000002', timestamp: daysAgo(1,3), fuel_level: 80.1, lat: 14.3500, lon: 121.0800, speed: 75.0, odometer_km: 32250.0, engine_status: 'on' },
    { truck_id: '11111111-0000-0000-0000-000000000002', driver_id: '22222222-0000-0000-0000-000000000003', trip_id: '33333333-0000-0000-0000-000000000002', timestamp: daysAgo(1,2), fuel_level: 76.3, lat: 14.2000, lon: 121.1400, speed: 72.0, odometer_km: 32350.0, engine_status: 'on' },
    { truck_id: '11111111-0000-0000-0000-000000000002', driver_id: '22222222-0000-0000-0000-000000000003', trip_id: '33333333-0000-0000-0000-000000000002', timestamp: daysAgo(1,1), fuel_level: 73.0, lat: 14.0800, lon: 121.1800, speed: 68.0, odometer_km: 32314.6, engine_status: 'on' },
  ];

  const { error: telErr } = await supabase.from('telemetry_logs').insert(telemetry);
  if (telErr) { console.error('Telemetry error:', telErr.message); process.exit(1); }
  console.log(`Telemetry seeded: ${telemetry.length} records`);

  // ── 6. Alerts ──────────────────────────────────────────────
  const { error: alertErr } = await supabase.from('alerts').insert([
    {
      truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002',
      trip_id: '33333333-0000-0000-0000-000000000001', timestamp: mins(30),
      alert_type: 'fuel_anomaly', severity: 'high', is_resolved: false,
      message: 'Sudden fuel drop of 15.6% detected while vehicle was stationary. Possible siphoning or sensor fault.',
    },
    {
      truck_id: '11111111-0000-0000-0000-000000000002', driver_id: '22222222-0000-0000-0000-000000000003',
      trip_id: '33333333-0000-0000-0000-000000000002', timestamp: daysAgo(1, 3.5),
      alert_type: 'overspeed', severity: 'medium', is_resolved: true,
      message: 'Speed of 112 km/h exceeded the 100 km/h threshold for 4 minutes.',
    },
    {
      truck_id: '11111111-0000-0000-0000-000000000003', driver_id: '22222222-0000-0000-0000-000000000004',
      trip_id: null, timestamp: daysAgo(2),
      alert_type: 'maintenance', severity: 'high', is_resolved: false,
      message: 'Cumulative distance of 5,000 km reached. Oil change and preventive maintenance required.',
    },
    {
      truck_id: '11111111-0000-0000-0000-000000000004', driver_id: '22222222-0000-0000-0000-000000000005',
      trip_id: '33333333-0000-0000-0000-000000000003', timestamp: daysAgo(2, 1),
      alert_type: 'low_fuel', severity: 'medium', is_resolved: true,
      message: 'Fuel level dropped below 20%. Refueling recommended before next trip.',
    },
    {
      truck_id: '11111111-0000-0000-0000-000000000001', driver_id: '22222222-0000-0000-0000-000000000002',
      trip_id: '33333333-0000-0000-0000-000000000001', timestamp: mins(15),
      alert_type: 'rest_alert', severity: 'low', is_resolved: false,
      message: 'Driver Juan Dela Cruz has been operating for 2 hours 45 minutes. Rest break recommended.',
    },
  ]);

  if (alertErr) { console.error('Alerts error:', alertErr.message); process.exit(1); }
  console.log('Alerts seeded: 5 records');

  console.log('\n✓ Seed complete!');
  console.log('\nTest login credentials:');
  console.log('  Admin:  admin@fleetsgsa.com  / password123');
  console.log('  Driver: juan@fleetsgsa.com   / password123');
}

seed().catch(err => { console.error(err); process.exit(1); });
