import { useState } from 'react';
import { Truck, AlertTriangle, Fuel, Wrench, Activity, Clock, RefreshCw } from 'lucide-react';
import { normalizeAlert } from '../utils/api';
import { useApi } from '../hooks/useApi';
import { useLiveFleet } from '../hooks/useLiveFleet';
import { getStatusColor, getStatusLabel } from '../utils/statusColors';
import FleetMap from './FleetMap';
import TruckDetailModal from './TruckDetailModal';

const buildStatCards = (trucks) => [
  { label: 'Total Fleet',     value: trucks.length,                                          icon: Truck,         textColor: 'text-blue-600',   bgColor: 'bg-blue-50' },
  { label: 'Active Trips',    value: trucks.filter(t => t.tripStatus === 'active').length,   icon: Activity,      textColor: 'text-green-600',  bgColor: 'bg-green-50' },
  { label: 'Anomalies',       value: trucks.filter(t => t.status === 'anomaly').length,      icon: AlertTriangle, textColor: 'text-red-600',    bgColor: 'bg-red-50' },
  { label: 'Rest Alerts',     value: trucks.filter(t => t.status === 'rest_alert').length,   icon: Clock,         textColor: 'text-amber-600',  bgColor: 'bg-amber-50' },
  { label: 'Maintenance Due', value: trucks.filter(t => t.status === 'maintenance').length,  icon: Wrench,        textColor: 'text-orange-600', bgColor: 'bg-orange-50' },
  { label: 'Low Fuel',        value: trucks.filter(t => t.status === 'low_fuel').length,     icon: Fuel,          textColor: 'text-yellow-600', bgColor: 'bg-yellow-50' },
];

