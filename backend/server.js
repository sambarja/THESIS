const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });
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

async function upsertTripSummary(tripId) {
  // Try the Supabase RPC first
  try {
    const { data, error } = await supabase.rpc('refresh_trip_summary', {
      p_trip_id: tripId,
    });
    if (!error) return data ?? null;
    console.warn('[trip_summary] RPC failed, using direct upsert fallback:', error.message);
  } catch (rpcErr) {
    console.warn('[trip_summary] RPC threw, using direct upsert fallback:', rpcErr.message);
  }

  // ── Direct JS fallback (works even if the RPC is not deployed) ──
  const { data: trip, error: tripErr } = await supabase
    .from('trip_sessions')
    .select('*')
    .eq('id', tripId)
    .single();

  if (tripErr || !trip) throw new Error(`Trip ${tripId} not found for summary upsert`);

  const [truckRes, driverRes, alertRes, logRes] = await Promise.all([
    supabase.from('trucks').select('truck_code, plate_number').eq('id', trip.truck_id).single(),
    supabase.from('users').select('full_name').eq('id', trip.driver_id).single(),
    supabase.from('alerts').select('id', { count: 'exact', head: true }).eq('trip_id', tripId),
    supabase.from('telemetry_logs')
      .select('fuel_level, anomaly_flag, timestamp')
      .eq('trip_id', tripId)
      .order('timestamp', { ascending: true }),
  ]);

  const logs      = logRes.data ?? [];
  const validFuel = logs.filter(l => l.fuel_level != null);
  const avgFuel   = validFuel.length
    ? +(validFuel.reduce((s, l) => s + l.fuel_level, 0) / validFuel.length).toFixed(2)
    : null;

  const { data, error } = await supabase
    .from('trip_summaries')
    .upsert({
      trip_id:               tripId,
      truck_id:              trip.truck_id,
      driver_id:             trip.driver_id,
      trip_status:           trip.trip_status,
      start_time:            trip.start_time,
      end_time:              trip.end_time,
      total_distance_km:     trip.distance_km ?? 0,
      total_operating_hours: trip.operating_hours ?? 0,
      total_alerts:          alertRes.count ?? 0,
      total_anomalies:       logs.filter(l => l.anomaly_flag).length,
      average_fuel_level:    avgFuel,
      start_fuel_level:      validFuel[0]?.fuel_level ?? null,
      final_fuel_level:      validFuel[validFuel.length - 1]?.fuel_level ?? null,
      log_count:             logs.length,
      truck_code:            truckRes.data?.truck_code ?? null,
      plate_number:          truckRes.data?.plate_number ?? null,
      driver_name:           driverRes.data?.full_name ?? null,
      updated_at:            new Date().toISOString(),
    }, { onConflict: 'trip_id' })
    .select()
    .single();

  if (error) throw error;
  return data;
}

async function archiveEndedTripLogs(options = {}) {
  const { data, error } = await supabase.rpc('archive_ended_trip_logs', {
    p_retention_days: Number(options.retentionDays ?? 30),
    p_max_trips: Number(options.maxTrips ?? 50),
    p_dry_run: Boolean(options.dryRun),
  });
  if (error) throw error;
  return data ?? null;
}

// ─────────────────────────────────────────────────────────────
// RBAC CONSTANTS
// ─────────────────────────────────────────────────────────────
const DASHBOARD_ROLES = ['head_admin', 'fleet_manager', 'manager'];

// ─────────────────────────────────────────────────────────────
// THRESHOLD CACHE — refreshed every 60 s to pick up settings changes
// ─────────────────────────────────────────────────────────────
let _thresholdCache = null;
let _thresholdCachedAt = 0;
const THRESHOLD_TTL_MS = 60_000;

async function getThresholds() {
  if (_thresholdCache && Date.now() - _thresholdCachedAt < THRESHOLD_TTL_MS) {
    return _thresholdCache;
  }
  const { data } = await supabase
    .from('settings').select('value').eq('key', 'thresholds').single();
  _thresholdCache = data?.value ?? {
    rest_hours: 6, rest_distance_km: 300, maintenance_km: 5000, overspeed_kmh: 100,
  };
  _thresholdCachedAt = Date.now();
  return _thresholdCache;
}

// Invalidate threshold cache (called after PUT /settings/thresholds)
function invalidateThresholdCache() { _thresholdCachedAt = 0; }

const ALERT_STATUS_PRIORITY = {
  fuel_anomaly: 400,
  rest_alert: 300,
  maintenance: 200,
  low_fuel: 100,
};

