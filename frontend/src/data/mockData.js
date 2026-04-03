// Mock data matching the Figma design — Philippines-based fleet
// Used as fallback when the backend API is unavailable

export const mockTrucks = [
  {
    id: 'TRK-001', name: 'Truck Alpha', driver: 'Juan Dela Cruz',
    status: 'active', position: [14.5995, 120.9842],
    fuel: 78, speed: 65, distance: 145.8, operatingHours: 3.5,
    tripStatus: 'active', tripStartTime: '2026-04-03T08:30:00',
    lastUpdate: '2026-04-03T12:15:00',
    route: [[14.5547,121.0244],[14.5695,121.0145],[14.5795,121.0045],[14.5895,120.9945],[14.5995,120.9842]],
  },
  {
    id: 'TRK-002', name: 'Truck Bravo', driver: 'Maria Santos',
    status: 'anomaly', position: [14.6091, 121.0223],
    fuel: 45, speed: 72, distance: 203.4, operatingHours: 5.2,
    tripStatus: 'active', tripStartTime: '2026-04-03T06:00:00',
    lastUpdate: '2026-04-03T12:10:00',
    route: [[14.5547,121.0644],[14.5747,121.0544],[14.5947,121.0344],[14.6091,121.0223]],
  },
  {
    id: 'TRK-003', name: 'Truck Charlie', driver: 'Roberto Garcia',
    status: 'low_fuel', position: [14.5764, 121.0851],
    fuel: 18, speed: 0, distance: 289.7, operatingHours: 7.8,
    tripStatus: 'active', tripStartTime: '2026-04-03T04:30:00',
    lastUpdate: '2026-04-03T12:18:00',
    route: [[14.5247,121.1044],[14.5447,121.0944],[14.5647,121.0894],[14.5764,121.0851]],
  },
  {
    id: 'TRK-004', name: 'Truck Delta', driver: 'Ana Reyes',
    status: 'rest_alert', position: [14.5378, 121.0199],
    fuel: 62, speed: 0, distance: 412.3, operatingHours: 9.1,
    tripStatus: 'active', tripStartTime: '2026-04-03T03:00:00',
    lastUpdate: '2026-04-03T12:05:00',
    route: [[14.4947,121.0444],[14.5147,121.0344],[14.5278,121.0244],[14.5378,121.0199]],
  },
  {
    id: 'TRK-005', name: 'Truck Echo', driver: 'Carlos Mendoza',
    status: 'maintenance', position: [14.5486, 121.0497],
    fuel: 85, speed: 0, distance: 156.2, operatingHours: 3.0,
    tripStatus: 'inactive', lastUpdate: '2026-04-03T11:45:00',
  },
  {
    id: 'TRK-006', name: 'Truck Foxtrot', driver: 'Linda Torres',
    status: 'idle', position: [14.5833, 120.9794],
    fuel: 92, speed: 0, distance: 0, operatingHours: 0,
    tripStatus: 'inactive', lastUpdate: '2026-04-03T10:30:00',
  },
  {
    id: 'TRK-007', name: 'Truck Golf', driver: 'Pedro Alvarez',
    status: 'active', position: [14.6504, 121.0494],
    fuel: 71, speed: 58, distance: 98.5, operatingHours: 2.3,
    tripStatus: 'active', tripStartTime: '2026-04-03T09:45:00',
    lastUpdate: '2026-04-03T12:20:00',
    route: [[14.6104,121.0694],[14.6304,121.0594],[14.6504,121.0494]],
  },
  {
    id: 'TRK-008', name: 'Truck Hotel', driver: 'Sofia Cruz',
    status: 'offline', position: [14.5243, 121.0792],
    fuel: 34, speed: 0, distance: 267.9, operatingHours: 6.2,
    tripStatus: 'inactive', lastUpdate: '2026-04-03T09:15:00',
  },
];

