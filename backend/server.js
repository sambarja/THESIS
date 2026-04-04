require('dotenv').config();
const express = require('express');
const cors    = require('cors');
const bcrypt  = require('bcryptjs');
const { createClient } = require('@supabase/supabase-js');

const app = express();
app.use(cors());
app.use(express.json());

// Service role key bypasses RLS — server-side only, never exposed to client
const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_KEY || process.env.SUPABASE_KEY
);

// ─────────────────────────────────────────────────────────────
// RBAC CONSTANTS
// ─────────────────────────────────────────────────────────────
const DASHBOARD_ROLES = ['head_admin', 'fleet_manager', 'manager'];

// ─────────────────────────────────────────────────────────────
// AUTH HELPER — resolves user from Bearer token (user_id)
// ─────────────────────────────────────────────────────────────
async function resolveUser(req) {
  const auth = req.headers['authorization'] || '';
  const userId = auth.startsWith('Bearer ') ? auth.slice(7).trim() : null;
  if (!userId) return null;
  const { data } = await supabase
    .from('users')
    .select('id, full_name, email, role, is_active')
    .eq('id', userId)
    .single();
  return data && data.is_active ? data : null;
}

// ─────────────────────────────────────────────────────────────
// MIDDLEWARE — dashboard access (head_admin, fleet_manager, manager)
// ─────────────────────────────────────────────────────────────
async function requireDashboard(req, res, next) {
  const user = await resolveUser(req);
  if (!user) return res.status(401).json({ error: 'Unauthorized — please log in' });
  if (!DASHBOARD_ROLES.includes(user.role))
    return res.status(403).json({ error: 'Access denied — dashboard is for admin accounts only' });
  req.user = user;
  next();
}

// ─────────────────────────────────────────────────────────────
// MIDDLEWARE — settings access (head_admin only)
// ─────────────────────────────────────────────────────────────
async function requireHeadAdmin(req, res, next) {
  const user = await resolveUser(req);
  if (!user) return res.status(401).json({ error: 'Unauthorized — please log in' });
  if (user.role !== 'head_admin')
    return res.status(403).json({ error: 'Access denied — Settings is restricted to Head Admin only' });
  req.user = user;
  next();
}
const PORT = process.env.PORT || 5000;

// ─────────────────────────────────────────────────────────────
// HEALTH CHECK
// ─────────────────────────────────────────────────────────────
app.get('/', (_req, res) => {
  res.json({ status: 'ok', service: 'Fleet Monitoring API v2' });
});

// ─────────────────────────────────────────────────────────────
// AUTH — POST /login  (dashboard admin login — drivers blocked)
// ─────────────────────────────────────────────────────────────
app.post('/login', async (req, res) => {
  const { email, password } = req.body;
  if (!email || !password)
    return res.status(400).json({ error: 'Email and password required' });

  const { data: user, error } = await supabase
    .from('users')
    .select('id, full_name, email, password_hash, role, is_active')
    .eq('email', email)
    .single();

  if (error || !user)
    return res.status(401).json({ error: 'Invalid email or password' });

  if (!user.is_active)
    return res.status(403).json({ error: 'Account is disabled' });

  // Drivers are not allowed to access the admin dashboard
  if (user.role === 'driver')
    return res.status(403).json({
      error: 'Driver accounts cannot access the admin dashboard. Use the truck device app to log in.',
    });

  const match = await bcrypt.compare(password, user.password_hash);
  if (!match)
    return res.status(401).json({ error: 'Invalid email or password' });

  res.json({
    user_id:   user.id,
    full_name: user.full_name,
    email:     user.email,
    role:      user.role,
  });
});

