import { useState } from 'react';
import { Save, UserPlus, Trash2, Truck, Bell, Shield, CheckCircle } from 'lucide-react';

const STORAGE_KEY = 'fleet_thresholds';

function loadThresholds() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}'); }
  catch { return {}; }
}

const tabs = [
  { id: 'thresholds',   label: 'Alert Thresholds', icon: Bell },
  { id: 'users',        label: 'User Management',  icon: Shield },
  { id: 'fleet',        label: 'Fleet Settings',   icon: Truck },
];

export default function Settings() {
  const saved = loadThresholds();
  const [activeTab, setActiveTab] = useState('thresholds');
  const [savedOk,   setSavedOk]   = useState(false);
  const [thresholds, setThresholds] = useState({
    restHours:           saved.restHours           ?? '6',
    restDistance:        saved.restDistance        ?? '300',
    maintenanceDistance: saved.maintenanceDistance ?? '5000',
    overspeedKmh:        saved.overspeedKmh        ?? '100',
  });

  const handleChange = (field) => (e) => {
    setThresholds(prev => ({ ...prev, [field]: e.target.value }));
    setSavedOk(false);
  };

  const handleSave = (e) => {
    e.preventDefault();
    localStorage.setItem(STORAGE_KEY, JSON.stringify(thresholds));
    setSavedOk(true);
    setTimeout(() => setSavedOk(false), 3000);
  };

  return (
    <div className="p-4 lg:p-6 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl sm:text-2xl font-semibold text-slate-900 mb-1">Settings</h1>
        <p className="text-sm text-slate-500">Configure fleet thresholds, users, and preferences</p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-xl mb-6 w-fit">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              activeTab === tab.id
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <tab.icon className="w-4 h-4" />
            <span className="hidden sm:inline">{tab.label}</span>
          </button>
        ))}
      </div>

      {/* ── ALERT THRESHOLDS ── */}
      {activeTab === 'thresholds' && (
        <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6">
          <div className="mb-6">
            <h2 className="text-base font-semibold text-slate-900 mb-1">Alert Thresholds</h2>
            <p className="text-sm text-slate-500">
              Fine-tune when rest alerts, maintenance reminders, and overspeed warnings trigger.
            </p>
          </div>

          <form onSubmit={handleSave} className="space-y-5">
            {/* Rest Hours */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Rest Alert — Hours (h)
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="number" min="1" max="24"
                  value={thresholds.restHours}
                  onChange={handleChange('restHours')}
                  className="w-32 px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <span className="text-xs text-slate-400">
                  Alert driver after this many hours of continuous operation
                </span>
              </div>
            </div>

            {/* Rest Distance */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Rest Alert — Distance (km)
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="number" min="1"
                  value={thresholds.restDistance}
                  onChange={handleChange('restDistance')}
                  className="w-32 px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <span className="text-xs text-slate-400">
                  Alert driver after this many kilometres without rest
                </span>
              </div>
            </div>

            {/* Maintenance */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Maintenance Alert — Distance (km)
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="number" min="1"
                  value={thresholds.maintenanceDistance}
                  onChange={handleChange('maintenanceDistance')}
                  className="w-32 px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <span className="text-xs text-slate-400">
                  Trigger maintenance reminder after this cumulative distance
                </span>
              </div>
            </div>

            {/* Overspeed */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Overspeed Alert (km/h)
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="number" min="1"
                  value={thresholds.overspeedKmh}
                  onChange={handleChange('overspeedKmh')}
                  className="w-32 px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <span className="text-xs text-slate-400">
                  Flag speed readings above this limit
                </span>
              </div>
            </div>

            {/* Reminder */}
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
              <p className="font-medium mb-1">Default thesis values</p>
              <p>Rest: <strong>6 h / 300 km</strong> · Maintenance: <strong>5,000 km</strong></p>
            </div>

            {/* Save */}
            <div className="flex items-center gap-3 pt-2">
              <button
                type="submit"
                className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
              >
                <Save className="w-4 h-4" />
                Save Thresholds
              </button>
              {savedOk && (
                <div className="flex items-center gap-1.5 text-green-600 text-sm font-medium">
                  <CheckCircle className="w-4 h-4" />
                  Saved successfully
                </div>
              )}
            </div>
          </form>
        </div>
      )}

      {/* ── USER MANAGEMENT ── */}
      {activeTab === 'users' && (
        <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6">
          <div className="mb-6">
            <h2 className="text-base font-semibold text-slate-900 mb-1">User Management</h2>
            <p className="text-sm text-slate-500">
              Add or remove admin users who can access this dashboard.
            </p>
          </div>

          {/* User list */}
          <div className="space-y-3 mb-6">
            {[
              { name: 'Admin User',  email: 'admin@fleet.com',  role: 'Administrator' },
              { name: 'Fleet Admin', email: 'fleet@sgsa.com',   role: 'Fleet Manager' },
            ].map(user => (
              <div key={user.email} className="flex items-center justify-between p-4 bg-slate-50 rounded-xl">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 bg-blue-100 rounded-full flex items-center justify-center">
                    <span className="text-sm font-semibold text-blue-600">
                      {user.name.charAt(0)}
                    </span>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-900">{user.name}</p>
                    <p className="text-xs text-slate-500">{user.email} · {user.role}</p>
                  </div>
                </div>
                <button className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>

          <button className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors">
            <UserPlus className="w-4 h-4" />
            Add User
          </button>
        </div>
      )}

      {/* ── FLEET SETTINGS ── */}
      {activeTab === 'fleet' && (
        <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6">
          <div className="mb-6">
            <h2 className="text-base font-semibold text-slate-900 mb-1">Fleet Settings</h2>
            <p className="text-sm text-slate-500">
              Add or remove trucks from the monitored fleet roster.
            </p>
          </div>

          <div className="space-y-3 mb-6">
            {[
              { id: 'TRK-001', name: 'Truck Alpha',   driver: 'Juan Dela Cruz' },
              { id: 'TRK-002', name: 'Truck Bravo',   driver: 'Maria Santos' },
              { id: 'TRK-003', name: 'Truck Charlie', driver: 'Roberto Garcia' },
              { id: 'TRK-004', name: 'Truck Delta',   driver: 'Ana Reyes' },
            ].map(truck => (
              <div key={truck.id} className="flex items-center justify-between p-4 bg-slate-50 rounded-xl">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 bg-slate-200 rounded-full flex items-center justify-center">
                    <Truck className="w-4 h-4 text-slate-600" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-900">{truck.name}</p>
                    <p className="text-xs text-slate-500">{truck.id} · {truck.driver}</p>
                  </div>
                </div>
                <button className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>

          <button className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors">
            <Truck className="w-4 h-4" />
            Add Truck
          </button>
        </div>
      )}
    </div>
  );
}
