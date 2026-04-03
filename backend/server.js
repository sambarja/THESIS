require('dotenv').config();
const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const { createClient } = require('@supabase/supabase-js');
const bcrypt = require('bcryptjs');


const app = express();
app.use(cors());
app.use(bodyParser.json());

// Supabase client
const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_KEY
);

const PORT = process.env.PORT || 5000;

// ----------------------
// Health check endpoint
// ----------------------
app.get('/', (req, res) => {
  res.json({ status: 'ok', service: 'Fleet Monitoring API' });
});

// ----------------------
// User login
// ----------------------
app.post('/login', async (req, res) => {
  const { email, password } = req.body;
  if (!email || !password) return res.status(400).json({ error: 'Email and password required' });

  const { data: users, error } = await supabase
    .from('users')
    .select('*')
    .eq('email', email)
    .single();

  if (error || !users) return res.status(401).json({ error: 'Invalid email or password' });

  const match = await bcrypt.compare(password, users.password_hash);
  if (!match) return res.status(401).json({ error: 'Invalid email or password' });

  res.status(200).json({ user_id: users.id, role: users.role, email: users.email });
});

// ----------------------
// Vehicle registration (only assign to driver)
// ----------------------
app.post('/vehicles', async (req, res) => {
  const { plate_number, user_id } = req.body;

  if (!plate_number || !user_id) {
    return res.status(400).json({ error: 'plate_number and user_id are required' });
  }

  // Ensure the user exists and is a driver
  const { data: user, error: userErr } = await supabase
    .from('users')
    .select('id, role')
    .eq('id', user_id)
    .single();

  if (userErr || !user) return res.status(400).json({ error: 'Invalid user_id' });
  if (user.role !== 'driver') return res.status(403).json({ error: 'Only drivers can be assigned to vehicles' });

  const { data, error } = await supabase
    .from('vehicles')
    .insert([{ plate_number, user_id }])
    .select();

  if (error) return res.status(400).json({ error: error.message });
  res.status(201).json(data[0]);
});

// ----------------------
// Sensor data ingestion
// ----------------------
app.post('/vehicles/:vehicleId/sensor', async (req, res) => {
  const { vehicleId } = req.params;
  const { user_id, fuel_level, speed_kmph, odometer_km, latitude, longitude } = req.body;

  // Check vehicle ownership
  const { data: vehicle, error: vErr } = await supabase
    .from('vehicles')
    .select('user_id')
    .eq('id', vehicleId)
    .single();

  if (vErr || !vehicle) return res.status(404).json({ error: 'Vehicle not found' });
  if (vehicle.user_id !== user_id) return res.status(403).json({ error: 'Only assigned driver can post sensor data' });

  const { data, error } = await supabase
    .from('sensor_data')
    .insert([{
      vehicle_id: vehicleId,
      fuel_level,
      speed_kmph,
      odometer_km,
      latitude,
      longitude
    }])
    .select();

  if (error) return res.status(400).json({ error: error.message });
  res.status(201).json(data[0]);

  // ── SO4: ML anomaly detection (background, non-blocking) ──────────────────
  setImmediate(async () => {
    try {
      // Fetch the two most recent readings to compute delta features
      const { data: recent } = await supabase
        .from('sensor_data')
        .select('fuel_level, odometer_km')
        .eq('vehicle_id', vehicleId)
        .order('created_at', { ascending: false })
        .limit(2);

      const prev         = recent && recent.length >= 2 ? recent[1] : null;
      const fuelDelta    = prev ? ((fuel_level ?? 0) - (prev.fuel_level ?? 0)) : 0;
      const odoDelta     = prev ? ((odometer_km ?? 0) - (prev.odometer_km ?? 0)) : 0;
      const fuelPerKm    = odoDelta > 0 ? (-fuelDelta / odoDelta) : 0;  // positive = consumed

      // Fetch last 40 fuel readings for Matrix Profile window
      const { data: fuelHistory } = await supabase
        .from('sensor_data')
        .select('fuel_level')
        .eq('vehicle_id', vehicleId)
        .order('created_at', { ascending: false })
        .limit(40);

      const fuelSeries = fuelHistory
        ? fuelHistory.map(r => r.fuel_level ?? 0).reverse()
        : [];

      const mlRes = await fetch('http://localhost:5001/detect', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fuel_level:      fuel_level     ?? 0,
          speed_kmph:      speed_kmph     ?? 0,
          fuel_delta:      fuelDelta,
          odometer_delta:  odoDelta,
          fuel_per_km:     fuelPerKm,
          fuel_series:     fuelSeries,   // enables Matrix Profile
        }),
        signal: AbortSignal.timeout(4000),
      });

      if (mlRes.ok) {
        const mlData = await mlRes.json();
        const { is_anomaly, model_source, combined_score, details } = mlData;
        if (is_anomaly) {
          await supabase.from('alerts').insert([{
            vehicle_id: vehicleId,
            type:       'fuel_anomaly',
            severity:   'high',
            details:    `[${model_source}] ${details}`,
          }]);
          console.log(`[anomaly] Alert for vehicle ${vehicleId} model=${model_source} score=${combined_score}`);
        }
      }
    } catch {
      // Anomaly service offline — sensor data saved, detection skipped
    }
  });
});