// ─────────────────────────────────────────────────────────────
// DRIVER DEVICE AUTH — POST /driver/login  (truck-side device only)
// ─────────────────────────────────────────────────────────────
app.post('/driver/login', async (req, res) => {
  const { email, password } = req.body;
  if (!email || !password)
    return res.status(400).json({ error: 'Email and password required' });

  const { data: user, error } = await supabase
    .from('users')
    .select('id, full_name, email, password_hash, role, is_active')
    .eq('email', email)
    .single();

  if (error || !user)
    return res.status(401).json({ error: 'Invalid email or password' });

  if (!user.is_active)
    return res.status(403).json({ error: 'Account is disabled' });

  // Only drivers can use the device login
  if (user.role !== 'driver')
    return res.status(403).json({ error: 'This login is for driver accounts only' });

  const match = await bcrypt.compare(password, user.password_hash);
  if (!match)
    return res.status(401).json({ error: 'Invalid email or password' });

  // Check if driver has an active trip
  const { data: activeTrip } = await supabase
    .from('trip_sessions')
    .select('id, truck_id, start_time, trucks(truck_code, plate_number)')
    .eq('driver_id', user.id)
    .eq('trip_status', 'active')
    .order('start_time', { ascending: false })
    .limit(1)
    .single();

  res.json({
    user_id:     user.id,
    full_name:   user.full_name,
    email:       user.email,
    role:        user.role,
    active_trip: activeTrip ?? null,
  });
});

// ─────────────────────────────────────────────────────────────
// FLEET STATUS — GET /fleet/status
// Returns one object per truck with latest telemetry + active trip
// ─────────────────────────────────────────────────────────────
app.get('/fleet/status', requireDashboard, async (req, res) => {
  const { data: trucks, error: tErr } = await supabase
    .from('trucks')
    .select('*')
    .order('truck_code');

  if (tErr) return res.status(400).json({ error: tErr.message });

  const statuses = await Promise.all(trucks.map(async (truck) => {
    // Latest telemetry
    const { data: latest } = await supabase
      .from('telemetry_logs')
      .select('fuel_level, lat, lon, speed, odometer_km, timestamp, anomaly_flag')
      .eq('truck_id', truck.id)
      .order('timestamp', { ascending: false })
      .limit(1)
      .single();

    // Active trip
    const { data: trip } = await supabase
      .from('trip_sessions')
      .select('id, start_time, distance_km, operating_hours, driver_id')
      .eq('truck_id', truck.id)
      .eq('trip_status', 'active')
      .order('start_time', { ascending: false })
      .limit(1)
      .single();

    // Driver name for active trip
    let driverName = null;
    if (trip?.driver_id) {
      const { data: drv } = await supabase
        .from('users')
        .select('full_name')
        .eq('id', trip.driver_id)
        .single();
      driverName = drv?.full_name ?? null;
    }

    // Unresolved alerts count
    const { count: alertCount } = await supabase
      .from('alerts')
      .select('id', { count: 'exact', head: true })
      .eq('truck_id', truck.id)
      .eq('is_resolved', false);

    const ONLINE_MS = 10 * 60 * 1000; // 10 min
    const isOnline  = latest?.timestamp
      ? Date.now() - new Date(latest.timestamp).getTime() < ONLINE_MS
      : false;

    return {
      id:               truck.id,
      truck_code:       truck.truck_code,
      plate_number:     truck.plate_number,
      model:            truck.model,
      status:           truck.status,
      device_installed: truck.device_installed,

      // Telemetry
      fuel_level:  latest?.fuel_level  ?? null,
      speed:       latest?.speed       ?? null,
      lat:         latest?.lat         ?? null,
      lon:         latest?.lon         ?? null,
      odometer_km: latest?.odometer_km ?? null,
      last_update: latest?.timestamp   ?? null,
      is_online:   isOnline,
      anomaly_flag: latest?.anomaly_flag ?? false,

      // Active trip
      trip_id:          trip?.id         ?? null,
      trip_status:      trip ? 'active' : 'idle',
      trip_start_time:  trip?.start_time ?? null,
      distance_km:      trip?.distance_km      ?? 0,
      operating_hours:  trip?.operating_hours  ?? 0,
      driver_id:        trip?.driver_id        ?? null,
      driver_name:      driverName,

      // Alerts
      active_alert_count: alertCount ?? 0,
    };
  }));

  res.json(statuses);
});

// ─────────────────────────────────────────────────────────────
// TRUCKS
// ─────────────────────────────────────────────────────────────

