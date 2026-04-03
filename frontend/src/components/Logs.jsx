import { useState, useMemo } from 'react';
import { Search, Download, Filter } from 'lucide-react';
import { format } from 'date-fns';
import { mockTelemetryLogs } from '../data/mockData';

export default function Logs() {
  const [search,          setSearch]          = useState('');
  const [filterTruck,     setFilterTruck]     = useState('all');
  const [anomalyOnly,     setAnomalyOnly]     = useState(false);

  const uniqueTrucks = [...new Set(mockTelemetryLogs.map(l => l.truckId))];

  const filtered = useMemo(() => mockTelemetryLogs.filter(l => {
    const q = search.toLowerCase();
    return (
      (l.truckName.toLowerCase().includes(q) || l.truckId.toLowerCase().includes(q)) &&
      (filterTruck === 'all' || l.truckId === filterTruck) &&
      (!anomalyOnly || l.anomaly)
    );
  }), [search, filterTruck, anomalyOnly]);

  const handleExport = () => {
    const header = 'Timestamp,Truck ID,Truck Name,Fuel,Lat,Lon,Speed,Anomaly,Status\n';
    const rows = mockTelemetryLogs.map(l =>
      `${l.timestamp},${l.truckId},${l.truckName},${l.fuel},${l.latitude},${l.longitude},${l.speed},${l.anomaly},${l.tripStatus}`
    ).join('\n');
    const blob = new Blob([header + rows], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `telemetry_logs_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
  };

  const stats = [
    { label: 'Total Logs',    value: mockTelemetryLogs.length,                                  color: 'text-slate-900' },
    { label: 'Active Trucks', value: uniqueTrucks.length,                                        color: 'text-green-600' },
    { label: 'Anomalies',     value: mockTelemetryLogs.filter(l => l.anomaly).length,            color: 'text-red-600' },
    { label: 'Avg Speed',     value: Math.round(mockTelemetryLogs.reduce((s,l) => s+l.speed,0) / mockTelemetryLogs.length) + ' km/h', color: 'text-blue-600' },
  ];

  return (
    <div className="p-3 sm:p-4 lg:p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold text-slate-900 mb-1">Telemetry Logs</h1>
          <p className="text-sm text-slate-500">View and analyze fleet telemetry data</p>
        </div>
        <button
          onClick={handleExport}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <Download className="w-4 h-4" />
          <span className="hidden sm:inline">Export CSV</span>
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        {stats.map(s => (
          <div key={s.label} className="bg-white rounded-xl border border-slate-200 p-3 sm:p-4">
            <p className="text-xs text-slate-500 mb-1">{s.label}</p>
            <p className={`text-xl sm:text-2xl font-bold ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Filter className="w-4 h-4 text-slate-500" />
          <span className="text-sm font-medium text-slate-900">Filters</span>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mb-3">
          <div className="lg:col-span-2 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text" value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search by truck name or ID..."
              className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <select value={filterTruck} onChange={e => setFilterTruck(e.target.value)}
            className="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
            <option value="all">All Trucks</option>
            {uniqueTrucks.map(id => <option key={id} value={id}>{id}</option>)}
          </select>
        </div>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={anomalyOnly} onChange={e => setAnomalyOnly(e.target.checked)}
            className="w-4 h-4 text-blue-600 border-slate-300 rounded focus:ring-blue-500" />
          <span className="text-sm text-slate-600">Show anomalies only</span>
        </label>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200">
          <span className="text-sm font-medium text-slate-900">Logs ({filtered.length})</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                {['Timestamp','Truck','Latitude','Longitude','Speed','Fuel','Status','Anomaly'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-12 text-center text-slate-400">No logs found</td></tr>
              ) : filtered.map(log => (
                <tr key={log.id} className={`hover:bg-slate-50 transition-colors ${log.anomaly ? 'bg-red-50' : ''}`}>
                  <td className="px-4 py-3 whitespace-nowrap text-slate-700">
                    {format(new Date(log.timestamp), 'MMM d, h:mm a')}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <p className="font-medium text-slate-900">{log.truckName}</p>
                    <p className="text-xs text-slate-400">{log.truckId}</p>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-slate-600">{log.latitude.toFixed(6)}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-slate-600">{log.longitude.toFixed(6)}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-slate-700">{log.speed} km/h</td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <div className="w-14 bg-slate-200 rounded-full h-1.5">
                        <div className={`h-1.5 rounded-full ${log.fuel > 50 ? 'bg-green-500' : log.fuel > 20 ? 'bg-yellow-500' : 'bg-red-500'}`}
                          style={{ width: `${log.fuel}%` }} />
                      </div>
                      <span className="text-slate-700 w-8">{log.fuel}%</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                      log.tripStatus === 'active' ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-600'
                    }`}>{log.tripStatus}</span>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {log.anomaly
                      ? <span className="px-2 py-0.5 bg-red-100 text-red-700 rounded text-xs font-medium">Yes</span>
                      : <span className="text-slate-400">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
