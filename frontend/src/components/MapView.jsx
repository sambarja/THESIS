import { useState } from 'react';
import FleetMap from './FleetMap';
import TruckDetailModal from './TruckDetailModal';
import { mockTrucks, adminLocation } from '../data/mockData';
import { getStatusColor, getStatusLabel } from '../utils/statusColors';

export default function MapView() {
  const [selectedTruckId, setSelectedTruckId] = useState(null);
  const selectedTruck = mockTrucks.find(t => t.id === selectedTruckId);

  return (
    // Fill the entire <main> viewport height minus the header (≈ 65px)
    <div className="flex flex-col lg:flex-row" style={{ height: 'calc(100vh - 65px)' }}>

      {/* Full-height map */}
      <div className="flex-1 min-h-[400px] lg:min-h-0">
        <FleetMap
          trucks={mockTrucks}
          selectedTruckId={selectedTruckId}
          onTruckSelect={setSelectedTruckId}
          showAdminLocation
          adminLocation={adminLocation}
        />
      </div>

      {/* Sidebar list — scrolls independently */}
      <div className="w-full lg:w-72 xl:w-80 bg-white border-t lg:border-t-0 lg:border-l border-slate-200 flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200 flex-shrink-0">
          <h3 className="text-sm font-semibold text-slate-900">Fleet Status</h3>
          <p className="text-xs text-slate-500">{mockTrucks.length} trucks tracked</p>
        </div>
        <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
          {mockTrucks.map(truck => (
            <button
              key={truck.id}
              onClick={() => setSelectedTruckId(truck.id)}
              className={`w-full text-left px-4 py-3 hover:bg-slate-50 transition-colors ${
                selectedTruckId === truck.id ? 'bg-blue-50' : ''
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${getStatusColor(truck.status)}`} />
                <span className="text-sm font-medium text-slate-900 truncate">{truck.name}</span>
                <span className="text-xs text-slate-400 ml-auto flex-shrink-0">{truck.id}</span>
              </div>
              <p className="text-xs text-slate-500 mb-1">{truck.driver}</p>
              <div className="flex items-center justify-between text-xs text-slate-600">
                <span>{getStatusLabel(truck.status)}</span>
                <span>{truck.fuel}% fuel</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {selectedTruck && (
        <TruckDetailModal truck={selectedTruck} onClose={() => setSelectedTruckId(null)} />
      )}
    </div>
  );
}