const ALERT_META_PATTERN = /\s*\[meta:([^\]]+)\]\s*$/;

function statusFromAlertType(alertType) {
  if (alertType === 'fuel_anomaly') return 'anomaly';
  if (alertType === 'rest_alert') return 'rest_alert';
  if (alertType === 'maintenance') return 'maintenance';
  if (alertType === 'low_fuel') return 'low_fuel';
  return null;
}

function stripAlertMeta(message = '') {
  return String(message ?? '').replace(ALERT_META_PATTERN, '').trim();
}

function parseAlertMeta(message = '') {
  const match = String(message ?? '').match(ALERT_META_PATTERN);
  if (!match) return {};

  return Object.fromEntries(
    match[1]
      .split(';')
      .map(part => part.split('=').map(value => value.trim()))
      .filter(([key, value]) => key && value)
  );
}

function withAlertMeta(message = '', meta = {}) {
  const base = stripAlertMeta(message);
  const merged = {
    ...parseAlertMeta(message),
    ...Object.fromEntries(
      Object.entries(meta).filter(([, value]) => value != null && value !== '')
    ),
  };

  const encoded = Object.entries(merged)
    .map(([key, value]) => `${key}=${String(value).replace(/[;\]]/g, '')}`)
    .join(';');

  return encoded ? `${base} [meta:${encoded}]` : base;
}

function sanitizeAlert(alert) {
  return alert ? { ...alert, message: stripAlertMeta(alert.message) } : alert;
}

function computeLiveOperatingHours(startTime, storedHours = 0) {
  if (!startTime) return +(storedHours ?? 0);
  return +((Date.now() - new Date(startTime).getTime()) / 3_600_000).toFixed(2);
}

async function attachTripStatus(rows = []) {
  const tripIds = [...new Set(rows.map(row => row.trip_id).filter(Boolean))];
  if (tripIds.length === 0) {
    return rows.map(row => ({
      ...row,
      trip_status: row.engine_status === 'on' ? 'active' : 'idle',
    }));
  }

  const { data: trips } = await supabase
    .from('trip_sessions')
    .select('id, trip_status')
    .in('id', tripIds);

  const tripMap = Object.fromEntries((trips ?? []).map(trip => [trip.id, trip.trip_status]));

  return rows.map(row => ({
    ...row,
    trip_status: tripMap[row.trip_id] ?? (row.engine_status === 'on' ? 'active' : 'idle'),
  }));
}