// GET /trucks — all trucks (with assigned driver looked up separately)
app.get('/trucks', requireDashboard, async (_req, res) => {
  const { data: trucks, error } = await supabase
    .from('trucks')
    .select('*')
    .order('truck_code');

  if (error) return res.status(400).json({ error: error.message });

  // Attach assigned driver to each truck
  const result = await Promise.all(trucks.map(async (truck) => {
    const { data: driver } = await supabase
      .from('users')
      .select('id, full_name, email')
      .eq('assigned_truck_id', truck.id)
      .single();
    return { ...truck, driver: driver ?? null };
  }));

  res.json(result);
});

// GET /trucks/:id — single truck with assigned driver
app.get('/trucks/:id', requireDashboard, async (req, res) => {
  const { data: truck, error } = await supabase
    .from('trucks')
    .select('*')
    .eq('id', req.params.id)
    .single();

  if (error) return res.status(404).json({ error: 'Truck not found' });

  const { data: driver } = await supabase
    .from('users')
    .select('id, full_name, email')
    .eq('assigned_truck_id', truck.id)
    .single();

  res.json({ ...truck, driver: driver ?? null });
});

// GET /trucks/:id/telemetry/latest — most recent telemetry reading
app.get('/trucks/:id/telemetry/latest', requireDashboard, async (req, res) => {
  const { data, error } = await supabase
    .from('telemetry_logs')
    .select('*')
    .eq('truck_id', req.params.id)
    .order('timestamp', { ascending: false })
    .limit(1)
    .single();

  if (error) return res.status(404).json({ error: 'No telemetry found' });
  res.json(data);
});

// GET /trucks/:id/telemetry/history?limit=50 — recent telemetry history
app.get('/trucks/:id/telemetry/history', requireDashboard, async (req, res) => {
  const limit = Math.min(parseInt(req.query.limit ?? '50'), 500);

  const { data, error } = await supabase
    .from('telemetry_logs')
    .select('id, timestamp, fuel_level, lat, lon, speed, odometer_km, engine_status, anomaly_flag, anomaly_score, model_source')
    .eq('truck_id', req.params.id)
    .order('timestamp', { ascending: false })
    .limit(limit);

  if (error) return res.status(400).json({ error: error.message });
  res.json(data.reverse()); // return in chronological order
});

// GET /trucks/:id/trips — all trips for a truck
app.get('/trucks/:id/trips', requireDashboard, async (req, res) => {
  const { data, error } = await supabase
    .from('trip_sessions')
    .select('*')
    .eq('truck_id', req.params.id)
    .order('start_time', { ascending: false });

  if (error) return res.status(400).json({ error: error.message });
  res.json(data);
});

// ─────────────────────────────────────────────────────────────
// TRIPS
// ─────────────────────────────────────────────────────────────

// GET /trips/:id — single trip details
app.get('/trips/:id', requireDashboard, async (req, res) => {
  const { data: trip, error } = await supabase
    .from('trip_sessions')
    .select('*')
    .eq('id', req.params.id)
    .single();

  if (error) return res.status(404).json({ error: 'Trip not found' });

  const [{ data: truck }, { data: driver }] = await Promise.all([
    supabase.from('trucks').select('truck_code, plate_number, model').eq('id', trip.truck_id).single(),
    supabase.from('users').select('full_name, email').eq('id', trip.driver_id).single(),
  ]);

  res.json({ ...trip, truck: truck ?? null, driver: driver ?? null });
});

// GET /trips/:id/route — GPS polyline for a trip
app.get('/trips/:id/route', requireDashboard, async (req, res) => {
  const { data, error } = await supabase
    .from('telemetry_logs')
    .select('lat, lon, fuel_level, speed, timestamp')
    .eq('trip_id', req.params.id)
    .not('lat', 'is', null)
    .not('lon', 'is', null)
    .order('timestamp', { ascending: true });

  if (error) return res.status(400).json({ error: error.message });
  res.json(data);
});

