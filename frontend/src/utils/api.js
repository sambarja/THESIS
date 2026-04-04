/**
 * Thin wrapper around fetch that automatically injects
 * the Authorization: Bearer {user_id} header for every
 * request to the backend.
 *
 * Usage:
 *   import { apiFetch } from '../utils/api';
 *   const data = await apiFetch('/fleet/status');
 */

const API = import.meta.env.VITE_API_URL || 'http://localhost:5000';

function getToken() {
  try {
    const u = JSON.parse(localStorage.getItem('fleet_user'));
    return u?.user_id ?? null;
  } catch {
    return null;
  }
}

export async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers ?? {}),
  };

  const res = await fetch(`${API}${path}`, { ...options, headers });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(body.error || `HTTP ${res.status}`);
  }

  return res.json();
}

// ─────────────────────────────────────────────────────────────
// DATA NORMALIZATION HELPERS
// Maps backend field names → shape all UI components expect
// ─────────────────────────────────────────────────────────────

/**
 * Normalize a truck from /fleet/status to the shape UI components expect.
 * truck.id  = UUID  (used for API calls, React keys, selectedTruckId)
 * truck.code = 'TRK-001'  (for display)
 */
export function normalizeTruck(t) {
  return {
    id:               t.id,
    code:             t.truck_code,
    name:             t.model ? `${t.truck_code} — ${t.model}` : t.truck_code,
    driver:           t.driver_name    ?? 'Unassigned',
    status:           t.status         ?? 'idle',
    fuel:             t.fuel_level     ?? 0,
    speed:            t.speed          ?? 0,
    distance:         t.distance_km    ?? 0,
    operatingHours:   t.operating_hours ?? 0,
    position:         (t.lat != null && t.lon != null) ? [t.lat, t.lon] : [14.5029, 121.0169],
    tripId:           t.trip_id        ?? null,
    tripStatus:       t.trip_status    ?? 'idle',
    tripStartTime:    t.trip_start_time ?? null,
    lastUpdate:       t.last_update    ?? new Date().toISOString(),
    is_online:        t.is_online      ?? false,
    active_alert_count: t.active_alert_count ?? 0,
    plate_number:     t.plate_number   ?? '',
    device_installed: t.device_installed ?? false,
  };
}

/**
 * Normalize an alert from /alerts to the shape UI components expect.
 */
export function normalizeAlert(a) {
  return {
    id:        a.id,
    truckId:   a.truck_id,
    truckName: a.truck_code ?? a.truck_id ?? 'Unknown',
    type:      a.alert_type ?? 'unknown',
    severity:  a.severity   ?? 'low',
    message:   a.message    ?? '',
    timestamp: a.timestamp,
    resolved:  a.is_resolved ?? false,
  };
}

/**
 * Normalize a telemetry log from /logs to the shape UI components expect.
 */
export function normalizeLog(l) {
  return {
    id:          l.id,
    truckId:     l.truck_id,
    truckName:   l.truck_code ?? l.truck_id ?? 'Unknown',
    driverId:    l.driver_id ?? null,
    driverName:  l.driver_name ?? 'Unknown Driver',
    tripId:      l.trip_id ?? null,
    fuel:        l.fuel_level ?? 0,
    latitude:    l.lat ?? 0,
    longitude:   l.lon ?? 0,
    speed:       l.speed ?? 0,
    anomaly:     l.anomaly_flag ?? false,
    tripStatus:  l.trip_status ?? (l.engine_status === 'on' ? 'active' : 'idle'),
    timestamp:   l.timestamp,
    archivedAt:  l.archived_at ?? null,
    source:      l.archived_at ? 'archived' : 'recent',
  };
}

export function normalizeTripSummary(summary) {
  return {
    id: summary.id ?? summary.trip_id,
    tripId: summary.trip_id,
    truckId: summary.truck_id,
    truckCode: summary.truck_code ?? 'Unknown Truck',
    driverId: summary.driver_id,
    driverName: summary.driver_name ?? 'Unknown Driver',
    tripStatus: summary.trip_status ?? 'ended',
    startTime: summary.start_time,
    endTime: summary.end_time,
    totalDistanceKm: summary.total_distance_km ?? 0,
    totalOperatingHours: summary.total_operating_hours ?? 0,
    totalAlerts: summary.total_alerts ?? 0,
    totalAnomalies: summary.total_anomalies ?? 0,
    averageFuelLevel: summary.average_fuel_level,
    finalFuelLevel: summary.final_fuel_level,
    logCount: summary.log_count ?? 0,
    plateNumber: summary.plate_number ?? '',
    createdAt: summary.created_at ?? summary.updated_at ?? null,
  };
}