function parseDateStart(value) {
  if (!value) return null;
  const parsed = new Date(`${value}T00:00:00.000Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

function parseDateEnd(value) {
  if (!value) return null;
  const parsed = new Date(`${value}T23:59:59.999Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

function applyTimestampFilters(query, reqQuery, column = 'timestamp') {
  const dateFrom = parseDateStart(reqQuery.date_from);
  const dateTo = parseDateEnd(reqQuery.date_to);
  let nextQuery = query;

  if (reqQuery.truck_id) nextQuery = nextQuery.eq('truck_id', reqQuery.truck_id);
  if (reqQuery.driver_id) nextQuery = nextQuery.eq('driver_id', reqQuery.driver_id);
  if (reqQuery.trip_id) nextQuery = nextQuery.eq('trip_id', reqQuery.trip_id);
  if (dateFrom) nextQuery = nextQuery.gte(column, dateFrom);
  if (dateTo) nextQuery = nextQuery.lte(column, dateTo);

  return nextQuery;
}

async function buildNameMaps(rows = []) {
  const truckIds = [...new Set(rows.map(row => row.truck_id).filter(Boolean))];
  const driverIds = [...new Set(rows.map(row => row.driver_id).filter(Boolean))];

  const [truckRes, driverRes] = await Promise.all([
    truckIds.length
      ? supabase.from('trucks').select('id, truck_code').in('id', truckIds)
      : Promise.resolve({ data: [] }),
    driverIds.length
      ? supabase.from('users').select('id, full_name').in('id', driverIds)
      : Promise.resolve({ data: [] }),
  ]);

  return {
    truckMap: Object.fromEntries((truckRes.data ?? []).map(truck => [truck.id, truck.truck_code])),
    driverMap: Object.fromEntries((driverRes.data ?? []).map(driver => [driver.id, driver.full_name])),
  };
}

function filterLogsByDriver(rows = [], driverSearch = '') {
  if (!driverSearch) return rows;
  const query = driverSearch.toLowerCase();
  return rows.filter(row => (row.driver_name ?? '').toLowerCase().includes(query));
}

async function enrichLiveLogs(rows = []) {
  const withStatuses = await attachTripStatus(rows);
  const { truckMap, driverMap } = await buildNameMaps(withStatuses);
  return withStatuses.map(row => ({
    ...row,
    truck_code: truckMap[row.truck_id] ?? null,
    driver_name: driverMap[row.driver_id] ?? null,
  }));
}

async function enrichArchivedLogs(rows = []) {
  const { truckMap, driverMap } = await buildNameMaps(rows);
  return rows.map(row => ({
    ...row,
    truck_code: row.truck_code ?? truckMap[row.truck_id] ?? null,
    driver_name: row.driver_name ?? driverMap[row.driver_id] ?? null,
    trip_status: row.trip_status ?? 'ended',
  }));
}

async function resolveRestAlertsForTrip(trip_id, resolvedBy) {
  const { data: openAlerts } = await supabase
    .from('alerts')
    .select('id, message')
    .eq('trip_id', trip_id)
    .eq('alert_type', 'rest_alert')
    .eq('is_resolved', false);

  if (!openAlerts?.length) return;

  // Save the current trip distance as the resolution baseline so the next
  // rest alert fires after ANOTHER full threshold interval from this point.
  const { data: tripRow } = await supabase
    .from('trip_sessions')
    .select('distance_km')
    .eq('id', trip_id)
    .single();
  const resolvedAtKm = String((tripRow?.distance_km ?? 0).toFixed(1));

  const resolvedAt = new Date().toISOString();
  await Promise.all(openAlerts.map(alert => supabase
    .from('alerts')
    .update({
      is_resolved: true,
      message: withAlertMeta(alert.message, {
        resolved_by:    resolvedBy,
        resolved_at:    resolvedAt,
        resolved_at_km: resolvedAtKm,
      }),
    })
    .eq('id', alert.id)));
}

async function deriveTruckStatus(truck_id) {
  const [
    { data: activeAlerts },
    { data: trip },
  ] = await Promise.all([
    supabase.from('alerts')
      .select('alert_type, timestamp')
      .eq('truck_id', truck_id)
      .eq('is_resolved', false)
      .order('timestamp', { ascending: false }),
    supabase.from('trip_sessions')
      .select('trip_status')
      .eq('truck_id', truck_id)
      .in('trip_status', ['active', 'paused'])
      .order('start_time', { ascending: false })
      .limit(1)
      .maybeSingle(),
  ]);

  const topAlert = (activeAlerts ?? [])
    .map(a => ({ ...a, priority: ALERT_STATUS_PRIORITY[a.alert_type] ?? 0 }))
    .sort((a, b) => b.priority - a.priority || new Date(b.timestamp) - new Date(a.timestamp))[0];

  const alertStatus = statusFromAlertType(topAlert?.alert_type);
  if (alertStatus) return alertStatus;
  if (trip?.trip_status === 'active' || trip?.trip_status === 'paused') return 'active';
  return 'idle';
}

async function syncTruckStatus(truck_id) {
  const nextStatus = await deriveTruckStatus(truck_id);
  await supabase.from('trucks').update({ status: nextStatus }).eq('id', truck_id);
  return nextStatus;
}

// ─────────────────────────────────────────────────────────────
// OPERATIONAL ALERT CHECKS — rest, maintenance, overspeed
// Called in background after every telemetry insert
// ─────────────────────────────────────────────────────────────
async function checkOperationalAlerts(truck_id, driver_id, trip_id, speed, odometer_km) {
  try {
    const thr = await getThresholds();
    const numericSpeed = Number(speed ?? 0);
    const movingNow = numericSpeed >= 5;

    // ── 1. Overspeed ────────────────────────────────────────
    if (thr.overspeed_kmh && numericSpeed > thr.overspeed_kmh) {
      const cutoff = new Date(Date.now() - 5 * 60_000).toISOString(); // dedup within 5 min
      const { count } = await supabase.from('alerts')
        .select('id', { count: 'exact', head: true })
        .eq('truck_id', truck_id).eq('alert_type', 'overspeed')
        .gte('timestamp', cutoff);
      if (!count) {
        await supabase.from('alerts').insert([{
          truck_id, driver_id, trip_id,
          alert_type: 'overspeed', severity: 'medium',
          message: `Overspeed: ${Math.round(numericSpeed)} km/h (limit ${thr.overspeed_kmh} km/h)`,
        }]);
        console.log(`[alert] overspeed truck=${truck_id} speed=${numericSpeed}`);
      }
    }

    if (!trip_id) return;

    // ── 2. Rest alerts (distance + hours) ──────────────────
    const { data: trip } = await supabase.from('trip_sessions')
      .select('start_time, distance_km, trip_status').eq('id', trip_id).single();

    if (trip) {
      const distKm = trip.distance_km ?? 0;

      // Don't check rest while paused and stationary
      const skipRest = (trip.trip_status === 'paused' && !movingNow) || !movingNow;

      if (!skipRest) {
        // Only act if there's no already-open rest alert
        const { count: openRest } = await supabase.from('alerts')
          .select('id', { count: 'exact', head: true })
          .eq('trip_id', trip_id)
          .eq('alert_type', 'rest_alert')
          .eq('is_resolved', false);

        if (!openRest) {
          // Get the most recent rest alert for this trip (resolved or not)
          const { data: lastAlert } = await supabase.from('alerts')
            .select('timestamp, is_resolved, message')
            .eq('trip_id', trip_id)
            .eq('alert_type', 'rest_alert')
            .order('timestamp', { ascending: false })
            .limit(1)
            .maybeSingle();

          // ── Determine baseline for the next threshold interval ──────────
          // If the last alert was resolved (by admin or driver pause), use
          // resolved_at_km / resolved_at as the reference point so the NEXT
          // alert fires after ONE MORE full interval from that point.
          // If there is no previous alert, baseline = trip start.
          let baselineKm   = 0;
          let baselineTime = new Date(trip.start_time);

          if (lastAlert?.is_resolved) {
            const meta = parseAlertMeta(lastAlert.message);
            const savedKm = parseFloat(meta.resolved_at_km ?? 'NaN');
            if (Number.isFinite(savedKm)) baselineKm = savedKm;
            if (meta.resolved_at) {
              const t = new Date(meta.resolved_at);
              if (!isNaN(t.getTime())) baselineTime = t;
            }
          }

          const distSinceBaseline  = distKm - baselineKm;
          const hoursSinceBaseline = (Date.now() - baselineTime.getTime()) / 3_600_000;

          const needsRest =
            (thr.rest_distance_km > 0 && distSinceBaseline  >= thr.rest_distance_km) ||
            (thr.rest_hours       > 0 && hoursSinceBaseline >= thr.rest_hours);

          // 10-minute dedup guard: avoid spamming if still driving past threshold
          const tenMinAgo      = new Date(Date.now() - 10 * 60_000).toISOString();
          const recentlyAlerted = lastAlert?.timestamp && lastAlert.timestamp >= tenMinAgo;

          if (needsRest && !recentlyAlerted) {
            const reason = distSinceBaseline >= thr.rest_distance_km
              ? `${distKm.toFixed(1)} km driven (every ${thr.rest_distance_km} km)`
              : `${hoursSinceBaseline.toFixed(1)} h driving (every ${thr.rest_hours} h)`;

            await supabase.from('alerts').insert([{
              truck_id, driver_id, trip_id,
              alert_type: 'rest_alert', severity: 'medium',
              message: `Driver rest required — ${reason}`,
            }]);
            await syncTruckStatus(truck_id);
            console.log(
              `[alert] rest_alert truck=${truck_id}`
              + ` distSince=${distSinceBaseline.toFixed(1)}km`
              + ` reason=${reason}`
            );
          }
        }
      }
    }

    // ── 3. Maintenance (trip accumulated distance) ──────────
    if (thr.maintenance_km > 0 && trip_id) {
      const { data: tr } = await supabase.from('trip_sessions')
        .select('distance_km').eq('id', trip_id).single();
      if (tr && (tr.distance_km ?? 0) >= thr.maintenance_km) {
        const { count } = await supabase.from('alerts')
          .select('id', { count: 'exact', head: true })
          .eq('truck_id', truck_id).eq('alert_type', 'maintenance').eq('is_resolved', false);
        if (!count) {
          await supabase.from('alerts').insert([{
            truck_id, driver_id, trip_id,
            alert_type: 'maintenance', severity: 'low',
            message: `Scheduled maintenance due — ${(tr.distance_km ?? 0).toFixed(0)} km accumulated this trip`,
          }]);
          await syncTruckStatus(truck_id);
          console.log(`[alert] maintenance truck=${truck_id}`);
        }
      }
    }
  } catch (err) {
    console.error('[checkOperationalAlerts]', err.message);
  }
}

// ─────────────────────────────────────────────────────────────
// AUTH HELPER — resolves user from Bearer token (user_id)
// ─────────────────────────────────────────────────────────────
async function resolveUser(req) {
  const auth = req.headers['authorization'] || '';
  const userId = auth.startsWith('Bearer ') ? auth.slice(7).trim() : null;
  if (!userId) return null;
  const { data } = await supabase
    .from('users')
    .select('id, full_name, username, role, is_active')
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
  const { username, password } = req.body;
  if (!username || !password)
    return res.status(400).json({ error: 'Username and password are required.' });

  const { data: user, error } = await supabase
    .from('users')
    .select('id, full_name, username, password_hash, role, is_active')
    .eq('username', username.toLowerCase().trim())
    .single();

  // PGRST116 = no row found
  if (error?.code === 'PGRST116' || !user)
    return res.status(404).json({ error: 'No account found in the system.' });

  if (error)
    return res.status(500).json({ error: 'Authentication error.' });

  if (!user.is_active)
    return res.status(403).json({ error: 'This account has been deactivated.' });

  // Drivers are not allowed to access the admin dashboard
  if (user.role === 'driver')
    return res.status(403).json({
      error: 'This account is not authorized to access the dashboard. Use the truck device to log in.',
    });

  const match = await bcrypt.compare(password, user.password_hash);
  if (!match)
    return res.status(401).json({ error: 'Incorrect password.' });

  res.json({
    user_id:   user.id,
    full_name: user.full_name,
    username:  user.username,
    role:      user.role,
  });
});

// ─────────────────────────────────────────────────────────────
// DRIVER DEVICE AUTH — POST /driver/login  (truck-side device only)
// ─────────────────────────────────────────────────────────────
app.post('/driver/login', async (req, res) => {
  const { username, password } = req.body;
  if (!username || !password)
    return res.status(400).json({ error: 'Username and password are required.' });

  const { data: user, error } = await supabase
    .from('users')
    .select('id, full_name, username, password_hash, role, is_active')
    .eq('username', username.toLowerCase().trim())
    .single();

  if (error || !user)
    return res.status(401).json({ error: 'No account found in the system.' });

  if (!user.is_active)
    return res.status(403).json({ error: 'This account has been deactivated.' });

  // Only drivers can use the device login
  if (user.role !== 'driver')
    return res.status(403).json({ error: 'This login is for driver accounts only.' });

  const match = await bcrypt.compare(password, user.password_hash);
  if (!match)
    return res.status(401).json({ error: 'Incorrect password.' });

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
    username:    user.username,
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

    // Active or paused trip
    const { data: trip } = await supabase
      .from('trip_sessions')
      .select('id, start_time, distance_km, operating_hours, driver_id, trip_status')
      .eq('truck_id', truck.id)
      .in('trip_status', ['active', 'paused'])
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

      // Active/paused trip
      trip_id:          trip?.id              ?? null,
      trip_status:      trip?.trip_status     ?? 'idle',
      trip_start_time:  trip?.start_time      ?? null,
      distance_km:      trip?.distance_km      ?? 0,
      operating_hours:  trip
        ? computeLiveOperatingHours(trip.start_time, trip.operating_hours)
        : (trip?.operating_hours ?? 0),
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
    .select('id, full_name, username')
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
    .select('id, trip_id, timestamp, fuel_level, lat, lon, speed, odometer_km, engine_status, anomaly_flag, anomaly_score, model_source')
    .eq('truck_id', req.params.id)
    .order('timestamp', { ascending: false })
    .limit(limit);

  if (error) return res.status(400).json({ error: error.message });
  const withStatuses = await attachTripStatus(data ?? []);
  res.json(withStatuses.reverse()); // return in chronological order
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

// GET /trips/summaries — MUST be defined before /trips/:id to prevent route shadowing
app.get('/trips/summaries', requireDashboard, async (req, res) => {
  const limit = Math.min(parseInt(req.query.limit ?? '200'), 1000);
  const dateFrom = req.query.days
    ? new Date(Date.now() - Math.min(parseInt(req.query.days, 10), 3650) * 86400000).toISOString()
    : parseDateStart(req.query.date_from);
  const dateTo = parseDateEnd(req.query.date_to);

  let query = supabase
    .from('trip_summaries')
    .select('*')
    .order('end_time', { ascending: false, nullsFirst: false })
    .limit(limit);

  if (req.query.truck_id) query = query.eq('truck_id', req.query.truck_id);
  if (req.query.driver_id) query = query.eq('driver_id', req.query.driver_id);
  if (req.query.trip_id) query = query.eq('trip_id', req.query.trip_id);
  if (dateFrom) query = query.gte('start_time', dateFrom);
  if (dateTo) query = query.lte('end_time', dateTo);

  const { data, error } = await query;
  if (error) return res.status(400).json({ error: error.message });

  const rows = data ?? [];
  const totals = rows.reduce((acc, row) => {
    acc.total_distance_km += Number(row.total_distance_km ?? 0);
    acc.total_operating_hours += Number(row.total_operating_hours ?? 0);
    acc.total_alerts += Number(row.total_alerts ?? 0);
    acc.total_anomalies += Number(row.total_anomalies ?? 0);
    if (row.average_fuel_level != null) {
      acc.average_fuel_total += Number(row.average_fuel_level);
      acc.average_fuel_count += 1;
    }
    return acc;
  }, {
    total_distance_km: 0,
    total_operating_hours: 0,
    total_alerts: 0,
    total_anomalies: 0,
    average_fuel_total: 0,
    average_fuel_count: 0,
  });

  res.json({
    items: rows,
    count: rows.length,
    totals: {
      total_distance_km: +totals.total_distance_km.toFixed(1),
      total_operating_hours: +totals.total_operating_hours.toFixed(2),
      total_alerts: totals.total_alerts,
      total_anomalies: totals.total_anomalies,
      average_fuel_level: totals.average_fuel_count
        ? +(totals.average_fuel_total / totals.average_fuel_count).toFixed(2)
        : null,
    },
  });
});

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
    supabase.from('users').select('full_name, username').eq('id', trip.driver_id).single(),
  ]);

  res.json({ ...trip, truck: truck ?? null, driver: driver ?? null });
});

