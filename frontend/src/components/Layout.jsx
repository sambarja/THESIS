import { useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useApi } from '../hooks/useApi';
import {
  LayoutDashboard, Map, Truck, Bell, ScrollText,
  BarChart3, Route, Menu, X, LogOut, User, Settings,
} from 'lucide-react';

// Navigation items visible to ALL dashboard roles
const BASE_NAV = [
  { path: '/dashboard',  icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/map',        icon: Map,              label: 'Live Map' },
  { path: '/trucks',     icon: Truck,            label: 'Trucks' },
  { path: '/alerts',     icon: Bell,             label: 'Alerts' },
  { path: '/logs',       icon: ScrollText,       label: 'Logs' },
  { path: '/analytics',  icon: BarChart3,        label: 'Analytics' },
  { path: '/trips',      icon: Route,            label: 'Trips' },
];

// Settings only for head_admin
const SETTINGS_NAV = { path: '/settings', icon: Settings, label: 'Settings' };

// Human-readable role labels
const ROLE_LABELS = {
  head_admin:    'Head Administrator',
  fleet_manager: 'Fleet Manager',
  manager:       'Manager',
  driver:        'Driver',
};

export default function Layout({ user, setUser }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();

  // Live unresolved alert count for bell badge
  const { data: unresolvedAlerts } = useApi('/alerts/summary', {
    transform: data => data.unresolved_count ?? 0,
    pollInterval: 30_000,
  });

  // Build nav list — Settings only appears for head_admin
  const navItems = user?.role === 'head_admin'
    ? [...BASE_NAV, SETTINGS_NAV]
    : BASE_NAV;

  const handleLogout = () => {
    setUser(null);
    navigate('/login');
  };

  const NavList = ({ onClick }) => (
    <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
      {navItems.map((item) => (
        <NavLink
          key={item.path}
          to={item.path}
          onClick={onClick}
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-sm ${
              isActive
                ? 'bg-blue-600 text-white'
                : 'text-slate-300 hover:bg-slate-800 hover:text-white'
            }`
          }
        >
          <item.icon className="w-5 h-5 flex-shrink-0" />
          <span>{item.label}</span>
        </NavLink>
      ))}
    </nav>
  );

  const UserFooter = () => (
    <div className="px-3 py-4 border-t border-slate-800">
      <div className="flex items-center gap-3 px-3 py-2 mb-1 min-w-0">
        <div className="flex items-center justify-center w-9 h-9 bg-slate-700 rounded-full flex-shrink-0">
          <User className="w-4 h-4 text-slate-300" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-white truncate">{user?.full_name ?? 'Admin User'}</p>
          <p className="text-xs text-slate-400 truncate">{ROLE_LABELS[user?.role] ?? user?.role}</p>
        </div>
      </div>
      <button
        onClick={handleLogout}
        className="flex items-center gap-2 w-full px-3 py-2 text-sm text-slate-300 hover:bg-slate-800 hover:text-white rounded-lg transition-colors"
      >
        <LogOut className="w-4 h-4" />
        <span>Logout</span>
      </button>
    </div>
  );

  const Logo = () => (
    <div className="flex items-center gap-3 px-6 py-5 border-b border-slate-800">
      <div className="flex items-center justify-center w-10 h-10 bg-blue-600 rounded-lg flex-shrink-0">
        <Truck className="w-6 h-6 text-white" />
      </div>
      <div className="min-w-0">
        <h1 className="text-lg font-semibold text-white leading-tight">FleetMonitor</h1>
        <p className="text-xs text-slate-400">Admin Dashboard</p>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">

      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex lg:flex-col w-64 bg-slate-900 flex-shrink-0">
        <Logo />
        <NavList />
        <UserFooter />
      </aside>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Mobile Sidebar */}
      <aside
        className={`fixed top-0 left-0 bottom-0 w-64 bg-slate-900 z-50 flex flex-col transform transition-transform duration-300 lg:hidden ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between px-6 py-5 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 bg-blue-600 rounded-lg">
              <Truck className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-white">FleetMonitor</h1>
              <p className="text-xs text-slate-400">Admin Dashboard</p>
            </div>
          </div>
          <button onClick={() => setSidebarOpen(false)} className="p-1 hover:bg-slate-800 rounded-lg">
            <X className="w-5 h-5 text-slate-300" />
          </button>
        </div>
        <NavList onClick={() => setSidebarOpen(false)} />
        <UserFooter />
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Bar */}
        <header className="bg-white border-b border-slate-200 px-4 lg:px-6 py-3 sm:py-4 flex-shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSidebarOpen(true)}
                className="lg:hidden p-2 hover:bg-slate-100 rounded-lg"
              >
                <Menu className="w-5 h-5 text-slate-600" />
              </button>
              <h2 className="text-lg sm:text-xl font-semibold text-slate-900 truncate">
                Fleet Monitoring Dashboard
              </h2>
            </div>
            <div className="flex items-center gap-2 sm:gap-3">
              <button
                onClick={() => navigate('/alerts')}
                className="relative p-2 hover:bg-slate-100 rounded-lg transition-colors"
                title="View Alerts"
              >
                <Bell className="w-5 h-5 text-slate-600" />
                {unresolvedAlerts > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center px-1">
                    {unresolvedAlerts > 99 ? '99+' : unresolvedAlerts}
                  </span>
                )}
              </button>
              <div className="hidden md:flex items-center gap-3 pl-3 border-l border-slate-200">
                <div className="flex items-center justify-center w-9 h-9 bg-slate-200 rounded-full">
                  <User className="w-5 h-5 text-slate-600" />
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-900">{user?.full_name ?? 'Admin'}</p>
                  <p className="text-xs text-slate-500">{ROLE_LABELS[user?.role] ?? user?.role}</p>
                </div>
              </div>
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