// POST /trip/start — start a new trip
app.post('/trip/start', async (req, res) => {
  const { truck_id, driver_id, start_lat, start_lon } = req.body;

  if (!truck_id || !driver_id)
    return res.status(400).json({ error: 'truck_id and driver_id required' });

  // Ensure no active trip for this truck
  const { data: existing } = await supabase
    .from('trip_sessions')
    .select('id')
    .eq('truck_id', truck_id)
    .eq('trip_status', 'active')
    .limit(1)
    .single();

  if (existing)
    return res.status(409).json({ error: 'Truck already has an active trip', trip_id: existing.id });

  const { data, error } = await supabase
    .from('trip_sessions')
    .insert([{ truck_id, driver_id, start_lat, start_lon, trip_status: 'active' }])
    .select()
    .single();

  if (error) return res.status(400).json({ error: error.message });

  // Mark truck as active
  await supabase.from('trucks').update({ status: 'active' }).eq('id', truck_id);

  res.status(201).json(data);
});

// POST /trip/end — end an active trip
app.post('/trip/end', async (req, res) => {
  const { trip_id, end_lat, end_lon } = req.body;

  if (!trip_id)
    return res.status(400).json({ error: 'trip_id required' });

  // Get trip + compute operating hours
  const { data: trip, error: fetchErr } = await supabase
    .from('trip_sessions')
    .select('id, truck_id, start_time, distance_km')
    .eq('id', trip_id)
    .single();

  if (fetchErr || !trip)
    return res.status(404).json({ error: 'Trip not found' });

  const endTime       = new Date();
  const operatingHours = +((endTime - new Date(trip.start_time)) / 3600000).toFixed(2);

  const { data, error } = await supabase
    .from('trip_sessions')
    .update({
      end_time:        endTime.toISOString(),
      trip_status:     'ended',
      end_lat,
      end_lon,
      operating_hours: operatingHours,
    })
    .eq('id', trip_id)
    .select()
    .single();

  if (error) return res.status(400).json({ error: error.message });

  // Mark truck as idle
  await supabase.from('trucks').update({ status: 'idle' }).eq('id', trip.truck_id);

  res.json(data);
});

// ─────────────────────────────────────────────────────────────
// TELEMETRY INGESTION — POST /telemetry
// Primary ingestion endpoint. Triggers ML anomaly detection.
// ─────────────────────────────────────────────────────────────
app.post('/telemetry', async (req, res) => {
  const receivedAt = new Date().toISOString();
  const {
    truck_id, driver_id, trip_id,
    fuel_level, lat, lon, speed, odometer_km,
    engine_status = 'on',
    sent_at,
  } = req.body;

  if (!truck_id) return res.status(400).json({ error: 'truck_id required' });

  const latencyMs = sent_at ? Date.now() - new Date(sent_at).getTime() : null;

  // Insert telemetry
  const { data, error } = await supabase
    .from('telemetry_logs')
    .insert([{ truck_id, driver_id, trip_id, fuel_level, lat, lon, speed, odometer_km, engine_status }])
    .select()
    .single();

  if (error) return res.status(400).json({ error: error.message });

  // Log latency for SO2-c
  try {
    await supabase.from('latency_logs')
      .insert([{ truck_id, sent_at: sent_at ?? null, received_at: receivedAt, latency_ms: latencyMs }]);
  } catch { /* ignore if table missing */ }

  // Update trip distance if trip_id provided
  if (trip_id && odometer_km != null) {
    const { data: firstLog } = await supabase
      .from('telemetry_logs')
      .select('odometer_km')
      .eq('trip_id', trip_id)
      .not('odometer_km', 'is', null)
      .order('timestamp', { ascending: true })
      .limit(1)
      .single();

    if (firstLog) {
      const distance = Math.max(0, odometer_km - firstLog.odometer_km);
      await supabase.from('trip_sessions')
        .update({ distance_km: +distance.toFixed(1) })
        .eq('id', trip_id);
    }
  }

  res.status(201).json({ ...data, received_at: receivedAt, latency_ms: latencyMs });

  // ── ML Anomaly Detection (background, non-blocking) ───────
  setImmediate(async () => {
    try {
      // Get last 2 readings for delta features
      const { data: recent } = await supabase
        .from('telemetry_logs')
        .select('fuel_level, odometer_km')
        .eq('truck_id', truck_id)
        .order('timestamp', { ascending: false })
        .limit(2);

      const prev       = recent?.length >= 2 ? recent[1] : null;
      const fuelDelta  = prev ? (fuel_level - prev.fuel_level) : 0;
      const odoDelta   = prev ? (odometer_km - prev.odometer_km) : 0;
      const fuelPerKm  = odoDelta > 0 ? (-fuelDelta / odoDelta) : 0;

      // Fuel series for Matrix Profile (last 40)
      const { data: fuelHistory } = await supabase
        .from('telemetry_logs')
        .select('fuel_level')
        .eq('truck_id', truck_id)
        .order('timestamp', { ascending: false })
        .limit(40);

      const fuelSeries = (fuelHistory ?? []).map(r => r.fuel_level ?? 0).reverse();

      const mlRes = await fetch('http://localhost:5001/detect', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fuel_level, speed_kmph: speed,
          fuel_delta: fuelDelta,
          odometer_delta: odoDelta,
          fuel_per_km: fuelPerKm,
          fuel_series: fuelSeries,
        }),
        signal: AbortSignal.timeout(4000),
      });

      if (mlRes.ok) {
        const { is_anomaly, model_source, combined_score, details } = await mlRes.json();

        // Update the telemetry log with anomaly result
        await supabase.from('telemetry_logs').update({
          anomaly_flag:  is_anomaly,
          anomaly_score: combined_score,
          model_source:  model_source,
        }).eq('id', data.id);

        if (is_anomaly) {
          // Insert alert
          await supabase.from('alerts').insert([{
            truck_id, driver_id, trip_id,
            alert_type: 'fuel_anomaly',
            severity:   'high',
            message:    `[${model_source}] ${details} (score: ${combined_score})`,
          }]);

          // Update truck status
          await supabase.from('trucks').update({ status: 'anomaly' }).eq('id', truck_id);

          console.log(`[anomaly] truck=${truck_id} model=${model_source} score=${combined_score}`);
        }
      }
    } catch {
      // ML service offline — telemetry saved, detection skipped
    }
  });
});