// GET /trips/:id/route — GPS polyline for a trip
app.get('/trips/:id/route', requireDashboard, async (req, res) => {
  const [liveRes, archivedRes] = await Promise.all([
    supabase
      .from('telemetry_logs')
      .select('lat, lon, fuel_level, speed, timestamp')
      .eq('trip_id', req.params.id)
      .not('lat', 'is', null)
      .not('lon', 'is', null)
      .order('timestamp', { ascending: true }),
    supabase
      .from('archived_telemetry_logs')
      .select('lat, lon, fuel_level, speed, timestamp')
      .eq('trip_id', req.params.id)
      .not('lat', 'is', null)
      .not('lon', 'is', null)
      .order('timestamp', { ascending: true }),
  ]);

  if (liveRes.error) return res.status(400).json({ error: liveRes.error.message });
  if (archivedRes.error) return res.status(400).json({ error: archivedRes.error.message });

  const merged = [...(liveRes.data ?? []), ...(archivedRes.data ?? [])]
    .sort((left, right) => new Date(left.timestamp) - new Date(right.timestamp));

  res.json(merged);
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

  await syncTruckStatus(truck_id);

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

  await syncTruckStatus(trip.truck_id);
  try {
    await upsertTripSummary(trip_id);
  } catch (summaryErr) {
    console.error('[trip_summary]', summaryErr.message);
  }

  res.json(data);
});

