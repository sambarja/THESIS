export function getStatusColor(status) {
  switch (status) {
    case 'active':      return 'bg-green-500';
    case 'idle':        return 'bg-gray-400';
    case 'anomaly':     return 'bg-red-500';
    case 'maintenance': return 'bg-orange-500';
    case 'rest_alert':  return 'bg-amber-500';
    case 'low_fuel':    return 'bg-yellow-500';
    case 'offline':     return 'bg-slate-600';
    case 'paused':      return 'bg-amber-400';
    default:            return 'bg-gray-400';
  }
}

export function getStatusLabel(status) {
  switch (status) {
    case 'active':      return 'Active Trip';
    case 'idle':        return 'Idle';
    case 'anomaly':     return 'Anomaly Detected';
    case 'maintenance': return 'Maintenance Due';
    case 'rest_alert':  return 'Rest Required';
    case 'low_fuel':    return 'Low Fuel';
    case 'offline':     return 'Offline';
    case 'paused':      return 'Driver Resting';
    default:            return 'Unknown';
  }
}

// Returns hex color for Leaflet markers
export function getStatusHex(status) {
  switch (status) {
    case 'active':      return '#22c55e';
    case 'idle':        return '#9ca3af';
    case 'anomaly':     return '#ef4444';
    case 'maintenance': return '#f97316';
    case 'rest_alert':  return '#f59e0b';
    case 'low_fuel':    return '#eab308';
    case 'offline':     return '#475569';
    default:            return '#9ca3af';
  }
}
