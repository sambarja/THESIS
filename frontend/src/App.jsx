// App.js
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import { useState } from "react";
import { CTable } from '@coreui/react'

import './App.css';

import LoginSignUp from './components/LoginSignUp';
import MyNavbar from "./components/MyNavbar";
import Dashboard from "./components/Dashboard";
import Alerts from "./components/Alerts";
import Logs from "./components/Logs";
import Settings from "./components/Settings";

// Dummy credentials
const DUMMY_USER = {
  email: "user",
  password: "1234"
};

// Protected Route Component
const ProtectedRoute = ({ isLoggedIn, children }) => {
  if (!isLoggedIn) {
    return <Navigate to="/login" replace />;
  }
  return children;
};

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  return (
    <Router>
      {isLoggedIn && <MyNavbar />}
      <Routes>
        <Route
          path="/login"
          element={<LoginSignUp setIsLoggedIn={setIsLoggedIn} />}
        />

        <Route
          path="/"
          element={
            <ProtectedRoute isLoggedIn={isLoggedIn}>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/alerts"
          element={
            <ProtectedRoute isLoggedIn={isLoggedIn}>
              <Alerts />
            </ProtectedRoute>
          }
        />
        <Route
          path="/logs"
          element={
            <ProtectedRoute isLoggedIn={isLoggedIn}>
              <Logs />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings"
          element={
            <ProtectedRoute isLoggedIn={isLoggedIn}>
              <Settings />
            </ProtectedRoute>
          }
        />
        {/* Catch-all redirect to login */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </Router>
  );
}

export default App;