// POST /trip/pause — driver presses REST button; pauses the active trip
app.post('/trip/pause', async (req, res) => {
  const { trip_id } = req.body;
  if (!trip_id) return res.status(400).json({ error: 'trip_id required' });

  const { data, error } = await supabase
    .from('trip_sessions')
    .update({ trip_status: 'paused' })
    .eq('id', trip_id).eq('trip_status', 'active')
    .select().single();

  if (error || !data) return res.status(400).json({ error: 'Could not pause trip — not found or not active' });

  await resolveRestAlertsForTrip(trip_id, 'driver_pause');

  await syncTruckStatus(data.truck_id);

  console.log(`[trip] paused trip=${trip_id}`);
  res.json(data);
});

// POST /trip/resume — driver resumes after rest
app.post('/trip/resume', async (req, res) => {
  const { trip_id } = req.body;
  if (!trip_id) return res.status(400).json({ error: 'trip_id required' });

  const { data, error } = await supabase
    .from('trip_sessions')
    .update({ trip_status: 'active' })
    .eq('id', trip_id).eq('trip_status', 'paused')
    .select().single();

  if (error || !data) return res.status(400).json({ error: 'Could not resume trip — not found or not paused' });

  await syncTruckStatus(data.truck_id);

  console.log(`[trip] resumed trip=${trip_id}`);
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

      // Skip ML on first reading — no delta features available yet
      if (!prev) return;

      const fuelDelta  = fuel_level - prev.fuel_level;
      const odoDelta   = Math.max(0, (odometer_km ?? 0) - (prev.odometer_km ?? 0));
      const fuelPerKm  = odoDelta > 0 ? (-fuelDelta / odoDelta) : 0;
      const numericSpeed = Number(speed ?? 0);

      // Skip ML when truck is genuinely stationary (idle/startup) — avoids false positives
      // from near-zero odometer delta which produces meaningless fuelPerKm values
      if (!trip_id) return;
      if (engine_status !== 'on') return;
      if (numericSpeed < 5 && odoDelta < 0.05) return;
      if (odoDelta < 0.08 && Math.abs(fuelDelta) < 0.8) return;
      if (fuelDelta > 1.5) return;

      // Skip if trip is paused — driver is intentionally resting
      const { data: currentTrip } = await supabase.from('trip_sessions')
        .select('trip_status').eq('id', trip_id).single();
      if (currentTrip?.trip_status === 'paused' && numericSpeed < 5) return;

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
        const suspiciousContext =
          fuelDelta <= -2.0 ||
          fuelPerKm >= 0.6 ||
          (numericSpeed < 5 && fuelDelta <= -4.0);
        const contextualAnomaly = Boolean(is_anomaly && combined_score > 0.55 && suspiciousContext);

        // Update the telemetry log with anomaly result
        await supabase.from('telemetry_logs').update({
          anomaly_flag:  contextualAnomaly,
          anomaly_score: combined_score,
          model_source:  model_source,
        }).eq('id', data.id);

        if (contextualAnomaly && combined_score > 0.65) {
          // Dedup: don't spam anomaly alerts (1 per 5 min per truck)
          const fiveMinAgo = new Date(Date.now() - 5 * 60_000).toISOString();
          const { count: recentAnomaly } = await supabase.from('alerts')
            .select('id', { count: 'exact', head: true })
            .eq('truck_id', truck_id).eq('alert_type', 'fuel_anomaly')
            .gte('timestamp', fiveMinAgo);

          if (!recentAnomaly) {
          // Insert alert
          await supabase.from('alerts').insert([{
            truck_id, driver_id, trip_id,
            alert_type: 'fuel_anomaly',
            severity:   'high',
            message:    `[${model_source}] ${details} (score: ${combined_score.toFixed(3)})`,
          }]);

          await syncTruckStatus(truck_id);

          console.log(`[anomaly] truck=${truck_id} model=${model_source} score=${combined_score}`);
          } // end dedup check
        }
      }
    } catch {
      // ML service offline — telemetry saved, detection skipped
    }
  });

  // Operational alert checks run independently of ML
  setImmediate(() => checkOperationalAlerts(truck_id, driver_id, trip_id, speed, odometer_km));
});