// ----------------------
// Alerts creation (driver or admin)
// ----------------------
app.post('/vehicles/:vehicleId/alerts', async (req, res) => {
  const { vehicleId } = req.params;
  const { user_id, type, severity, details } = req.body;

  if (!type || !severity || !details) {
    return res.status(400).json({ error: 'type, severity, and details are required' });
  }

  // Check if user can post alert (driver assigned or admin)
  const { data: user, error: userErr } = await supabase
    .from('users')
    .select('role')
    .eq('id', user_id)
    .single();
  if (userErr || !user) return res.status(404).json({ error: 'User not found' });

  const { data: vehicle, error: vehicleErr } = await supabase
    .from('vehicles')
    .select('user_id')
    .eq('id', vehicleId)
    .single();
  if (vehicleErr || !vehicle) return res.status(404).json({ error: 'Vehicle not found' });

  if (user.role !== 'admin' && vehicle.user_id !== user_id) {
    return res.status(403).json({ error: 'Only assigned driver or admin can create alerts' });
  }

  const { data, error } = await supabase
    .from('alerts')
    .insert([{
      vehicle_id: vehicleId,
      type,
      severity,
      details
    }])
    .select();

  if (error) return res.status(400).json({ error: error.message });
  res.status(201).json(data[0]);
});

// ----------------------
// Fetch vehicles
// ----------------------
app.get('/vehicles', async (req, res) => {
  const { data, error } = await supabase.from('vehicles').select();
  if (error) return res.status(400).json({ error: error.message });
  res.json(data);
});

// ----------------------
// Fetch alerts for a vehicle
// ----------------------
app.get('/vehicles/:vehicleId/alerts', async (req, res) => {
  const { vehicleId } = req.params;
  const { data, error } = await supabase.from('alerts').select().eq('vehicle_id', vehicleId);
  if (error) return res.status(400).json({ error: error.message });
  res.json(data);
});

// ----------------------
// Get all sensor data for a vehicle
// ----------------------
app.get('/vehicles/:vehicleId/sensor', async (req, res) => {
  const { vehicleId } = req.params;
  const { data, error } = await supabase
    .from('sensor_data')
    .select('*')
    .eq('vehicle_id', vehicleId)
    .order('created_at', { ascending: true });
  if (error) return res.status(400).json({ error: error.message });
  res.status(200).json(data);
});

// ----------------------
// Get latest sensor reading for a vehicle
// ----------------------
app.get('/vehicles/:vehicleId/sensor/latest', async (req, res) => {
  const { vehicleId } = req.params;
  const { data, error } = await supabase
    .from('sensor_data')
    .select('*')
    .eq('vehicle_id', vehicleId)
    .order('created_at', { ascending: false })
    .limit(1)
    .single();
  if (error) return res.status(404).json({ error: 'No sensor data found' });
  res.json(data);
});

// ----------------------
// Get all alerts across all vehicles
// ----------------------
app.get('/alerts', async (req, res) => {
  const { data, error } = await supabase
    .from('alerts')
    .select('*, vehicles(plate_number)')
    .order('created_at', { ascending: false });
  if (error) return res.status(400).json({ error: error.message });
  res.json(data);
});

// ----------------------
// Get all sensor logs (paginated, latest first)
// ----------------------
app.get('/sensor-logs', async (req, res) => {
  const { data, error } = await supabase
    .from('sensor_data')
    .select('*, vehicles(plate_number)')
    .order('created_at', { ascending: false })
    .limit(100);
  if (error) return res.status(400).json({ error: error.message });
  res.json(data);
});

// ----------------------
// SO2-c: Telemetry ingestion with latency logging
// ----------------------
app.post('/telemetry', async (req, res) => {
  // Unified ingestion endpoint — records sent_at from client and received_at server-side
  const receivedAt = new Date().toISOString();
  const { vehicle_id, fuel_level, speed_kmph, odometer_km,
          latitude, longitude, sent_at } = req.body;

  if (!vehicle_id) return res.status(400).json({ error: 'vehicle_id required' });

  const latencyMs = sent_at
    ? Date.now() - new Date(sent_at).getTime()
    : null;

  const { data, error } = await supabase
    .from('sensor_data')
    .insert([{ vehicle_id, fuel_level, speed_kmph, odometer_km,
               latitude, longitude }])
    .select();

  if (error) return res.status(400).json({ error: error.message });

  // Log latency record
  await supabase.from('latency_logs').insert([{
    vehicle_id,
    sent_at:     sent_at ?? null,
    received_at: receivedAt,
    latency_ms:  latencyMs,
  }]).catch(() => {});   // ignore if table doesn't exist yet

  res.status(201).json({
    ...data[0],
    received_at: receivedAt,
    latency_ms:  latencyMs,
  });
});

