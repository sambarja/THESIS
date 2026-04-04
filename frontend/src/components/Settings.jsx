import { useState, useEffect } from 'react';
import { Save, UserPlus, Trash2, Truck, Bell, Shield, CheckCircle, RefreshCw, AlertTriangle } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { useApi } from '../hooks/useApi';

const tabs = [
  { id: 'thresholds', label: 'Alert Thresholds', icon: Bell },
  { id: 'users',      label: 'User Management',  icon: Shield },
  { id: 'fleet',      label: 'Fleet Settings',   icon: Truck },
];

const ROLE_LABELS = {
  head_admin:    'Head Admin',
  fleet_manager: 'Fleet Manager',
  manager:       'Manager',
  driver:        'Driver',
};

// ── THRESHOLDS TAB ────────────────────────────────────────────
function ThresholdsTab() {
  const [saving,    setSaving]    = useState(false);
  const [savedOk,   setSavedOk]   = useState(false);
  const [saveError, setSaveError] = useState('');
  const [thresholds, setThresholds] = useState(null);

  const { data, loading, error, refetch } = useApi('/settings/thresholds');

  // Populate form once data loads
  useEffect(() => {
    if (data && !thresholds) {
      setThresholds({
        restHours:           String(data.rest_hours           ?? '6'),
        restDistance:        String(data.rest_distance_km     ?? '300'),
        maintenanceDistance: String(data.maintenance_km       ?? '5000'),
        overspeedKmh:        String(data.overspeed_kmh        ?? '100'),
      });
    }
  }, [data, thresholds]);

  const handleChange = (field) => (e) => {
    setThresholds(prev => ({ ...prev, [field]: e.target.value }));
    setSavedOk(false);
    setSaveError('');
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSaveError('');
    try {
      await apiFetch('/settings/thresholds', {
        method: 'PUT',
        body: JSON.stringify({
          rest_hours:        Number(thresholds.restHours),
          rest_distance_km:  Number(thresholds.restDistance),
          maintenance_km:    Number(thresholds.maintenanceDistance),
          overspeed_kmh:     Number(thresholds.overspeedKmh),
        }),
      });
      setSavedOk(true);
      setTimeout(() => setSavedOk(false), 3000);
      refetch();
    } catch (err) {
      setSaveError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading || !thresholds) return (
    <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6">
      <p className="text-sm text-slate-400">{error ?? 'Loading thresholds…'}</p>
    </div>
  );

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6">
      <div className="mb-6">
        <h2 className="text-base font-semibold text-slate-900 mb-1">Alert Thresholds</h2>
        <p className="text-sm text-slate-500">
          Fine-tune when rest alerts, maintenance reminders, and overspeed warnings trigger.
        </p>
      </div>

      <form onSubmit={handleSave} className="space-y-5">
        {[
          { field: 'restHours',           label: 'Rest Alert — Hours (h)',          min: 1, max: 24, hint: 'Alert driver after this many hours of continuous operation' },
          { field: 'restDistance',        label: 'Rest Alert — Distance (km)',      min: 1,          hint: 'Alert driver after this many kilometres without rest' },
          { field: 'maintenanceDistance', label: 'Maintenance Alert — Distance (km)', min: 1,        hint: 'Trigger maintenance reminder after this cumulative distance' },
          { field: 'overspeedKmh',        label: 'Overspeed Alert (km/h)',          min: 1,          hint: 'Flag speed readings above this limit' },
        ].map(({ field, label, min, max, hint }) => (
          <div key={field}>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">{label}</label>
            <div className="flex items-center gap-3">
              <input
                type="number" min={min} max={max}
                value={thresholds[field]}
                onChange={handleChange(field)}
                className="w-32 px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <span className="text-xs text-slate-400">{hint}</span>
            </div>
          </div>
        ))}

        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
          <p className="font-medium mb-1">Default thesis values</p>
          <p>Rest: <strong>6 h / 300 km</strong> · Maintenance: <strong>5,000 km</strong></p>
        </div>

        {saveError && (
          <div className="flex items-center gap-2 text-sm text-red-600">
            <AlertTriangle className="w-4 h-4" />
            {saveError}
          </div>
        )}

        <div className="flex items-center gap-3 pt-2">
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {saving ? 'Saving…' : 'Save Thresholds'}
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
  );
}

// Role badge styling
const ROLE_BADGE = {
  head_admin:    'bg-purple-100 text-purple-700',
  fleet_manager: 'bg-blue-100 text-blue-700',
  manager:       'bg-indigo-100 text-indigo-700',
  driver:        'bg-green-100 text-green-700',
};