// ─────────────────────────────────────────────────────────────
async function handleRecentLogs(req, res) {
  const limit = Math.min(parseInt(req.query.limit ?? '200'), 1000);

  let query = applyTimestampFilters(
    supabase
    .from('telemetry_logs')
    .select('*')
    .order('timestamp', { ascending: false })
    .limit(limit),
    req.query
  );

  const { data, error } = await query;
  if (error) return res.status(400).json({ error: error.message });

  const enriched = await enrichLiveLogs(data ?? []);
  res.json(filterLogsByDriver(enriched, req.query.driver_search));
}

// TELEMETRY LOGS — GET /logs and /logs/recent
// ─────────────────────────────────────────────────────────────
app.get('/logs', requireDashboard, handleRecentLogs);
app.get('/logs/recent', requireDashboard, handleRecentLogs);

app.get('/logs/archived', requireDashboard, async (req, res) => {
  const limit = Math.min(parseInt(req.query.limit ?? '200'), 1000);

  let query = applyTimestampFilters(
    supabase
      .from('archived_telemetry_logs')
      .select('*')
      .order('timestamp', { ascending: false })
      .limit(limit),
    req.query
  );

  const { data, error } = await query;
  if (error) return res.status(400).json({ error: error.message });

  const enriched = await enrichArchivedLogs(data ?? []);
  res.json(filterLogsByDriver(enriched, req.query.driver_search));
});

