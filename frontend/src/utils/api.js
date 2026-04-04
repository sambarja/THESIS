/**
 * Thin wrapper around fetch that automatically injects
 * the Authorization: Bearer {user_id} header for every
 * request to the backend.
 *
 * Usage:
 *   import { apiFetch } from '../utils/api';
 *   const data = await apiFetch('/fleet/status');
 */

const API = import.meta.env.VITE_API_URL || 'http://localhost:5000';

function getToken() {
  try {
    const u = JSON.parse(localStorage.getItem('fleet_user'));
    return u?.user_id ?? null;
  } catch {
    return null;
  }
}

export async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers ?? {}),
  };

  const res = await fetch(`${API}${path}`, { ...options, headers });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(body.error || `HTTP ${res.status}`);
  }

  return res.json();
}