// ── USERS TAB ─────────────────────────────────────────────────
function UsersTab() {
  const EMPTY_FORM = { full_name: '', username: '', password: '', role: 'fleet_manager' };
  const [showAdd,  setShowAdd]  = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [toggling, setToggling] = useState(null);
  const [addError, setAddError] = useState('');
  const [addForm,  setAddForm]  = useState(EMPTY_FORM);

  const { data: users, loading, error, refetch } = useApi('/settings/users');

  const adminUsers  = (users ?? []).filter(u => u.role !== 'driver');
  const driverUsers = (users ?? []).filter(u => u.role === 'driver');

  const handleDelete = async (id) => {
    if (!window.confirm('Remove this user? This cannot be undone.')) return;
    setDeleting(id);
    try {
      await apiFetch(`/settings/users/${id}`, { method: 'DELETE' });
      refetch();
    } catch (err) {
      alert(err.message);
    } finally {
      setDeleting(null);
    }
  };

  const handleToggleActive = async (user) => {
    setToggling(user.id);
    try {
      await apiFetch(`/settings/users/${user.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !user.is_active }),
      });
      refetch();
    } catch (err) {
      alert(err.message);
    } finally {
      setToggling(null);
    }
  };

  const handleAdd = async (e) => {
    e.preventDefault();
    setAddError('');
    try {
      await apiFetch('/settings/users', {
        method: 'POST',
        body: JSON.stringify(addForm),
      });
      setShowAdd(false);
      setAddForm(EMPTY_FORM);
      refetch();
    } catch (err) {
      setAddError(err.message);
    }
  };

  const UserRow = ({ user }) => (
    <div key={user.id} className={`flex items-center justify-between p-4 rounded-xl ${user.is_active ? 'bg-slate-50' : 'bg-slate-100 opacity-60'}`}>
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-9 h-9 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
          <span className="text-sm font-semibold text-blue-600">{user.full_name.charAt(0).toUpperCase()}</span>
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-medium text-slate-900">{user.full_name}</p>
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${ROLE_BADGE[user.role] ?? 'bg-slate-100 text-slate-600'}`}>
              {ROLE_LABELS[user.role] ?? user.role}
            </span>
            {!user.is_active && <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-600">Deactivated</span>}
          </div>
          <p className="text-xs text-slate-500 mt-0.5">@{user.username}</p>
        </div>
      </div>
      <div className="flex items-center gap-1 flex-shrink-0 ml-2">
        <button
          onClick={() => handleToggleActive(user)}
          disabled={toggling === user.id || user.role === 'head_admin'}
          title={user.is_active ? 'Deactivate' : 'Reactivate'}
          className="p-2 text-slate-400 hover:text-amber-500 hover:bg-amber-50 rounded-lg transition-colors disabled:opacity-40"
        >
          {toggling === user.id
            ? <RefreshCw className="w-4 h-4 animate-spin" />
            : <Shield className="w-4 h-4" />}
        </button>
        <button
          onClick={() => handleDelete(user.id)}
          disabled={deleting === user.id || user.role === 'head_admin'}
          title="Delete user"
          className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-40"
        >
          {deleting === user.id
            ? <RefreshCw className="w-4 h-4 animate-spin" />
            : <Trash2 className="w-4 h-4" />}
        </button>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      {/* Admin-side users */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6">
        <div className="mb-4">
          <h2 className="text-base font-semibold text-slate-900 mb-1">Dashboard Users</h2>
          <p className="text-sm text-slate-500">Admin accounts that can access this dashboard (fleet managers, managers).</p>
        </div>

        {error && <p className="text-sm text-red-600 mb-4">{error}</p>}

        <div className="space-y-3 mb-4">
          {loading ? (
            <p className="text-sm text-slate-400">Loading users…</p>
          ) : adminUsers.length === 0 ? (
            <p className="text-sm text-slate-400">No admin users found</p>
          ) : adminUsers.map(user => <UserRow key={user.id} user={user} />)}
        </div>
      </div>

      {/* Driver accounts */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6">
        <div className="mb-4">
          <h2 className="text-base font-semibold text-slate-900 mb-1">Driver Accounts</h2>
          <p className="text-sm text-slate-500">Driver accounts for truck-device login only. Drivers cannot access this dashboard.</p>
        </div>

        <div className="space-y-3 mb-4">
          {loading ? (
            <p className="text-sm text-slate-400">Loading drivers…</p>
          ) : driverUsers.length === 0 ? (
            <p className="text-sm text-slate-400">No driver accounts found</p>
          ) : driverUsers.map(user => <UserRow key={user.id} user={user} />)}
        </div>
      </div>

      {/* Add user form */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6">
        <h2 className="text-base font-semibold text-slate-900 mb-4">Add Account</h2>
        {showAdd ? (
          <form onSubmit={handleAdd} className="space-y-3">
            {addError && <p className="text-xs text-red-600 bg-red-50 px-3 py-2 rounded-lg">{addError}</p>}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Full Name</label>
                <input required placeholder="e.g. Juan Dela Cruz" value={addForm.full_name}
                  onChange={e => setAddForm(f => ({ ...f, full_name: e.target.value }))}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Username</label>
                <input required placeholder="e.g. juandc" value={addForm.username}
                  onChange={e => setAddForm(f => ({ ...f, username: e.target.value }))}
                  autoCapitalize="none"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Password</label>
                <input required type="password" placeholder="Set a password" value={addForm.password}
                  onChange={e => setAddForm(f => ({ ...f, password: e.target.value }))}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Role</label>
                <select value={addForm.role} onChange={e => setAddForm(f => ({ ...f, role: e.target.value }))}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                  <option value="fleet_manager">Fleet Manager (dashboard)</option>
                  <option value="manager">Manager (dashboard)</option>
                  <option value="driver">Driver (truck device only)</option>
                </select>
              </div>
            </div>
            {addForm.role === 'driver' && (
              <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                Driver accounts can only log in from the truck-side device. They cannot access this dashboard.
              </p>
            )}
            <div className="flex gap-2 pt-1">
              <button type="submit"
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors">
                Add Account
              </button>
              <button type="button" onClick={() => { setShowAdd(false); setAddError(''); setAddForm(EMPTY_FORM); }}
                className="px-4 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 text-sm font-medium rounded-lg transition-colors">
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <button onClick={() => setShowAdd(true)}
            className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors">
            <UserPlus className="w-4 h-4" />
            Add Account
          </button>
        )}
      </div>
    </div>
  );
}

// ── FLEET TAB ─────────────────────────────────────────────────
function FleetTab() {
  const [showAdd,  setShowAdd]  = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [addError, setAddError] = useState('');
  const [addForm,  setAddForm]  = useState({ truck_code: '', plate_number: '', model: '' });

  const { data: trucks, loading, error, refetch } = useApi('/trucks');

  const handleDelete = async (id) => {
    if (!window.confirm('Remove this truck from the fleet?')) return;
    setDeleting(id);
    try {
      await apiFetch(`/trucks/${id}`, { method: 'DELETE' });
      refetch();
    } catch (err) {
      alert(err.message);
    } finally {
      setDeleting(null);
    }
  };

  const handleAdd = async (e) => {
    e.preventDefault();
    setAddError('');
    try {
      await apiFetch('/trucks', {
        method: 'POST',
        body: JSON.stringify(addForm),
      });
      setShowAdd(false);
      setAddForm({ truck_code: '', plate_number: '', model: '' });
      refetch();
    } catch (err) {
      setAddError(err.message);
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6">
      <div className="mb-6">
        <h2 className="text-base font-semibold text-slate-900 mb-1">Fleet Settings</h2>
        <p className="text-sm text-slate-500">Add or remove trucks from the monitored fleet roster.</p>
      </div>

      {error && <p className="text-sm text-red-600 mb-4">{error}</p>}

      <div className="space-y-3 mb-6">
        {loading ? (
          <p className="text-sm text-slate-400">Loading trucks…</p>
        ) : (trucks ?? []).length === 0 ? (
          <p className="text-sm text-slate-400">No trucks in fleet</p>
        ) : (trucks ?? []).map(truck => (
          <div key={truck.id} className="flex items-center justify-between p-4 bg-slate-50 rounded-xl">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 bg-slate-200 rounded-full flex items-center justify-center">
                <Truck className="w-4 h-4 text-slate-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-slate-900">
                  {truck.model ?? truck.truck_code}
                </p>
                <p className="text-xs text-slate-500">
                  {truck.truck_code} · {truck.plate_number}
                  {truck.driver && <span> · {truck.driver.full_name}</span>}
                </p>
              </div>
            </div>
            <button
              onClick={() => handleDelete(truck.id)}
              disabled={deleting === truck.id}
              className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-40"
            >
              {deleting === truck.id
                ? <RefreshCw className="w-4 h-4 animate-spin" />
                : <Trash2 className="w-4 h-4" />}
            </button>
          </div>
        ))}
      </div>

      {showAdd ? (
        <form onSubmit={handleAdd} className="bg-slate-50 rounded-xl p-4 space-y-3">
          <p className="text-sm font-medium text-slate-900">New Truck</p>
          {addError && <p className="text-xs text-red-600">{addError}</p>}
          <input required placeholder="Truck code (e.g. TRK-005)" value={addForm.truck_code}
            onChange={e => setAddForm(f => ({ ...f, truck_code: e.target.value }))}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          <input required placeholder="Plate number" value={addForm.plate_number}
            onChange={e => setAddForm(f => ({ ...f, plate_number: e.target.value }))}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          <input placeholder="Model (optional)" value={addForm.model}
            onChange={e => setAddForm(f => ({ ...f, model: e.target.value }))}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          <div className="flex gap-2">
            <button type="submit"
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors">
              Add Truck
            </button>
            <button type="button" onClick={() => { setShowAdd(false); setAddError(''); }}
              className="px-4 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 text-sm font-medium rounded-lg transition-colors">
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <button onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors">
          <Truck className="w-4 h-4" />
          Add Truck
        </button>
      )}
    </div>
  );
}

// ── MAIN SETTINGS ─────────────────────────────────────────────
export default function Settings() {
  const [activeTab, setActiveTab] = useState('thresholds');

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

      {activeTab === 'thresholds' && <ThresholdsTab />}
      {activeTab === 'users'      && <UsersTab />}
      {activeTab === 'fleet'      && <FleetTab />}
    </div>
  );
}