// ─────────────────────────────────────────────────────────────
// ALERTS — GET /alerts
// ─────────────────────────────────────────────────────────────
app.get('/alerts', requireDashboard, async (req, res) => {
  let query = supabase
    .from('alerts')
    .select('*')
    .order('timestamp', { ascending: false });

  if (req.query.truck_id)   query = query.eq('truck_id', req.query.truck_id);
  if (req.query.resolved === 'false') query = query.eq('is_resolved', false);
  if (req.query.severity)   query = query.eq('severity', req.query.severity);

  const limit = Math.min(parseInt(req.query.limit ?? '100'), 500);
  query = query.limit(limit);

  const { data, error } = await query;
  if (error) return res.status(400).json({ error: error.message });
  res.json(data);
});

// PATCH /alerts/:id/resolve
app.patch('/alerts/:id/resolve', requireDashboard, async (req, res) => {
  const { data, error } = await supabase
    .from('alerts')
    .update({ is_resolved: true })
    .eq('id', req.params.id)
    .select()
    .single();

  if (error) return res.status(400).json({ error: error.message });
  res.json(data);
});

// ─────────────────────────────────────────────────────────────
// SO2-c: LATENCY STATS — GET /latency/stats
// ─────────────────────────────────────────────────────────────
app.get('/latency/stats', requireDashboard, async (_req, res) => {
  const { data, error } = await supabase
    .from('latency_logs')
    .select('latency_ms, received_at')
    .order('received_at', { ascending: false })
    .limit(500);

  if (error) return res.status(400).json({ error: error.message });

  const values = (data ?? []).map(r => r.latency_ms).filter(v => v != null && v >= 0);
  if (values.length === 0)
    return res.json({ count: 0, avg_ms: null, p95_ms: null, max_ms: null, target_ms: 3000 });

  values.sort((a, b) => a - b);
  const avg = values.reduce((s, v) => s + v, 0) / values.length;
  const p95 = values[Math.floor(values.length * 0.95)];

  res.json({
    count:               values.length,
    avg_ms:              Math.round(avg),
    p95_ms:              p95,
    max_ms:              values[values.length - 1],
    target_ms:           3000,
    within_target_pct:   +(values.filter(v => v <= 3000).length / values.length * 100).toFixed(1),
  });
});