// ----------------------
// SO2-c: Latency stats
// ----------------------
app.get('/latency/stats', async (req, res) => {
  const { data, error } = await supabase
    .from('latency_logs')
    .select('latency_ms, received_at')
    .order('received_at', { ascending: false })
    .limit(500);

  if (error) return res.status(400).json({ error: error.message });

  const values = (data || [])
    .map(r => r.latency_ms)
    .filter(v => v !== null && v >= 0);

  if (values.length === 0)
    return res.json({ count: 0, avg_ms: null, p95_ms: null, max_ms: null });

  values.sort((a, b) => a - b);
  const avg  = values.reduce((s, v) => s + v, 0) / values.length;
  const p95  = values[Math.floor(values.length * 0.95)];
  const max  = values[values.length - 1];

  res.json({
    count:   values.length,
    avg_ms:  Math.round(avg),
    p95_ms:  p95,
    max_ms:  max,
    target_ms: 3000,
    within_target_pct: +(values.filter(v => v <= 3000).length / values.length * 100).toFixed(1),
  });
});

// ----------------------
// SO3-a: Route history for a vehicle (GPS polyline)
// ----------------------
app.get('/vehicles/:vehicleId/route', async (req, res) => {
  const { vehicleId } = req.params;
  const limit = Math.min(parseInt(req.query.limit ?? '200'), 500);

  const { data, error } = await supabase
    .from('sensor_data')
    .select('latitude, longitude, fuel_level, speed_kmph, odometer_km, created_at')
    .eq('vehicle_id', vehicleId)
    .not('latitude',  'is', null)
    .not('longitude', 'is', null)
    .order('created_at', { ascending: false })
    .limit(limit);

  if (error) return res.status(400).json({ error: error.message });
  res.json((data || []).reverse());   // chronological order
});

// ----------------------
// SO3-e / SO5-a: Fleet analytics
// ----------------------
app.get('/analytics', async (req, res) => {
  const days    = Math.min(parseInt(req.query.days ?? '7'), 30);
  const since   = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();

  const [{ data: vehicles }, { data: sensorData }, { data: alertData }] =
    await Promise.all([
      supabase.from('vehicles').select('id, plate_number'),
      supabase.from('sensor_data')
        .select('vehicle_id, fuel_level, odometer_km, speed_kmph, created_at')
        .gte('created_at', since)
        .order('vehicle_id')
        .order('created_at'),
      supabase.from('alerts')
        .select('vehicle_id, type, severity, created_at')
        .gte('created_at', since),
    ]);

  const vehicleMap = Object.fromEntries(
    (vehicles || []).map(v => [v.id, v.plate_number])
  );

  // Group sensor data by vehicle
  const byVehicle = {};
  for (const row of (sensorData || [])) {
    if (!byVehicle[row.vehicle_id]) byVehicle[row.vehicle_id] = [];
    byVehicle[row.vehicle_id].push(row);
  }

  const stats = Object.entries(byVehicle).map(([vid, rows]) => {
    rows.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

    // Distance: max odometer - min odometer
    const odos       = rows.map(r => r.odometer_km).filter(v => v != null);
    const distance   = odos.length >= 2
      ? Math.max(...odos) - Math.min(...odos)
      : 0;

    // Fuel consumed: sum of negative deltas
    let fuelConsumed = 0;
    for (let i = 1; i < rows.length; i++) {
      const d = (rows[i].fuel_level ?? 0) - (rows[i-1].fuel_level ?? 0);
      if (d < 0) fuelConsumed += Math.abs(d);
    }

    // Operating hours: span from first to last reading
    const operatingHours = rows.length >= 2
      ? (new Date(rows[rows.length-1].created_at) - new Date(rows[0].created_at))
        / 3600000
      : 0;

    // Avg speed
    const speeds   = rows.map(r => r.speed_kmph).filter(v => v != null);
    const avgSpeed = speeds.length
      ? speeds.reduce((s, v) => s + v, 0) / speeds.length
      : 0;

    // Alerts
    const vAlerts  = (alertData || []).filter(a => a.vehicle_id === vid);
    const anomalies= vAlerts.filter(a => a.type === 'fuel_anomaly').length;

    // Fuel trend (sampled — last 50 points)
    const sample   = rows.length > 50
      ? rows.filter((_, i) => i % Math.ceil(rows.length / 50) === 0)
      : rows;
    const fuelTrend = sample.map(r => ({
      t: r.created_at,
      v: r.fuel_level,
    }));

    return {
      vehicle_id:       vid,
      plate_number:     vehicleMap[vid] ?? vid,
      readings:         rows.length,
      distance_km:      +distance.toFixed(1),
      fuel_consumed_pct: +fuelConsumed.toFixed(2),
      operating_hours:  +operatingHours.toFixed(2),
      avg_speed_kmph:   +avgSpeed.toFixed(1),
      alert_count:      vAlerts.length,
      anomaly_count:    anomalies,
      fuel_trend:       fuelTrend,
    };
  });

  res.json({
    period_days: days,
    since,
    vehicles:    stats,
    totals: {
      total_distance_km:    +stats.reduce((s, v) => s + v.distance_km, 0).toFixed(1),
      total_fuel_consumed:  +stats.reduce((s, v) => s + v.fuel_consumed_pct, 0).toFixed(2),
      total_operating_hours: +stats.reduce((s, v) => s + v.operating_hours, 0).toFixed(2),
      total_anomalies:       stats.reduce((s, v) => s + v.anomaly_count, 0),
    },
  });
});

