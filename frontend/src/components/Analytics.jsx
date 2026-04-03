import { TrendingUp, Activity, Fuel, AlertTriangle } from 'lucide-react';
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { mockTrucks, mockAlerts, mockTelemetryLogs } from '../data/mockData';

const COLORS = ['#22c55e', '#eab308', '#ef4444', '#f97316', '#f59e0b', '#ec4899', '#475569'];

const fuelTrendData = [
  { time: '06:00', avgFuel: 92 },
  { time: '07:00', avgFuel: 88 },
  { time: '08:00', avgFuel: 84 },
  { time: '09:00', avgFuel: 78 },
  { time: '10:00', avgFuel: 72 },
  { time: '11:00', avgFuel: 66 },
  { time: '12:00', avgFuel: 60 },
];

const distanceData = [
  { truck: 'TRK-001', distance: 145.8 },
  { truck: 'TRK-002', distance: 203.4 },
  { truck: 'TRK-003', distance: 289.7 },
  { truck: 'TRK-004', distance: 412.3 },
  { truck: 'TRK-005', distance: 156.2 },
  { truck: 'TRK-007', distance: 98.5 },
];

export default function Analytics() {
  const totalDistance      = mockTrucks.reduce((s, t) => s + t.distance, 0);
  const avgFuel            = Math.round(mockTrucks.reduce((s, t) => s + t.fuel, 0) / mockTrucks.length);
  const totalOpHours       = mockTrucks.reduce((s, t) => s + t.operatingHours, 0);
  const activeTrips        = mockTrucks.filter(t => t.tripStatus === 'active');
  const avgSpeed           = activeTrips.length
    ? Math.round(activeTrips.reduce((s, t) => s + t.speed, 0) / activeTrips.length)
    : 0;
  const utilization        = Math.round((activeTrips.length / mockTrucks.length) * 100);
  const activeAlerts       = mockAlerts.filter(a => !a.resolved).length;

  const alertTypeData = [
    { name: 'Anomaly',     value: mockAlerts.filter(a => a.type === 'anomaly').length },
    { name: 'Rest Alert',  value: mockAlerts.filter(a => a.type === 'rest').length },
    { name: 'Maintenance', value: mockAlerts.filter(a => a.type === 'maintenance').length },
    { name: 'Low Fuel',    value: mockAlerts.filter(a => a.type === 'low_fuel').length },
  ];

  const statusData = [
    { name: 'Active',      value: mockTrucks.filter(t => t.status === 'active').length },
    { name: 'Idle',        value: mockTrucks.filter(t => t.status === 'idle').length },
    { name: 'Anomaly',     value: mockTrucks.filter(t => t.status === 'anomaly').length },
    { name: 'Maintenance', value: mockTrucks.filter(t => t.status === 'maintenance').length },
    { name: 'Rest Alert',  value: mockTrucks.filter(t => t.status === 'rest_alert').length },
    { name: 'Low Fuel',    value: mockTrucks.filter(t => t.status === 'low_fuel').length },
    { name: 'Offline',     value: mockTrucks.filter(t => t.status === 'offline').length },
  ];

  const tooltipStyle = {
    contentStyle: { backgroundColor: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' },
  };

  return (
    <div className="p-3 sm:p-4 lg:p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl sm:text-2xl font-semibold text-slate-900 mb-1">Analytics & Monitoring</h1>
        <p className="text-sm text-slate-500">Fleet performance insights and metrics</p>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6">
        {[
          { icon: TrendingUp,   color: 'from-blue-500 to-blue-600',   shade: 'blue-100',   value: `${totalDistance.toFixed(1)} km`,  label: 'Total Distance Today' },
          { icon: Activity,     color: 'from-green-500 to-green-600', shade: 'green-100',  value: activeTrips.length,                label: 'Active Trips' },
          { icon: Fuel,         color: 'from-orange-500 to-orange-600',shade:'orange-100', value: `${avgFuel}%`,                     label: 'Average Fuel Level' },
          { icon: AlertTriangle,color: 'from-purple-500 to-purple-600',shade:'purple-100', value: activeAlerts,                      label: 'Active Alerts' },
        ].map(({ icon: Icon, color, value, label }) => (
          <div key={label} className={`bg-gradient-to-br ${color} rounded-xl p-4 sm:p-5 text-white`}>
            <Icon className="w-6 h-6 opacity-80 mb-3" />
            <p className="text-2xl sm:text-3xl font-bold mb-1">{value}</p>
            <p className="text-xs opacity-90">{label}</p>
          </div>
        ))}
      </div>

      {/* Charts row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div className="bg-white rounded-xl border border-slate-200 p-4 sm:p-5">
          <h3 className="text-base font-semibold text-slate-900 mb-4">Fuel Level Trend</h3>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={fuelTrendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="time" stroke="#94a3b8" style={{ fontSize: '11px' }} />
              <YAxis stroke="#94a3b8" style={{ fontSize: '11px' }} />
              <Tooltip {...tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              <Line type="monotone" dataKey="avgFuel" stroke="#3b82f6" strokeWidth={2.5}
                name="Avg Fuel (%)" dot={{ fill: '#3b82f6', r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-4 sm:p-5">
          <h3 className="text-base font-semibold text-slate-900 mb-4">Distance by Truck</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={distanceData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="truck" stroke="#94a3b8" style={{ fontSize: '11px' }} />
              <YAxis stroke="#94a3b8" style={{ fontSize: '11px' }} />
              <Tooltip {...tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              <Bar dataKey="distance" fill="#22c55e" name="Distance (km)" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Charts row 2 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div className="bg-white rounded-xl border border-slate-200 p-4 sm:p-5">
          <h3 className="text-base font-semibold text-slate-900 mb-4">Alert Type Distribution</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={alertTypeData} cx="50%" cy="50%" outerRadius={75} dataKey="value"
                label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                labelLine={false} style={{ fontSize: '11px' }}>
                {alertTypeData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ fontSize: '12px', borderRadius: '8px' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-4 sm:p-5">
          <h3 className="text-base font-semibold text-slate-900 mb-4">Fleet Status Distribution</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={statusData.filter(d => d.value > 0)} cx="50%" cy="50%" outerRadius={75} dataKey="value"
                label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                labelLine={false} style={{ fontSize: '11px' }}>
                {statusData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ fontSize: '12px', borderRadius: '8px' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        {[
          { label: 'Total Operating Hours', value: `${totalOpHours.toFixed(1)} h`, sub: 'Across all active trucks' },
          { label: 'Average Speed',         value: `${avgSpeed} km/h`,             sub: 'Active trips only' },
          { label: 'Fleet Utilization',     value: `${utilization}%`,              sub: 'Trucks currently active' },
        ].map(s => (
          <div key={s.label} className="bg-white rounded-xl border border-slate-200 p-4 sm:p-5">
            <p className="text-xs text-slate-500 mb-2">{s.label}</p>
            <p className="text-2xl sm:text-3xl font-bold text-slate-900 mb-1">{s.value}</p>
            <p className="text-xs text-slate-400">{s.sub}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
