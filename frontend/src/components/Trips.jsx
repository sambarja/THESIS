import { useState, useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, Marker, Polyline, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import {
  ArrowLeft, RefreshCw, AlertTriangle, Search,
  MapPin, ChevronRight, Route,
} from 'lucide-react';
import { format, isValid, differenceInMinutes } from 'date-fns';
import { useApi } from '../hooks/useApi';
import { apiFetch, normalizeTruck, normalizeTripSummary } from '../utils/api';

// ── Fix Leaflet default icon broken with Vite (same guard as FleetMap) ────────
if (!L.Icon.Default.__fixed) {
  delete L.Icon.Default.prototype._getIconUrl;
  L.Icon.Default.mergeOptions({
    iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
    iconUrl:       'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
    shadowUrl:     'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  });
  L.Icon.Default.__fixed = true;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function ensureArray(v) { return Array.isArray(v) ? v : []; }
function safeNum(v, fb = 0) { const n = Number(v); return Number.isFinite(n) ? n : fb; }

function fmtDate(v, fb = '--') {
  if (!v) return fb;
  const d = new Date(v);
  return isValid(d) ? format(d, 'MMM d, yyyy h:mm a') : fb;
}

function fmtDuration(start, end) {
  if (!start || !end) return '--';
  const s = new Date(start), e = new Date(end);
  if (!isValid(s) || !isValid(e)) return '--';
  const mins = differenceInMinutes(e, s);
  if (mins < 0) return '--';
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function buildSummaryPath(days, truckId) {
  const p = new URLSearchParams({ days: String(days), limit: '200' });
  if (truckId && truckId !== 'all') p.set('truck_id', truckId);
  return `/trips/summaries?${p.toString()}`;
}

// ── Leaflet custom icons ───────────────────────────────────────────────────────
function createStartIcon() {
  return L.divIcon({
    html: `<div style="
      width:34px;height:34px;background:#16a34a;
      border-radius:50%;border:3px solid white;
      box-shadow:0 2px 8px rgba(0,0,0,0.35);
      display:flex;align-items:center;justify-content:center;
      font-size:13px;font-weight:700;color:white;letter-spacing:-0.5px;
    ">S</div>`,
    className: '',
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    popupAnchor: [0, -20],
  });
}

function createEndIcon() {
  return L.divIcon({
    html: `<div style="
      width:34px;height:34px;background:#dc2626;
      border-radius:50%;border:3px solid white;
      box-shadow:0 2px 8px rgba(0,0,0,0.35);
      display:flex;align-items:center;justify-content:center;
      font-size:13px;font-weight:700;color:white;letter-spacing:-0.5px;
    ">E</div>`,
    className: '',
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    popupAnchor: [0, -20],
  });
}

// ── FitRoute: auto-zoom map to polyline bounds ────────────────────────────────
function FitRoute({ route }) {
  const map = useMap();
  useEffect(() => {
    if (route.length > 1) {
      map.fitBounds(L.latLngBounds(route), { padding: [48, 48], maxZoom: 16 });
    } else if (route.length === 1) {
      map.setView(route[0], 14);
    }
  }, [route, map]);
  return null;
}

// ── TripRouteMap ──────────────────────────────────────────────────────────────
function TripRouteMap({ route }) {
  const center = route.length > 0 ? route[0] : [14.5995, 121.0000];
  const startPt = route.length > 0 ? route[0] : null;
  const endPt   = route.length > 1 ? route[route.length - 1] : null;

  return (
    <MapContainer center={center} zoom={13} className="w-full h-full" style={{ minHeight: '100%' }}>
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution="© OpenStreetMap contributors"
        maxZoom={19}
      />
      <FitRoute route={route} />

      {route.length > 1 && (
        <>
          {/* White halo for contrast on light tiles */}
          <Polyline positions={route} pathOptions={{ color: '#ffffff', weight: 7, opacity: 0.5 }} />
          {/* Main route line */}
          <Polyline positions={route} pathOptions={{ color: '#3b82f6', weight: 4, opacity: 0.9 }} />
        </>
      )}

      {startPt && (
        <Marker position={startPt} icon={createStartIcon()}>
          <Popup>
            <div style={{ fontWeight: 600, fontSize: 13 }}>Trip Start</div>
            <div style={{ fontSize: 11, color: '#64748b' }}>
              {startPt[0].toFixed(5)}, {startPt[1].toFixed(5)}
            </div>
          </Popup>
        </Marker>
      )}

      {endPt && (
        <Marker position={endPt} icon={createEndIcon()}>
          <Popup>
            <div style={{ fontWeight: 600, fontSize: 13 }}>Trip End</div>
            <div style={{ fontSize: 11, color: '#64748b' }}>
              {endPt[0].toFixed(5)}, {endPt[1].toFixed(5)}
            </div>
          </Popup>
        </Marker>
      )}
    </MapContainer>
  );
}

// ── Detail sub-components ─────────────────────────────────────────────────────
function StatCard({ label, value, colorClass }) {
  return (
    <div className={`bg-gradient-to-br ${colorClass} rounded-xl p-4 text-white`}>
      <p className="text-2xl font-bold mb-1">{value}</p>
      <p className="text-xs opacity-90">{label}</p>
    </div>
  );
}

function DetailField({ label, value }) {
  return (
    <div>
      <dt className="text-xs text-slate-500 uppercase tracking-wide">{label}</dt>
      <dd className="font-medium text-slate-900 mt-0.5 break-all">{value}</dd>
    </div>
  );
}

// ── Trip Detail View ──────────────────────────────────────────────────────────
function TripDetail({ trip, route, routeLoading, onBack }) {
  const avgFuel = trip.averageFuelLevel != null && Number.isFinite(safeNum(trip.averageFuelLevel))
    ? `${Math.round(safeNum(trip.averageFuelLevel))}%`
    : '--';
  const finalFuel = trip.finalFuelLevel != null && Number.isFinite(safeNum(trip.finalFuelLevel))
    ? `${Math.round(safeNum(trip.finalFuelLevel))}%`
    : '--';

  return (
    <div className="p-3 sm:p-4 lg:p-6 max-w-7xl mx-auto">
      {/* Back */}
      <button
        onClick={onBack}
        className="flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-800 mb-5 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Trips
      </button>

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl sm:text-2xl font-semibold text-slate-900 mb-1">
          Trip — {trip.truckCode}
        </h1>
        <p className="text-sm text-slate-500">
          {trip.driverName} &nbsp;·&nbsp; {fmtDate(trip.startTime)} → {fmtDate(trip.endTime, 'In progress')}
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <StatCard label="Distance" value={`${safeNum(trip.totalDistanceKm)} km`} colorClass="from-blue-500 to-blue-600" />
        <StatCard label="Duration"  value={fmtDuration(trip.startTime, trip.endTime)} colorClass="from-emerald-500 to-emerald-600" />
        <StatCard label="Alerts"    value={safeNum(trip.totalAlerts)}    colorClass="from-amber-500 to-amber-600" />
        <StatCard label="Anomalies" value={safeNum(trip.totalAnomalies)} colorClass="from-red-500 to-red-600" />
      </div>

      {/* Route map */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden mb-4">
        <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2">
          <MapPin className="w-4 h-4 text-slate-500" />
          <span className="text-sm font-medium text-slate-900">Trip Route</span>
          <div className="ml-auto flex items-center gap-3 text-xs text-slate-500">
            <span className="flex items-center gap-1">
              <span className="inline-block w-3 h-3 rounded-full bg-green-600 border-2 border-white shadow" />
              Start
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block w-3 h-3 rounded-full bg-red-600 border-2 border-white shadow" />
              End
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block w-8 h-1 rounded bg-blue-500" />
              Route
            </span>
          </div>
        </div>
        <div className="h-96">
          {routeLoading ? (
            <div className="h-full flex items-center justify-center text-slate-400 text-sm gap-2">
              <RefreshCw className="w-5 h-5 animate-spin" />
              Loading route...
            </div>
          ) : route && route.length > 0 ? (
            <TripRouteMap route={route} />
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-slate-400 text-sm gap-2">
              <Route className="w-8 h-8 opacity-30" />
              No route data available for this trip.
            </div>
          )}
        </div>
      </div>

      {/* Detail fields */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 sm:p-5">
        <h3 className="text-sm font-semibold text-slate-900 mb-4">Trip Details</h3>
        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-8 gap-y-4 text-sm">
          <DetailField label="Trip ID"      value={trip.tripId || '--'} />
          <DetailField label="Truck"        value={trip.truckCode || '--'} />
          <DetailField label="Plate"        value={trip.plateNumber || '--'} />
          <DetailField label="Driver"       value={trip.driverName || '--'} />
          <DetailField label="Start Time"   value={fmtDate(trip.startTime)} />
          <DetailField label="End Time"     value={fmtDate(trip.endTime, 'In progress')} />
          <DetailField label="Op. Hours"    value={`${safeNum(trip.totalOperatingHours)} h`} />
          <DetailField label="Avg Fuel"     value={avgFuel} />
          <DetailField label="Final Fuel"   value={finalFuel} />
          <DetailField label="Log Count"    value={safeNum(trip.logCount)} />
          <DetailField label="Status"       value={trip.tripStatus || '--'} />
        </dl>
      </div>
    </div>
  );
}

// ── Main Trips Page ───────────────────────────────────────────────────────────
export default function Trips() {
  const [days, setDays]               = useState(30);
  const [truckId, setTruckId]         = useState('all');
  const [driverSearch, setDriverSearch] = useState('');
  const [selectedTrip, setSelectedTrip] = useState(null);
  const [tripRoute, setTripRoute]     = useState(null);
  const [routeLoading, setRouteLoading] = useState(false);

  // Trip summaries — poll every 30 s so newly-completed trips appear automatically
  const summariesApi = useApi(buildSummaryPath(days, truckId), {
    transform: payload => {
      const p = payload && typeof payload === 'object' ? payload : {};
      return ensureArray(p.items).map(normalizeTripSummary);
    },
    pollInterval: 30_000,
  });

  // Fleet (for truck filter dropdown)
  const fleetApi = useApi('/fleet/status', {
    transform: rows => ensureArray(rows).map(normalizeTruck),
  });

  const summaries = ensureArray(summariesApi.data);
  const fleet     = ensureArray(fleetApi.data);
  const loading   = summariesApi.loading || fleetApi.loading;

  const truckOptions = useMemo(() => (
    [...fleet]
      .sort((a, b) => String(a.code ?? '').localeCompare(String(b.code ?? '')))
      .map(t => ({ id: t.id, label: t.code ?? 'Unknown' }))
  ), [fleet]);

  // Client-side driver filter
  const filtered = useMemo(() => {
    if (!driverSearch.trim()) return summaries;
    const q = driverSearch.toLowerCase();
    return summaries.filter(s => (s.driverName ?? '').toLowerCase().includes(q));
  }, [summaries, driverSearch]);

  // Fetch route when trip is selected
  useEffect(() => {
    if (!selectedTrip) { setTripRoute(null); return; }
    setRouteLoading(true);
    setTripRoute(null);
    apiFetch(`/trips/${selectedTrip.tripId}/route`)
      .then(pts => {
        const latLngs = ensureArray(pts)
          .filter(p => p.lat != null && p.lon != null)
          .map(p => [p.lat, p.lon]);
        setTripRoute(latLngs);
      })
      .catch(() => setTripRoute([]))
      .finally(() => setRouteLoading(false));
  }, [selectedTrip]);

  const handleRefresh = () => {
    summariesApi.refetch?.();
    fleetApi.refetch?.();
  };

  // ── Detail view ──────────────────────────────────────────────────────────
  if (selectedTrip) {
    return (
      <TripDetail
        trip={selectedTrip}
        route={tripRoute}
        routeLoading={routeLoading}
        onBack={() => setSelectedTrip(null)}
      />
    );
  }

  // ── List view ─────────────────────────────────────────────────────────────
  return (
    <div className="p-3 sm:p-4 lg:p-6 max-w-7xl mx-auto">

      {/* Header */}
      <div className="mb-6 flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold text-slate-900 mb-1">Trip History</h1>
          <p className="text-sm text-slate-500">
            Browse completed trips, inspect routes, and review per-trip data.
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={loading}
          className="p-2 rounded-lg hover:bg-slate-100 transition-colors disabled:opacity-50"
          title="Refresh"
        >
          <RefreshCw className={`w-4 h-4 text-slate-500 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-4">
        <select
          value={days}
          onChange={e => setDays(Number(e.target.value))}
          className="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
        >
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
        </select>

        <select
          value={truckId}
          onChange={e => setTruckId(e.target.value)}
          className="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
        >
          <option value="all">All Trucks</option>
          {truckOptions.map(opt => (
            <option key={opt.id} value={opt.id}>{opt.label}</option>
          ))}
        </select>

        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-slate-400 pointer-events-none" />
          <input
            type="text"
            placeholder="Filter by driver…"
            value={driverSearch}
            onChange={e => setDriverSearch(e.target.value)}
            className="pl-8 pr-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 w-48 bg-white"
          />
        </div>
      </div>

      {/* Error */}
      {summariesApi.error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          {summariesApi.error}
        </div>
      )}

      {/* Result count */}
      {!loading && (
        <p className="text-xs text-slate-500 mb-3">
          {filtered.length === 0
            ? 'No trips found'
            : `${filtered.length} trip${filtered.length !== 1 ? 's' : ''} found`}
        </p>
      )}

      {/* Trip table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                {['Truck', 'Driver', 'Start', 'End', 'Duration', 'Distance', 'Avg Fuel', 'Alerts', 'Anomalies', ''].map(h => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={10} className="px-4 py-12 text-center text-slate-400">
                    <RefreshCw className="w-6 h-6 mx-auto mb-2 animate-spin opacity-40" />
                    Loading trips…
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={10} className="px-4 py-12 text-center">
                    <div className="flex flex-col items-center gap-2 text-slate-400">
                      <Route className="w-8 h-8 opacity-30" />
                      <span className="text-sm">
                        {summaries.length === 0
                          ? 'No completed trips found for this period.'
                          : 'No trips match the current driver filter.'}
                      </span>
                    </div>
                  </td>
                </tr>
              ) : (
                filtered.map(trip => {
                  const alerts    = safeNum(trip.totalAlerts);
                  const anomalies = safeNum(trip.totalAnomalies);
                  const avgFuel   = trip.averageFuelLevel != null && Number.isFinite(safeNum(trip.averageFuelLevel))
                    ? `${Math.round(safeNum(trip.averageFuelLevel))}%`
                    : '--';

                  return (
                    <tr
                      key={trip.id ?? trip.tripId}
                      className="hover:bg-blue-50 cursor-pointer transition-colors"
                      onClick={() => setSelectedTrip(trip)}
                    >
                      <td className="px-4 py-3 whitespace-nowrap font-medium text-slate-900">
                        {trip.truckCode}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-slate-700">{trip.driverName}</td>
                      <td className="px-4 py-3 whitespace-nowrap text-slate-600 text-xs">
                        {fmtDate(trip.startTime, 'Unknown')}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-slate-600 text-xs">
                        {fmtDate(trip.endTime, 'In progress')}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-slate-700">
                        {fmtDuration(trip.startTime, trip.endTime)}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-slate-700">
                        {safeNum(trip.totalDistanceKm)} km
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-slate-700">{avgFuel}</td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          alerts > 0 ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500'
                        }`}>
                          {alerts}
                        </span>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          anomalies > 0 ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-500'
                        }`}>
                          {anomalies}
                        </span>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-slate-400">
                        <ChevronRight className="w-4 h-4" />
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
