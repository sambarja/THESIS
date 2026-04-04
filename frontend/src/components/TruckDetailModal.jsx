import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Fuel, Activity, Route, Clock, AlertTriangle, Navigation, RefreshCw } from 'lucide-react';
import { format, formatDistanceStrict } from 'date-fns';
import FleetMap from './FleetMap';
import { normalizeAlert, normalizeLog } from '../utils/api';
import { useApi } from '../hooks/useApi';
import { getStatusColor, getStatusLabel } from '../utils/statusColors';

/** Convert fractional hours (e.g. 1.5) to "1h 30m" */
function fmtHM(hours) {
  if (hours == null || isNaN(hours)) return '—';
  const h = Math.floor(hours);
  const m = Math.round((hours - h) * 60);
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

function Tab({ label, active, onClick, count }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
        active ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-100'
      }`}
    >
      {label}{count != null ? ` (${count})` : ''}
    </button>
  );
}

export default function TruckDetailModal({ truck, onClose }) {
  const [activeTab, setActiveTab] = useState('map');
  const [nowTs, setNowTs] = useState(Date.now());

  const { data: rawAlerts, loading: alertsLoading } = useApi(
    `/alerts?truck_id=${truck.id}`,
    { transform: arr => arr.map(normalizeAlert), pollInterval: 15_000 },
  );

  const { data: rawLogs, loading: logsLoading } = useApi(
    `/trucks/${truck.id}/telemetry/history?limit=50`,
    { transform: arr => arr.map(normalizeLog), pollInterval: 8_000 },
  );

  const truckAlerts = rawAlerts ?? [];
  const truckLogs   = rawLogs   ?? [];
  const liveTripActive = truck.tripStatus === 'active' || truck.tripStatus === 'paused';
  const liveOperatingHours = liveTripActive && truck.tripStartTime
    ? (nowTs - new Date(truck.tripStartTime).getTime()) / 3_600_000
    : truck.operatingHours;

  useEffect(() => {
    if (!liveTripActive || !truck.tripStartTime) return;
    setNowTs(Date.now());
    const id = setInterval(() => setNowTs(Date.now()), 1000);
    return () => clearInterval(id);
  }, [liveTripActive, truck.tripStartTime]);

  return createPortal(
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-3 sm:p-4" style={{ zIndex: 9999 }}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-start justify-between p-5 sm:p-6 border-b border-slate-200 flex-shrink-0">
          <div>
            <div className="flex items-center gap-3 mb-1 flex-wrap">
              <h2 className="text-xl sm:text-2xl font-semibold text-slate-900">{truck.name}</h2>
              <span className={`px-3 py-1 rounded-full text-xs text-white font-medium ${getStatusColor(truck.status)}`}>
                {getStatusLabel(truck.status)}
              </span>
            </div>
            <p className="text-sm text-slate-500">{truck.driver} • {truck.code}</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg transition-colors ml-2 flex-shrink-0">
            <X className="w-5 h-5 text-slate-500" />
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto p-5 sm:p-6">
          {/* Stats */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
            <div className="bg-blue-50 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <Fuel className="w-4 h-4 text-blue-600" />
                <span className="text-xs text-blue-700 font-medium">Fuel Level</span>
              </div>
              <p className="text-2xl font-semibold text-blue-600 mb-2">{truck.fuel}%</p>
              <div className="bg-blue-200 rounded-full h-1.5">
                <div className="bg-blue-600 h-1.5 rounded-full" style={{ width: `${truck.fuel}%` }} />
              </div>
            </div>
            <div className="bg-green-50 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <Activity className="w-4 h-4 text-green-600" />
                <span className="text-xs text-green-700 font-medium">Speed</span>
              </div>
              <p className="text-2xl font-semibold text-green-600">{truck.speed}</p>
              <p className="text-xs text-green-600 mt-1">km/h</p>
            </div>
            <div className="bg-purple-50 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <Route className="w-4 h-4 text-purple-600" />
                <span className="text-xs text-purple-700 font-medium">Distance</span>
              </div>
              <p className="text-2xl font-semibold text-purple-600">{truck.distance}</p>
              <p className="text-xs text-purple-600 mt-1">km traveled</p>
            </div>
            <div className="bg-orange-50 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <Clock className="w-4 h-4 text-orange-600" />
                <span className="text-xs text-orange-700 font-medium">Op. Hours</span>
              </div>
              <p className="text-2xl font-semibold text-orange-600">{fmtHM(liveOperatingHours)}</p>
              <p className="text-xs text-orange-600 mt-1">this trip</p>
            </div>
          </div>

          {/* Trip info */}
          {(truck.tripStatus === 'active' || truck.tripStatus === 'paused') && truck.tripStartTime && (
            <div className="bg-slate-50 rounded-xl p-4 mb-6 text-sm">
              <div className="flex items-center justify-between mb-2">
                <p className="font-medium text-slate-900">Current Trip</p>
                {truck.tripStatus === 'paused' && (
                  <span className="px-2 py-0.5 bg-amber-100 text-amber-700 text-xs rounded-full font-medium">Driver Resting</span>
                )}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-slate-600">
                <p>Started: <span className="text-slate-900">{format(new Date(truck.tripStartTime), 'MMM d, h:mm a')}</span></p>
                <p>Elapsed: <span className="text-slate-900">{formatDistanceStrict(new Date(truck.tripStartTime), new Date(nowTs))}</span></p>
                <p>Distance: <span className="text-slate-900">{truck.distance} km</span></p>
                <p>Location: <span className="text-slate-900">{truck.position[0].toFixed(4)}, {truck.position[1].toFixed(4)}</span></p>
              </div>
            </div>
          )}

          {/* Tabs */}
          <div className="flex gap-2 mb-4 flex-wrap">
            <Tab label="Map"       active={activeTab === 'map'}    onClick={() => setActiveTab('map')} />
            <Tab label="Live Data" active={activeTab === 'live'}   onClick={() => setActiveTab('live')} />
            <Tab label="Alerts"    active={activeTab === 'alerts'} onClick={() => setActiveTab('alerts')}
              count={alertsLoading ? null : truckAlerts.length} />
            <Tab label="Logs"      active={activeTab === 'logs'}   onClick={() => setActiveTab('logs')} />
          </div>

          {/* Tab content */}
          {activeTab === 'map' && (
            <div className="h-80 sm:h-96 rounded-xl overflow-hidden border border-slate-200">
              <FleetMap trucks={[truck]} selectedTruckId={truck.id} singleTruck />
            </div>
          )}

          {activeTab === 'live' && (
            <div className="bg-slate-50 rounded-xl p-4">
              <p className="font-medium text-slate-900 mb-3 text-sm">Real-time Telemetry</p>
              <div className="grid grid-cols-2 gap-3 text-sm">
                {[
                  ['Latitude',    truck.position[0].toFixed(6)],
                  ['Longitude',   truck.position[1].toFixed(6)],
                  ['Speed',       `${truck.speed} km/h`],
                  ['Fuel',        `${truck.fuel}%`],
                  ['Trip Status', truck.tripStatus],
                  ['Last Update', format(new Date(truck.lastUpdate), 'h:mm a')],
                ].map(([label, value]) => (
                  <div key={label}>
                    <span className="text-slate-500">{label}:</span>
                    <span className="ml-2 text-slate-900 capitalize">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'alerts' && (
            <div className="space-y-3">
              {alertsLoading ? (
                <div className="text-center py-10 text-slate-400">
                  <RefreshCw className="w-8 h-8 mx-auto mb-2 animate-spin opacity-40" />
                  <p className="text-sm">Loading alerts…</p>
                </div>
              ) : truckAlerts.length === 0 ? (
                <div className="text-center py-10 text-slate-400">
                  <AlertTriangle className="w-10 h-10 mx-auto mb-2 opacity-30" />
                  <p className="text-sm">No alerts for this truck</p>
                </div>
              ) : truckAlerts.map((alert) => (
                <div
                  key={alert.id}
                  className={`border-l-4 rounded-xl p-4 ${
                    alert.severity === 'high'   ? 'bg-red-50 border-red-500' :
                    alert.severity === 'medium' ? 'bg-orange-50 border-orange-500' :
                                                  'bg-yellow-50 border-yellow-500'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
                    <span className={`text-xs font-semibold uppercase tracking-wide ${
                      alert.severity === 'high'   ? 'text-red-700' :
                      alert.severity === 'medium' ? 'text-orange-700' : 'text-yellow-700'
                    }`}>{alert.type}</span>
                    {alert.resolved && (
                      <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full">Resolved</span>
                    )}
                  </div>
                  <p className="text-sm text-slate-800 mb-1">{alert.message}</p>
                  <p className="text-xs text-slate-500">{format(new Date(alert.timestamp), 'MMM d, yyyy h:mm a')}</p>
                </div>
              ))}
            </div>
          )}

          {activeTab === 'logs' && (
            <div className="space-y-2">
              {logsLoading ? (
                <div className="text-center py-10 text-slate-400">
                  <RefreshCw className="w-8 h-8 mx-auto mb-2 animate-spin opacity-40" />
                  <p className="text-sm">Loading telemetry…</p>
                </div>
              ) : truckLogs.length === 0 ? (
                <div className="text-center py-10 text-slate-400">
                  <Navigation className="w-10 h-10 mx-auto mb-2 opacity-30" />
                  <p className="text-sm">No logs available</p>
                </div>
              ) : [...truckLogs].reverse().map((log) => (
                <div key={log.id} className="bg-slate-50 rounded-xl p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-slate-900">
                      {format(new Date(log.timestamp), 'MMM d, h:mm a')}
                    </span>
                    {log.anomaly && (
                      <span className="px-2 py-0.5 bg-red-100 text-red-700 text-xs rounded-full">Anomaly</span>
                    )}
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs text-slate-600">
                    <span>Speed: {log.speed} km/h</span>
                    <span>Fuel: {log.fuel}%</span>
                    <span>Lat: {log.latitude.toFixed(4)}</span>
                    <span>Lng: {log.longitude.toFixed(4)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
