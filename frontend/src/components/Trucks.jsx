import { useState } from 'react';
import { Search, SlidersHorizontal } from 'lucide-react';
import { mockTrucks } from '../data/mockData';
import { getStatusColor, getStatusLabel } from '../utils/statusColors';
import TruckDetailModal from './TruckDetailModal';

export default function Trucks() {
  const [selectedTruckId, setSelectedTruckId] = useState(null);
  const [searchTerm, setSearchTerm]           = useState('');
  const [filterStatus, setFilterStatus]       = useState('all');
  const [viewMode, setViewMode]               = useState('grid');

  const selectedTruck = mockTrucks.find(t => t.id === selectedTruckId);

  const filtered = mockTrucks.filter(t => {
    const q = searchTerm.toLowerCase();
    const matchSearch = t.name.toLowerCase().includes(q) || t.driver.toLowerCase().includes(q) || t.id.toLowerCase().includes(q);
    const matchStatus = filterStatus === 'all' || t.status === filterStatus;
    return matchSearch && matchStatus;
  });

  return (
    <div className="p-4 lg:p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl sm:text-2xl font-semibold text-slate-900 mb-1">Fleet Management</h1>
        <p className="text-sm text-slate-500">Manage and monitor all trucks in your fleet</p>
      </div>

      {/* Search + Filters */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 mb-6">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              placeholder="Search by name, driver, or ID..."
              className="w-full pl-10 pr-4 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div className="flex gap-3">
            <div className="flex items-center gap-2">
              <SlidersHorizontal className="w-4 h-4 text-slate-500" />
              <select
                value={filterStatus}
                onChange={e => setFilterStatus(e.target.value)}
                className="px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="all">All Status</option>
                <option value="active">Active</option>
                <option value="idle">Idle</option>
                <option value="anomaly">Anomaly</option>
                <option value="maintenance">Maintenance</option>
                <option value="rest_alert">Rest Alert</option>
                <option value="low_fuel">Low Fuel</option>
                <option value="offline">Offline</option>
              </select>
            </div>
            <div className="flex border border-slate-300 rounded-lg overflow-hidden">
              {['grid', 'list'].map(mode => (
                <button
                  key={mode}
                  onClick={() => setViewMode(mode)}
                  className={`px-4 py-2 text-sm capitalize transition-colors ${
                    viewMode === mode ? 'bg-blue-600 text-white' : 'bg-white text-slate-700 hover:bg-slate-50'
                  } ${mode === 'list' ? 'border-l border-slate-300' : ''}`}
                >
                  {mode}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <p className="text-xs text-slate-500 mb-4">
        Showing {filtered.length} of {mockTrucks.length} trucks
      </p>

      {/* Grid view */}
      {viewMode === 'grid' ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map(truck => (
            <button
              key={truck.id}
              onClick={() => setSelectedTruckId(truck.id)}
              className="bg-white rounded-xl border border-slate-200 p-5 text-left hover:shadow-md hover:border-blue-300 transition-all"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">{truck.name}</h3>
                  <p className="text-xs text-slate-400">{truck.id}</p>
                </div>
                <div className={`w-2.5 h-2.5 rounded-full mt-1 ${getStatusColor(truck.status)}`} />
              </div>
              <p className="text-xs text-slate-500 mb-3 pb-3 border-b border-slate-100">{truck.driver}</p>
              <span className={`inline-block px-2.5 py-1 rounded-full text-xs text-white mb-3 ${getStatusColor(truck.status)}`}>
                {getStatusLabel(truck.status)}
              </span>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div><p className="text-slate-400">Speed</p><p className="text-slate-800 font-medium">{truck.speed} km/h</p></div>
                <div><p className="text-slate-400">Fuel</p><p className="text-slate-800 font-medium">{truck.fuel}%</p></div>
                <div><p className="text-slate-400">Distance</p><p className="text-slate-800 font-medium">{truck.distance} km</p></div>
                <div><p className="text-slate-400">Hours</p><p className="text-slate-800 font-medium">{truck.operatingHours}h</p></div>
              </div>
            </button>
          ))}
        </div>
      ) : (
        /* List view */
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  {['Truck', 'Driver', 'Status', 'Speed', 'Fuel', 'Distance', 'Hours'].map(h => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map(truck => (
                  <tr
                    key={truck.id}
                    onClick={() => setSelectedTruckId(truck.id)}
                    className="hover:bg-slate-50 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${getStatusColor(truck.status)}`} />
                        <div>
                          <p className="font-medium text-slate-900">{truck.name}</p>
                          <p className="text-xs text-slate-400">{truck.id}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-700">{truck.driver}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2.5 py-1 rounded-full text-xs text-white ${getStatusColor(truck.status)}`}>
                        {getStatusLabel(truck.status)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-700">{truck.speed} km/h</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-16 bg-slate-200 rounded-full h-1.5">
                          <div
                            className={`h-1.5 rounded-full ${truck.fuel > 50 ? 'bg-green-500' : truck.fuel > 20 ? 'bg-yellow-500' : 'bg-red-500'}`}
                            style={{ width: `${truck.fuel}%` }}
                          />
                        </div>
                        <span className="text-slate-700 w-8 text-right">{truck.fuel}%</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-700">{truck.distance} km</td>
                    <td className="px-4 py-3 text-slate-700">{truck.operatingHours}h</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {selectedTruck && (
        <TruckDetailModal truck={selectedTruck} onClose={() => setSelectedTruckId(null)} />
      )}
    </div>
  );
}