app.post('/maintenance/archive-logs', requireHeadAdmin, async (req, res) => {
  try {
    const result = await archiveEndedTripLogs({
      retentionDays: req.body?.retention_days ?? req.query.retention_days ?? 30,
      maxTrips: req.body?.max_trips ?? req.query.max_trips ?? 50,
      dryRun: req.body?.dry_run === true || req.query.dry_run === 'true',
    });
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
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

  // Attach truck_code to each alert for display purposes
  const truckIds = [...new Set((data ?? []).map(a => a.truck_id).filter(Boolean))];
  const truckMap = {};
  await Promise.all(truckIds.map(async (tid) => {
    const { data: t } = await supabase.from('trucks').select('truck_code').eq('id', tid).single();
    if (t) truckMap[tid] = t.truck_code;
  }));

  res.json((data ?? []).map(a => ({ ...sanitizeAlert(a), truck_code: truckMap[a.truck_id] ?? null })));
});

app.get('/alerts/summary', requireDashboard, async (_req, res) => {
  const { count: unresolved_count, error } = await supabase
    .from('alerts')
    .select('id', { count: 'exact', head: true })
    .eq('is_resolved', false);

  if (error) return res.status(400).json({ error: error.message });
  res.json({ unresolved_count: unresolved_count ?? 0 });
});

// PATCH /alerts/:id/resolve
app.patch('/alerts/:id/resolve', requireDashboard, async (req, res) => {
  const { data: existing, error: fetchErr } = await supabase
    .from('alerts')
    .select('*')
    .eq('id', req.params.id)
    .single();

  if (fetchErr || !existing) return res.status(404).json({ error: 'Alert not found' });

  const updates = { is_resolved: true };
  if (existing.alert_type === 'rest_alert') {
    // Fetch current trip distance so the next rest alert resets from this point
    let resolvedAtKm = null;
    if (existing.trip_id) {
      const { data: tripRow } = await supabase
        .from('trip_sessions')
        .select('distance_km')
        .eq('id', existing.trip_id)
        .single();
      resolvedAtKm = String((tripRow?.distance_km ?? 0).toFixed(1));
    }
    updates.message = withAlertMeta(existing.message, {
      resolved_by:    'admin',
      resolved_at:    new Date().toISOString(),
      ...(resolvedAtKm != null ? { resolved_at_km: resolvedAtKm } : {}),
    });
  }

  const { data, error } = await supabase
    .from('alerts')
    .update(updates)
    .eq('id', req.params.id)
    .select()
    .single();

  if (error) return res.status(400).json({ error: error.message });
  await syncTruckStatus(data.truck_id);
  res.json(sanitizeAlert(data));
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
  invalidateThresholdCache();   // force re-read on next telemetry
  res.json({ saved: true });
});

// GET /settings/users — list ALL users (all roles, for head admin management)
app.get('/settings/users', requireHeadAdmin, async (_req, res) => {
  const { data, error } = await supabase
    .from('users')
    .select('id, full_name, username, role, is_active, created_at')
    .order('role')
    .order('full_name');

  if (error) return res.status(400).json({ error: error.message });
  res.json(data);
});

// POST /settings/users — add a new user (any role)
app.post('/settings/users', requireHeadAdmin, async (req, res) => {
  const { full_name, username, password, role } = req.body;
  if (!full_name || !username || !password || !role)
    return res.status(400).json({ error: 'full_name, username, password, and role are required.' });

  if (!['fleet_manager', 'manager', 'driver'].includes(role))
    return res.status(400).json({ error: 'Invalid role. Allowed: fleet_manager, manager, driver.' });

  const password_hash = await bcrypt.hash(password, 10);

  const { data, error } = await supabase
    .from('users')
    .insert([{ full_name, username: username.toLowerCase().trim(), password_hash, role, is_active: true }])
    .select('id, full_name, username, role, created_at')
    .single();

  if (error) return res.status(400).json({ error: error.message });
  res.status(201).json(data);
});

// PATCH /settings/users/:id — update user (name, username, role, active status)
app.patch('/settings/users/:id', requireHeadAdmin, async (req, res) => {
  const allowed = ['full_name', 'username', 'role', 'is_active'];
  const updates = Object.fromEntries(
    Object.entries(req.body).filter(([k]) => allowed.includes(k))
  );
  if (updates.username) updates.username = updates.username.toLowerCase().trim();
  if (Object.keys(updates).length === 0)
    return res.status(400).json({ error: 'No valid fields to update.' });

  const { data, error } = await supabase
    .from('users')
    .update(updates)
    .eq('id', req.params.id)
    .select('id, full_name, username, role, is_active')
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