// ----------------------
// Fleet status — SO5 compliance (rest + maintenance + anomaly counts)
// ----------------------
app.get('/fleet/status', async (req, res) => {
  const REST_KM    = Number(req.query.rest_km)  || 300;
  const MAINT_KM   = Number(req.query.maint_km) || 5000;
  const ONLINE_MS  = 5 * 60 * 1000; // 5 min
  const ALERT_WINDOW_MS = 24 * 60 * 60 * 1000; // 24 h

  const { data: vehicles, error: vErr } = await supabase.from('vehicles').select('*');
  if (vErr) return res.status(400).json({ error: vErr.message });

  const since24h = new Date(Date.now() - ALERT_WINDOW_MS).toISOString();

  const statuses = await Promise.all(vehicles.map(async (vehicle) => {
    const [sensorRes, alertsRes] = await Promise.all([
      supabase.from('sensor_data').select('*')
        .eq('vehicle_id', vehicle.id)
        .order('created_at', { ascending: false })
        .limit(1)
        .single(),
      supabase.from('alerts').select('*')
        .eq('vehicle_id', vehicle.id)
        .gte('created_at', since24h),
    ]);

    const sensor  = sensorRes.data  ?? null;
    const alerts  = alertsRes.data  ?? [];
    const odometer = Number(sensor?.odometer_km ?? 0);

    const kmSinceRest  = odometer % REST_KM;
    const kmSinceMaint = odometer % MAINT_KM;
    const isOnline     = sensor?.created_at
      ? (Date.now() - new Date(sensor.created_at).getTime()) < ONLINE_MS
      : false;

    const fuelAnomalies = alerts.filter(a => {
      const t = (a.type ?? '').toLowerCase();
      return t.includes('fuel') || t.includes('anomal');
    }).length;

    return {
      vehicle_id:   vehicle.id,
      plate_number: vehicle.plate_number,
      is_online:    isOnline,
      fuel_level:   sensor?.fuel_level   ?? null,
      speed_kmph:   sensor?.speed_kmph   ?? null,
      odometer_km:  odometer,
      latitude:     sensor?.latitude     ?? null,
      longitude:    sensor?.longitude    ?? null,
      last_updated: sensor?.created_at   ?? null,

      // SO5 — driver rest (300 km)
      km_since_rest:      kmSinceRest,
      km_to_rest:         REST_KM - kmSinceRest,
      rest_progress_pct:  Math.min(100, (kmSinceRest / REST_KM) * 100),
      rest_needed:        kmSinceRest >= REST_KM * 0.9,

      // SO5 — oil maintenance (5 000 km)
      km_since_maintenance:      kmSinceMaint,
      km_to_maintenance:         MAINT_KM - kmSinceMaint,
      maintenance_progress_pct:  Math.min(100, (kmSinceMaint / MAINT_KM) * 100),
      maintenance_due:           kmSinceMaint >= MAINT_KM * 0.9,

      // SO5-a — operating hours (time since first reading today)
      operating_hours: (() => {
        if (!sensor?.created_at) return 0;
        const todayStart = new Date();
        todayStart.setHours(0, 0, 0, 0);
        const lastSeen = new Date(sensor.created_at);
        return lastSeen > todayStart
          ? +((lastSeen - todayStart) / 3600000).toFixed(2)
          : 0;
      })(),

      // Anomaly / alert counts (last 24 h)
      recent_fuel_anomalies: fuelAnomalies,
      recent_alert_count:    alerts.length,
    };
  }));

  res.json(statuses);
});

// ----------------------
// Start server
// ----------------------
app.listen(PORT, () => {
  console.log(`Backend running on http://localhost:${PORT}`);
});