export default function Dashboard() {
  const [selectedTruckId, setSelectedTruckId] = useState(null);

  const { trucks: rawTrucks, loading: trucksLoading, error: trucksError, refetch: refetchTrucks } =
    useLiveFleet();

  const { data: rawAlerts, loading: alertsLoading, refetch: refetchAlerts } =
    useApi('/alerts?resolved=false&limit=5', {
      transform: arr => arr.map(normalizeAlert),
      pollInterval: 30_000,
    });

  const trucks       = rawTrucks;
  const recentAlerts = rawAlerts  ?? [];
  const selectedTruck = trucks.find(t => t.id === selectedTruckId);
  const cards         = buildStatCards(trucks);
  const loading       = trucksLoading || alertsLoading;

  const handleRefresh = () => { refetchTrucks(); refetchAlerts(); };

  return (
    <div className="flex flex-col lg:flex-row gap-4 p-3 sm:p-4 lg:p-6">

      {/* ── LEFT COLUMN ── stat cards + map ─────────────────────────────── */}
      <div className="flex-1 flex flex-col gap-4 min-w-0">

        {/* Stat cards */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 sm:gap-3">
          {cards.map(card => (
            <div
              key={card.label}
              className="bg-white rounded-xl p-3 sm:p-4 border border-slate-200 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between mb-2">
                <div className={`p-2 rounded-lg ${card.bgColor}`}>
                  <card.icon className={`w-4 h-4 sm:w-5 sm:h-5 ${card.textColor}`} />
                </div>
                <span className={`text-xl sm:text-2xl font-bold ${card.textColor}`}>
                  {trucksLoading ? '—' : card.value}
                </span>
              </div>
              <p className="text-xs sm:text-sm text-slate-500 truncate">{card.label}</p>
            </div>
          ))}
        </div>

        {/* Error banner */}
        {trucksError && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            {trucksError}
          </div>
        )}

        {/* Map card */}
        <div className="bg-white rounded-xl border border-slate-200 p-3 sm:p-4 flex flex-col
                        h-[380px] sm:h-[460px] md:h-[520px] lg:h-[calc(100vh-280px)]">
          <div className="flex items-center justify-between mb-3 flex-shrink-0">
            <h3 className="text-base sm:text-lg font-semibold text-slate-900">Live Fleet Map</h3>
            <div className="flex items-center gap-3">
              <button onClick={handleRefresh} disabled={loading}
                className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors disabled:opacity-50">
                <RefreshCw className={`w-4 h-4 text-slate-500 ${loading ? 'animate-spin' : ''}`} />
              </button>
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                <span>Live Tracking</span>
              </div>
            </div>
          </div>
          <div className="flex-1 rounded-lg overflow-hidden">
            {trucks.length === 0 && !trucksLoading ? (
              <div className="w-full h-full flex items-center justify-center bg-slate-50 rounded-lg">
                <p className="text-sm text-slate-400">No trucks with GPS data</p>
              </div>
            ) : (
              <FleetMap
                trucks={trucks}
                selectedTruckId={selectedTruckId}
                onTruckSelect={setSelectedTruckId}
              />
            )}
          </div>
        </div>
      </div>

      {/* ── RIGHT COLUMN ── recent alerts + fleet list ───────────────────── */}
      <div className="w-full lg:w-80 xl:w-96 flex flex-col gap-4">

        {/* Recent Alerts */}
        <div className="bg-white rounded-xl border border-slate-200 p-3 sm:p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm sm:text-base font-semibold text-slate-900">Recent Alerts</h3>
            <span className="text-xs text-slate-500">{recentAlerts.length} Active</span>
          </div>
          <div className="space-y-2 max-h-36 overflow-y-auto">
            {recentAlerts.length === 0 ? (
              <p className="text-xs text-slate-400 text-center py-4">
                {alertsLoading ? 'Loading…' : 'No active alerts'}
              </p>
            ) : recentAlerts.map(alert => (
              <div key={alert.id} className="flex items-start gap-2 p-2 bg-slate-50 rounded-lg">
                <AlertTriangle className={`w-4 h-4 flex-shrink-0 mt-0.5 ${
                  alert.severity === 'high'   ? 'text-red-500'    :
                  alert.severity === 'medium' ? 'text-orange-500' : 'text-yellow-500'
                }`} />
                <div className="min-w-0">
                  <p className="text-xs font-medium text-slate-800 truncate">{alert.truckName}</p>
                  <p className="text-xs text-slate-500 line-clamp-2">{alert.message}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Fleet Status list */}
        <div className="bg-white rounded-xl border border-slate-200 p-3 sm:p-4 flex flex-col
                        max-h-[420px] lg:max-h-[calc(100vh-340px)]">
          <h3 className="text-sm sm:text-base font-semibold text-slate-900 mb-3 flex-shrink-0">
            Fleet Status
          </h3>
          <div className="flex-1 overflow-y-auto space-y-2">
            {trucksLoading ? (
              <p className="text-xs text-slate-400 text-center py-8">Loading fleet…</p>
            ) : trucks.length === 0 ? (
              <p className="text-xs text-slate-400 text-center py-8">No trucks in fleet</p>
            ) : trucks.map(truck => (
              <button
                key={truck.id}
                onClick={() => setSelectedTruckId(truck.id)}
                className={`w-full text-left p-3 rounded-xl border transition-all ${
                  selectedTruckId === truck.id
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${getStatusColor(truck.status)}`} />
                    <span className="text-sm font-medium text-slate-900 truncate">{truck.name}</span>
                  </div>
                  <span className="text-xs text-slate-400 ml-2 flex-shrink-0">{truck.code}</span>
                </div>
                <p className="text-xs text-slate-500 mb-1.5 truncate">{truck.driver}</p>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-500">{getStatusLabel(truck.status)}</span>
                  <div className="flex gap-2 text-slate-600">
                    <span>{truck.speed} km/h</span>
                    <span>{truck.fuel}% fuel</span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {selectedTruck && (
        <TruckDetailModal truck={selectedTruck} onClose={() => setSelectedTruckId(null)} />
      )}
    </div>
  );
}
