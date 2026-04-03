const BASE_URL = 'http://localhost:5000';

async function apiFetch(path) {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

export async function getVehicles() {
  return apiFetch('/vehicles');
}

export async function getLatestSensor(vehicleId) {
  try {
    return await apiFetch(`/vehicles/${vehicleId}/sensor/latest`);
  } catch {
    return null;
  }
}

export async function getVehicleAlerts(vehicleId) {
  return apiFetch(`/vehicles/${vehicleId}/alerts`);
}

export async function getAllAlerts() {
  return apiFetch('/alerts');
}

export async function getSensorLogs() {
  return apiFetch('/sensor-logs');
}

export async function getVehicleRoute(vehicleId, limit = 200) {
  return apiFetch(`/vehicles/${vehicleId}/route?limit=${limit}`);
}

export async function getAnalytics(days = 7) {
  return apiFetch(`/analytics?days=${days}`);
}

export async function getLatencyStats() {
  return apiFetch('/latency/stats');
}

export async function postTelemetry(vehicleId, payload) {
  const res = await fetch(`${BASE_URL}/telemetry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ vehicle_id: vehicleId, ...payload, sent_at: new Date().toISOString() }),
  });
  if (!res.ok) throw new Error('Failed to post telemetry');
  return res.json();
}

export async function getFleetStatus(opts = {}) {
  const params = new URLSearchParams();
  if (opts.rest_km)  params.set('rest_km',  opts.rest_km);
  if (opts.maint_km) params.set('maint_km', opts.maint_km);
  const qs = params.toString();
  return apiFetch('/fleet/status' + (qs ? `?${qs}` : ''));
}

export async function postSensorData(vehicleId, payload) {
  const res = await fetch(`${BASE_URL}/vehicles/${vehicleId}/sensor`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to post sensor data');
  return res.json();
}
