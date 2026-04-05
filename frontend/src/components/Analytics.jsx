import { useMemo, useState } from 'react';
import { Activity, AlertTriangle, Fuel, RefreshCw, Route, Clock3 } from 'lucide-react';
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { normalizeTruck, normalizeTripSummary } from '../utils/api';
import { useApi } from '../hooks/useApi';

const COLORS = ['#22c55e', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#64748b'];
const tooltipStyle = {
  contentStyle: { backgroundColor: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' },
};

function buildSummaryPath(days, truckId) {
  const params = new URLSearchParams({ days: String(days), limit: '200' });
  if (truckId && truckId !== 'all') params.set('truck_id', truckId);
  return `/trips/summaries?${params.toString()}`;
}

function ensureArray(value) {
  return Array.isArray(value) ? value : [];
}

function safeNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}


export default function Analytics() {
  const [days, setDays] = useState(90);
  const [truckId, setTruckId] = useState('all');

  const summariesApi = useApi(buildSummaryPath(days, truckId), {
    transform: payload => {
      const safePayload = payload && typeof payload === 'object' ? payload : {};
      return {
        items: ensureArray(safePayload.items).map(normalizeTripSummary),
        totals: safePayload.totals && typeof safePayload.totals === 'object' ? safePayload.totals : {},
        count: safeNumber(safePayload.count),
      };
    },
    pollInterval: 30_000,
  });

  const fleetApi = useApi('/fleet/status', {
    transform: rows => ensureArray(rows).map(normalizeTruck),
    pollInterval: 15_000,
  });

  const loading = summariesApi.loading || fleetApi.loading;
  const summaries = ensureArray(summariesApi.data?.items);
  const totals = summariesApi.data?.totals && typeof summariesApi.data.totals === 'object'
    ? summariesApi.data.totals
    : {};
  const fleet = ensureArray(fleetApi.data);
  const activeTrips = fleet.filter(truck => truck.tripStatus === 'active').length;
  const avgFuelValue = totals.average_fuel_level;
  const avgFuel = avgFuelValue != null && Number.isFinite(Number(avgFuelValue))
    ? `${Math.round(Number(avgFuelValue))}%`
    : '--';

  const truckOptions = useMemo(() => (
    [...fleet]
      .sort((left, right) => String(left.code ?? '').localeCompare(String(right.code ?? '')))
      .map(truck => ({ id: truck.id, label: truck.code ?? 'Unknown Truck' }))
  ), [fleet]);

  const distanceByTruck = useMemo(() => {
    const grouped = {};
    for (const summary of summaries) {
      const truckCode = summary.truckCode || 'Unknown Truck';
      grouped[truckCode] = (grouped[truckCode] ?? 0) + safeNumber(summary.totalDistanceKm);
    }
    return Object.entries(grouped).map(([truck, distance]) => ({ truck, distance: +distance.toFixed(1) }));
  }, [summaries]);

  const issueByTruck = useMemo(() => {
    const grouped = {};
    for (const summary of summaries) {
      const truckCode = summary.truckCode || 'Unknown Truck';
      if (!grouped[truckCode]) grouped[truckCode] = { truck: truckCode, alerts: 0, anomalies: 0 };
      grouped[truckCode].alerts += safeNumber(summary.totalAlerts);
      grouped[truckCode].anomalies += safeNumber(summary.totalAnomalies);
    }
    return Object.values(grouped);
  }, [summaries]);

  const statusDistribution = useMemo(() => {
    const grouped = {};
    for (const truck of fleet) {
      const status = truck.status || 'unknown';
      grouped[status] = (grouped[status] ?? 0) + 1;
    }
    return Object.entries(grouped)
      .map(([name, value]) => ({ name: name.replace('_', ' '), value }))
      .filter(item => item.value > 0);
  }, [fleet]);

  const summaryCards = [
    { icon: Route, color: 'from-blue-500 to-blue-600', value: loading ? '--' : `${safeNumber(totals.total_distance_km)} km`, label: `Total Distance (${days}d)` },
    { icon: Clock3, color: 'from-emerald-500 to-emerald-600', value: loading ? '--' : `${safeNumber(totals.total_operating_hours)} h`, label: 'Operating Hours' },
    { icon: Activity, color: 'from-indigo-500 to-indigo-600', value: loading ? '--' : activeTrips, label: 'Active Trips Now' },
    { icon: AlertTriangle, color: 'from-red-500 to-red-600', value: loading ? '--' : safeNumber(totals.total_anomalies), label: 'Total Anomalies' },
    { icon: Fuel, color: 'from-amber-500 to-amber-600', value: loading ? '--' : avgFuel, label: 'Average Fuel' },
  ];

  const showAnalyticsEmptyState = !loading && summaries.length === 0;

  const handleRefresh = () => {
    summariesApi.refetch?.();
    fleetApi.refetch?.();
  };

  return (
    <div className="p-3 sm:p-4 lg:p-6 max-w-7xl mx-auto">
      <div className="mb-6 flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold text-slate-900 mb-1">Analytics</h1>
          <p className="text-sm text-slate-500">Aggregated fleet metrics and trend charts. For per-trip records, see the Trips tab.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={truckId}
            onChange={event => setTruckId(event.target.value)}
            className="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="all">All Trucks</option>
            {truckOptions.map(option => (
              <option key={option.id} value={option.id}>{option.label}</option>
            ))}
          </select>
          <select
            value={days}
            onChange={event => setDays(Number(event.target.value))}
            className="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last 12 months</option>
          </select>
          <button
            onClick={handleRefresh}
            disabled={loading}
            className="p-2 rounded-lg hover:bg-slate-100 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 text-slate-500 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {summariesApi.error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          {summariesApi.error}
        </div>
      )}

      {showAnalyticsEmptyState && (
        <div className="mb-4 bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm text-slate-600">
          No analytics data yet because no trips have ended. Trip summaries will appear here after completed trips are recorded.
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 sm:gap-4 mb-6">
        {summaryCards.map(card => {
          const Icon = card.icon;
          return (
            <div key={card.label} className={`bg-gradient-to-br ${card.color} rounded-xl p-4 sm:p-5 text-white`}>
              <Icon className="w-6 h-6 opacity-80 mb-3" />
              <p className="text-2xl sm:text-3xl font-bold mb-1">{card.value}</p>
              <p className="text-xs opacity-90">{card.label}</p>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div className="bg-white rounded-xl border border-slate-200 p-4 sm:p-5">
          <h3 className="text-base font-semibold text-slate-900 mb-4">Distance by Truck</h3>
          {distanceByTruck.length === 0 ? (
            <div className="h-64 flex items-center justify-center text-slate-400 text-sm">
              {loading ? 'Loading...' : 'No trip summaries available yet.'}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={distanceByTruck}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="truck" stroke="#94a3b8" style={{ fontSize: '11px' }} />
                <YAxis stroke="#94a3b8" style={{ fontSize: '11px' }} />
                <Tooltip {...tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <Bar dataKey="distance" fill="#22c55e" name="Distance (km)" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-4 sm:p-5">
          <h3 className="text-base font-semibold text-slate-900 mb-4">Alerts vs Anomalies by Truck</h3>
          {issueByTruck.length === 0 ? (
            <div className="h-64 flex items-center justify-center text-slate-400 text-sm">
              {loading ? 'Loading...' : 'No trip summaries available yet.'}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={issueByTruck}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="truck" stroke="#94a3b8" style={{ fontSize: '11px' }} />
                <YAxis stroke="#94a3b8" style={{ fontSize: '11px' }} />
                <Tooltip {...tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <Bar dataKey="alerts" fill="#3b82f6" name="Alerts" radius={[6, 6, 0, 0]} />
                <Bar dataKey="anomalies" fill="#ef4444" name="Anomalies" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 p-4 sm:p-5 mb-6">
        <h3 className="text-base font-semibold text-slate-900 mb-4">Live Fleet Status Distribution</h3>
        {statusDistribution.length === 0 ? (
          <div className="h-56 flex items-center justify-center text-slate-400 text-sm">
            {loading ? 'Loading...' : 'No fleet data available.'}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={statusDistribution}
                cx="50%"
                cy="50%"
                outerRadius={75}
                dataKey="value"
                label={({ name, percent }) => `${name}: ${((percent ?? 0) * 100).toFixed(0)}%`}
                labelLine={false}
                style={{ fontSize: '11px' }}
              >
                {statusDistribution.map((item, index) => <Cell key={`${item.name}-${index}`} fill={COLORS[index % COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ fontSize: '12px', borderRadius: '8px' }} />
            </PieChart>
          </ResponsiveContainer>
        )}
      </div>

    </div>
  );
}