// ─────────────────────────────────────────────────────────────
// SO5: ANALYTICS — GET /analytics?days=7
// ─────────────────────────────────────────────────────────────
app.get('/analytics', requireDashboard, async (req, res) => {
  const days  = Math.min(parseInt(req.query.days ?? '7'), 30);
  const since = new Date(Date.now() - days * 86400000).toISOString();

  const [{ data: trucks }, { data: telemetry }, { data: alertData }] = await Promise.all([
    supabase.from('trucks').select('id, truck_code, plate_number'),
    supabase.from('telemetry_logs')
      .select('truck_id, fuel_level, odometer_km, speed, timestamp')
      .gte('timestamp', since).order('truck_id').order('timestamp'),
    supabase.from('alerts')
      .select('truck_id, alert_type, severity, timestamp')
      .gte('timestamp', since),
  ]);

  const truckMap = Object.fromEntries((trucks ?? []).map(t => [t.id, t]));
  const byTruck  = {};
  for (const row of (telemetry ?? [])) {
    if (!byTruck[row.truck_id]) byTruck[row.truck_id] = [];
    byTruck[row.truck_id].push(row);
  }

  const stats = Object.entries(byTruck).map(([tid, rows]) => {
    rows.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    const odos        = rows.map(r => r.odometer_km).filter(v => v != null);
    const distance    = odos.length >= 2 ? Math.max(...odos) - Math.min(...odos) : 0;
    let fuelConsumed  = 0;
    for (let i = 1; i < rows.length; i++) {
      const d = (rows[i].fuel_level ?? 0) - (rows[i-1].fuel_level ?? 0);
      if (d < 0) fuelConsumed += Math.abs(d);
    }
    const opHours   = rows.length >= 2
      ? (new Date(rows[rows.length-1].timestamp) - new Date(rows[0].timestamp)) / 3600000 : 0;
    const speeds    = rows.map(r => r.speed).filter(v => v != null);
    const avgSpeed  = speeds.length ? speeds.reduce((s,v) => s+v, 0) / speeds.length : 0;
    const vAlerts   = (alertData ?? []).filter(a => a.truck_id === tid);
    const anomalies = vAlerts.filter(a => a.alert_type === 'fuel_anomaly').length;
    const sample    = rows.length > 50 ? rows.filter((_,i) => i % Math.ceil(rows.length/50) === 0) : rows;

    return {
      truck_id:          tid,
      truck_code:        truckMap[tid]?.truck_code ?? tid,
      plate_number:      truckMap[tid]?.plate_number ?? '',
      readings:          rows.length,
      distance_km:       +distance.toFixed(1),
      fuel_consumed_pct: +fuelConsumed.toFixed(2),
      operating_hours:   +opHours.toFixed(2),
      avg_speed_kmph:    +avgSpeed.toFixed(1),
      alert_count:       vAlerts.length,
      anomaly_count:     anomalies,
      fuel_trend:        sample.map(r => ({ t: r.timestamp, v: r.fuel_level })),
    };
  });

  res.json({
    period_days: days,
    since,
    trucks: stats,
    totals: {
      total_distance_km:      +stats.reduce((s,v) => s + v.distance_km, 0).toFixed(1),
      total_fuel_consumed_pct: +stats.reduce((s,v) => s + v.fuel_consumed_pct, 0).toFixed(2),
      total_operating_hours:  +stats.reduce((s,v) => s + v.operating_hours, 0).toFixed(2),
      total_anomalies:        stats.reduce((s,v) => s + v.anomaly_count, 0),
    },
  });
});

// ─────────────────────────────────────────────────────────────
// SETTINGS — head_admin only
// ─────────────────────────────────────────────────────────────

// GET /settings/thresholds
app.get('/settings/thresholds', requireHeadAdmin, async (_req, res) => {
  const { data, error } = await supabase
    .from('settings')
    .select('*')
    .eq('key', 'thresholds')
    .single();

  if (error) {
    // Return defaults if not yet saved
    return res.json({
      rest_hours: 6, rest_distance_km: 300,
      maintenance_km: 5000, overspeed_kmh: 100,
    });
  }
  res.json(data.value);
});