export const mockAlerts = [
  {
    id: 'ALT-001', truckId: 'TRK-002', truckName: 'Truck Bravo',
    type: 'anomaly', severity: 'high', resolved: false,
    message: 'Sudden fuel drop detected. Possible siphoning event.',
    timestamp: '2026-04-03T12:10:00',
  },
  {
    id: 'ALT-002', truckId: 'TRK-004', truckName: 'Truck Delta',
    type: 'rest', severity: 'high', resolved: false,
    message: 'Driver has been operating for 9+ hours. Rest period required.',
    timestamp: '2026-04-03T12:05:00',
  },
  {
    id: 'ALT-003', truckId: 'TRK-003', truckName: 'Truck Charlie',
    type: 'low_fuel', severity: 'medium', resolved: false,
    message: 'ECU-derived fuel level below 20%. Refueling recommended.',
    timestamp: '2026-04-03T12:18:00',
  },
  {
    id: 'ALT-004', truckId: 'TRK-005', truckName: 'Truck Echo',
    type: 'maintenance', severity: 'medium', resolved: false,
    message: 'Vehicle has exceeded 5,000 km maintenance threshold.',
    timestamp: '2026-04-03T11:45:00',
  },
  {
    id: 'ALT-005', truckId: 'TRK-002', truckName: 'Truck Bravo',
    type: 'anomaly', severity: 'medium', resolved: true,
    message: 'Abnormal fuel consumption rate detected (Matrix Profile).',
    timestamp: '2026-04-03T10:30:00',
  },
  {
    id: 'ALT-006', truckId: 'TRK-001', truckName: 'Truck Alpha',
    type: 'anomaly', severity: 'low', resolved: true,
    message: 'Minor speed deviation flagged by Isolation Forest.',
    timestamp: '2026-04-03T09:15:00',
  },
];

export const mockTelemetryLogs = [
  { id: 'LOG-001', timestamp: '2026-04-03T12:20:00', truckId: 'TRK-007', truckName: 'Truck Golf', fuel: 71, latitude: 14.6504, longitude: 121.0494, speed: 58, anomaly: false, tripStatus: 'active' },
  { id: 'LOG-002', timestamp: '2026-04-03T12:18:00', truckId: 'TRK-003', truckName: 'Truck Charlie', fuel: 18, latitude: 14.5764, longitude: 121.0851, speed: 0, anomaly: false, tripStatus: 'active' },
  { id: 'LOG-003', timestamp: '2026-04-03T12:15:00', truckId: 'TRK-001', truckName: 'Truck Alpha', fuel: 78, latitude: 14.5995, longitude: 120.9842, speed: 65, anomaly: false, tripStatus: 'active' },
  { id: 'LOG-004', timestamp: '2026-04-03T12:10:00', truckId: 'TRK-002', truckName: 'Truck Bravo', fuel: 45, latitude: 14.6091, longitude: 121.0223, speed: 72, anomaly: true, tripStatus: 'active' },
  { id: 'LOG-005', timestamp: '2026-04-03T12:05:00', truckId: 'TRK-004', truckName: 'Truck Delta', fuel: 62, latitude: 14.5378, longitude: 121.0199, speed: 0, anomaly: false, tripStatus: 'active' },
  { id: 'LOG-006', timestamp: '2026-04-03T11:45:00', truckId: 'TRK-005', truckName: 'Truck Echo', fuel: 85, latitude: 14.5486, longitude: 121.0497, speed: 0, anomaly: false, tripStatus: 'inactive' },
  { id: 'LOG-007', timestamp: '2026-04-03T11:30:00', truckId: 'TRK-001', truckName: 'Truck Alpha', fuel: 82, latitude: 14.5795, longitude: 121.0045, speed: 68, anomaly: false, tripStatus: 'active' },
  { id: 'LOG-008', timestamp: '2026-04-03T11:15:00', truckId: 'TRK-002', truckName: 'Truck Bravo', fuel: 48, latitude: 14.5947, longitude: 121.0344, speed: 70, anomaly: false, tripStatus: 'active' },
];

export const adminLocation = [14.5764, 121.0514]; // Pasig area
