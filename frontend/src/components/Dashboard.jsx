import { useState } from 'react';
import { Truck, AlertTriangle, Fuel, Wrench, Activity, Clock } from 'lucide-react';
import { mockTrucks, mockAlerts, adminLocation } from '../data/mockData';
import { getStatusColor, getStatusLabel } from '../utils/statusColors';
import FleetMap from './FleetMap';
import TruckDetailModal from './TruckDetailModal';

const buildStatCards = (trucks) => [
  { label: 'Total Fleet',     value: trucks.length,                                         icon: Truck,         textColor: 'text-blue-600',   bgColor: 'bg-blue-50' },
  { label: 'Active Trips',    value: trucks.filter(t => t.tripStatus === 'active').length,  icon: Activity,      textColor: 'text-green-600',  bgColor: 'bg-green-50' },
  { label: 'Anomalies',       value: trucks.filter(t => t.status === 'anomaly').length,     icon: AlertTriangle, textColor: 'text-red-600',    bgColor: 'bg-red-50' },
  { label: 'Rest Alerts',     value: trucks.filter(t => t.status === 'rest_alert').length,  icon: Clock,         textColor: 'text-amber-600',  bgColor: 'bg-amber-50' },
  { label: 'Maintenance Due', value: trucks.filter(t => t.status === 'maintenance').length, icon: Wrench,        textColor: 'text-orange-600', bgColor: 'bg-orange-50' },
  { label: 'Low Fuel',        value: trucks.filter(t => t.status === 'low_fuel').length,    icon: Fuel,          textColor: 'text-yellow-600', bgColor: 'bg-yellow-50' },
];

export default function Dashboard() {
  const [selectedTruckId, setSelectedTruckId] = useState(null);
  const selectedTruck = mockTrucks.find(t => t.id === selectedTruckId);
  const cards        = buildStatCards(mockTrucks);
  const activeAlerts = mockAlerts.filter(a => !a.resolved);

  return (
    /*
     * Layout strategy:
     *  - Mobile / tablet  : single column, map has a fixed responsive height
     *  - Desktop (lg+)    : two columns, left flex-1 / right fixed-width panel,
     *                        both scroll independently via overflow-y-auto
     *
     * We deliberately avoid "h-full" here because the parent <main> is
     * overflow-auto and children cannot reliably get 100% of its scroll height.
     * Instead we give the map explicit heights per breakpoint and let the
     * right panel scroll on its own on desktop.
     */
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
                <span className={`text-xl sm:text-2xl font-bold ${card.textColor}`}>{card.value}</span>
              </div>
              <p className="text-xs sm:text-sm text-slate-500 truncate">{card.label}</p>
            </div>
          ))}
        </div>

        {/* Map card — explicit height per breakpoint so Leaflet is always happy */}
        <div className="bg-white rounded-xl border border-slate-200 p-3 sm:p-4 flex flex-col
                        h-[380px] sm:h-[460px] md:h-[520px] lg:h-[calc(100vh-280px)]">
          <div className="flex items-center justify-between mb-3 flex-shrink-0">
            <h3 className="text-base sm:text-lg font-semibold text-slate-900">Live Fleet Map</h3>
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              <span>Live Tracking</span>
            </div>
          </div>
          {/* Map takes all remaining space inside the card */}
          <div className="flex-1 rounded-lg overflow-hidden">
            <FleetMap
              trucks={mockTrucks}
              selectedTruckId={selectedTruckId}
              onTruckSelect={setSelectedTruckId}
              showAdminLocation
              adminLocation={adminLocation}
            />
          </div>
        </div>
      </div>

      {/* ── RIGHT COLUMN ── recent alerts + fleet list ───────────────────── */}
      <div className="w-full lg:w-80 xl:w-96 flex flex-col gap-4">

        {/* Recent Alerts */}
        <div className="bg-white rounded-xl border border-slate-200 p-3 sm:p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm sm:text-base font-semibold text-slate-900">Recent Alerts</h3>
            <span className="text-xs text-slate-500">{activeAlerts.length} Active</span>
          </div>
          <div className="space-y-2 max-h-36 overflow-y-auto">
            {mockAlerts.slice(0, 4).map(alert => (
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

        {/* Fleet Status list — on desktop it stretches and scrolls internally */}
        <div className="bg-white rounded-xl border border-slate-200 p-3 sm:p-4 flex flex-col
                        max-h-[420px] lg:max-h-[calc(100vh-340px)]">
          <h3 className="text-sm sm:text-base font-semibold text-slate-900 mb-3 flex-shrink-0">
            Fleet Status
          </h3>
          <div className="flex-1 overflow-y-auto space-y-2">
            {mockTrucks.map(truck => (
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
                  <span className="text-xs text-slate-400 ml-2 flex-shrink-0">{truck.id}</span>
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
