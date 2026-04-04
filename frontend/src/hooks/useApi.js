import { useState, useEffect, useCallback, useRef } from 'react';
import { apiFetch } from '../utils/api';

/**
 * Simple data-fetching hook with loading / error states.
 *
 * Options:
 *   transform    — function applied to the raw result before storing
 *   pollInterval — ms between auto-refetches (omit to disable polling)
 */
export function useApi(path, { transform, pollInterval } = {}) {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(!!path);
  const [error,   setError]   = useState(null);

  const transformRef = useRef(transform);
  transformRef.current = transform;

  const load = useCallback(async () => {
    if (!path) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await apiFetch(path);
      setData(transformRef.current ? transformRef.current(result) : result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [path]);

  // Initial fetch
  useEffect(() => { load(); }, [load]);

  // Optional polling
  useEffect(() => {
    if (!pollInterval) return;
    const id = setInterval(load, pollInterval);
    return () => clearInterval(id);
  }, [load, pollInterval]);

  return { data, loading, error, refetch: load };
}
