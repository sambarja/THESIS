import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useState } from 'react';

import Layout       from './components/Layout';
import LoginSignUp  from './components/LoginSignUp';
import Dashboard    from './components/Dashboard';
import MapView      from './components/MapView';
import Trucks       from './components/Trucks';
import Alerts       from './components/Alerts';
import Logs         from './components/Logs';
import Analytics    from './components/Analytics';
import Settings     from './components/Settings';

function ProtectedLayout({ isLoggedIn, setIsLoggedIn }) {
  if (!isLoggedIn) return <Navigate to="/login" replace />;
  return <Layout setIsLoggedIn={setIsLoggedIn} />;
}

export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  return (
    <Router>
      <Routes>
        <Route path="/login" element={<LoginSignUp setIsLoggedIn={setIsLoggedIn} />} />

        <Route element={<ProtectedLayout isLoggedIn={isLoggedIn} setIsLoggedIn={setIsLoggedIn} />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/map"       element={<MapView />} />
          <Route path="/trucks"    element={<Trucks />} />
          <Route path="/alerts"    element={<Alerts />} />
          <Route path="/logs"      element={<Logs />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings"  element={<Settings />} />
        </Route>

        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </Router>
  );
}