// PUT /settings/thresholds
app.put('/settings/thresholds', requireHeadAdmin, async (req, res) => {
  const { rest_hours, rest_distance_km, maintenance_km, overspeed_kmh } = req.body;

  const { error } = await supabase
    .from('settings')
    .upsert([{ key: 'thresholds', value: { rest_hours, rest_distance_km, maintenance_km, overspeed_kmh } }],
            { onConflict: 'key' });

  if (error) return res.status(400).json({ error: error.message });
  res.json({ saved: true });
});

// GET /settings/users — list all admin-side users
app.get('/settings/users', requireHeadAdmin, async (_req, res) => {
  const { data, error } = await supabase
    .from('users')
    .select('id, full_name, email, role, is_active, created_at')
    .in('role', ['head_admin', 'fleet_manager', 'manager'])
    .order('created_at');

  if (error) return res.status(400).json({ error: error.message });
  res.json(data);
});

// POST /settings/users — add a new admin-side user
app.post('/settings/users', requireHeadAdmin, async (req, res) => {
  const { full_name, email, password, role } = req.body;
  if (!full_name || !email || !password || !role)
    return res.status(400).json({ error: 'full_name, email, password, and role are required' });

  if (!['fleet_manager', 'manager', 'driver'].includes(role))
    return res.status(400).json({ error: 'Invalid role. Allowed: fleet_manager, manager, driver' });

  const password_hash = await bcrypt.hash(password, 10);

  const { data, error } = await supabase
    .from('users')
    .insert([{ full_name, email, password_hash, role, is_active: true }])
    .select('id, full_name, email, role, created_at')
    .single();

  if (error) return res.status(400).json({ error: error.message });
  res.status(201).json(data);
});

// PATCH /settings/users/:id — update user (enable/disable, role change)
app.patch('/settings/users/:id', requireHeadAdmin, async (req, res) => {
  const allowed = ['full_name', 'role', 'is_active'];
  const updates = Object.fromEntries(
    Object.entries(req.body).filter(([k]) => allowed.includes(k))
  );
  if (Object.keys(updates).length === 0)
    return res.status(400).json({ error: 'No valid fields to update' });

  const { data, error } = await supabase
    .from('users')
    .update(updates)
    .eq('id', req.params.id)
    .select('id, full_name, email, role, is_active')
    .single();

  if (error) return res.status(400).json({ error: error.message });
  res.json(data);
});

// DELETE /settings/users/:id
app.delete('/settings/users/:id', requireHeadAdmin, async (req, res) => {
  // Prevent deleting head admin accounts
  const { data: target } = await supabase
    .from('users').select('role').eq('id', req.params.id).single();

  if (target?.role === 'head_admin')
    return res.status(403).json({ error: 'Cannot delete head admin accounts' });

  const { error } = await supabase.from('users').delete().eq('id', req.params.id);
  if (error) return res.status(400).json({ error: error.message });
  res.json({ deleted: true });
});

// POST /trucks — add a new truck (head_admin only)
app.post('/trucks', requireHeadAdmin, async (req, res) => {
  const { truck_code, plate_number, model, notes } = req.body;
  if (!truck_code || !plate_number)
    return res.status(400).json({ error: 'truck_code and plate_number are required' });

  const { data, error } = await supabase
    .from('trucks')
    .insert([{ truck_code, plate_number, model, notes, device_installed: false }])
    .select()
    .single();

  if (error) return res.status(400).json({ error: error.message });
  res.status(201).json(data);
});

// DELETE /trucks/:id (head_admin only)
app.delete('/trucks/:id', requireHeadAdmin, async (req, res) => {
  // Check for active trip first
  const { data: activeTrip } = await supabase
    .from('trip_sessions')
    .select('id')
    .eq('truck_id', req.params.id)
    .eq('trip_status', 'active')
    .limit(1)
    .single();

  if (activeTrip)
    return res.status(409).json({ error: 'Cannot delete truck with an active trip' });

  const { error } = await supabase.from('trucks').delete().eq('id', req.params.id);
  if (error) return res.status(400).json({ error: error.message });
  res.json({ deleted: true });
});

// ─────────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`Fleet API running on http://localhost:${PORT}`);
});
