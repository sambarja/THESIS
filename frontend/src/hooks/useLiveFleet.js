import { useState, useEffect, useCallback, useRef } from 'react';
import { apiFetch, normalizeTruck } from '../utils/api';

const FLEET_POLL_MS = 10_000;  // re-fetch positions + fuel every 10 s

/**
 * Polls /fleet/status every 10 s and, for each truck with an active trip,
 * fetches the GPS route polyline from /trips/:id/route.
 *
 * Returns trucks with a `route` field: [[lat, lon], ...] for active trips.
 */
export function useLiveFleet() {
  const [trucks,  setTrucks]  = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  // Cache routes by trip_id so we don't flicker on every poll cycle
  const routeCache = useRef({});

  const fetchFleet = useCallback(async () => {
    try {
      const raw        = await apiFetch('/fleet/status');
      const normalized = raw.map(normalizeTruck);

      // 1. Immediately update positions / fuel using cached routes
      setTrucks(normalized.map(t => ({
        ...t,
        route: t.tripId ? (routeCache.current[t.tripId] ?? []) : [],
      })));
      setError(null);

      // 2. Fetch fresh route data for all active trips (non-blocking)
      const active = normalized.filter(t => t.tripId && t.tripStatus === 'active');
      if (active.length > 0) {
        await Promise.all(active.map(async (truck) => {
          try {
            const pts = await apiFetch(`/trips/${truck.tripId}/route`);
            routeCache.current[truck.tripId] = pts
              .filter(p => p.lat != null && p.lon != null)
              .map(p => [p.lat, p.lon]);
          } catch {
            // Route fetch failed — keep cached value, don't crash
          }
        }));

        // 3. Re-apply updated routes
        setTrucks(prev => prev.map(t => ({
          ...t,
          route: t.tripId ? (routeCache.current[t.tripId] ?? []) : [],
        })));
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFleet();
    const id = setInterval(fetchFleet, FLEET_POLL_MS);
    return () => clearInterval(id);
  }, [fetchFleet]);

  return { trucks, loading, error, refetch: fetchFleet };
}
