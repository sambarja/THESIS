import React, { useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet';
import L from 'leaflet';
import { getStatusHex } from '../utils/statusColors';

// Fix Leaflet default icon broken path with Vite
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl:       'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl:     'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

// ── Calls invalidateSize() whenever the map's DOM container changes size ──────
// This is the critical fix: Leaflet doesn't know the container resized on its own.
function MapResizeHandler() {
  const map = useMap();
  useEffect(() => {
    const container = map.getContainer();
    const ro = new ResizeObserver(() => {
      map.invalidateSize({ animate: false });
    });
    ro.observe(container);
    return () => ro.disconnect();
  }, [map]);
  return null;
}

// ── Pan + zoom to a selected truck when selectedTruckId changes ───────────────
function PanToSelected({ trucks, selectedTruckId }) {
  const map = useMap();
  useEffect(() => {
    if (!selectedTruckId) return;
    const truck = trucks.find(t => t.id === selectedTruckId);
    if (truck) {
      map.flyTo(truck.position, 15, { animate: true, duration: 0.75 });
    }
  }, [selectedTruckId, trucks, map]);
  return null;
}

// ── Auto-fit all trucks + admin into view ─────────────────────────────────────
function FitBounds({ trucks, adminLocation }) {
  const map = useMap();
  useEffect(() => {
    const points = trucks.map(t => t.position);
    if (adminLocation) points.push(adminLocation);
    if (points.length > 0) {
      map.fitBounds(L.latLngBounds(points), { padding: [40, 40], maxZoom: 14 });
    }
  }, [trucks, adminLocation, map]);
  return null;
}

function createTruckIcon(color, isSelected) {
  const size = isSelected ? 44 : 36;
  return L.divIcon({
    html: `
      <div style="
        width:${size}px;height:${size}px;
        background:${color};
        border-radius:50%;
        border:3px solid white;
        box-shadow:0 2px 8px rgba(0,0,0,0.35);
        display:flex;align-items:center;justify-content:center;
        ${isSelected ? `outline:3px solid ${color};outline-offset:3px;` : ''}
      ">
        <svg width="${size * 0.48}" height="${size * 0.48}" fill="none" stroke="white" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round"
            d="M9 17a2 2 0 11-4 0 2 2 0 014 0zM19 17a2 2 0 11-4 0 2 2 0 014 0z"/>
          <path stroke-linecap="round" stroke-linejoin="round"
            d="M13 16V6h4l2 4v6h-2M9 6H5v10h2"/>
        </svg>
      </div>`,
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -(size / 2 + 4)],
  });
}

function createAdminIcon() {
  return L.divIcon({
    html: `
      <div style="
        width:32px;height:32px;background:#7c3aed;
        border-radius:50%;border:3px solid white;
        box-shadow:0 2px 8px rgba(0,0,0,0.3);
        display:flex;align-items:center;justify-content:center;
      ">
        <svg width="14" height="14" fill="none" stroke="white" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round"
            d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
        </svg>
      </div>`,
    className: '',
    iconSize: [32, 32],
    iconAnchor: [16, 16],
    popupAnchor: [0, -20],
  });
}

export default function FleetMap({
  trucks = [],
  selectedTruckId = null,
  onTruckSelect,
  showAdminLocation = false,
  adminLocation,
  singleTruck = false,
}) {
  const center = trucks.length > 0 ? trucks[0].position : [14.5995, 121.0000];

  return (
    <MapContainer
      center={center}
      zoom={singleTruck ? 14 : 12}
      className="w-full h-full"
      style={{ minHeight: '100%' }}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution="© OpenStreetMap contributors"
        maxZoom={19}
      />

      {/* Always watch for resize and call invalidateSize */}
      <MapResizeHandler />

      {/* Fit all markers into view on first render */}
      {!singleTruck && <FitBounds trucks={trucks} adminLocation={adminLocation} />}

      {/* Pan to whichever truck the user clicked */}
      <PanToSelected trucks={trucks} selectedTruckId={selectedTruckId} />

      {/* Admin marker */}
      {showAdminLocation && adminLocation && (
        <Marker position={adminLocation} icon={createAdminIcon()}>
          <Popup>
            <div className="text-sm font-semibold">Admin Location</div>
            <div className="text-xs text-slate-500">Current position</div>
          </Popup>
        </Marker>
      )}

      {/* Truck markers + route polylines */}
      {trucks.map((truck) => {
        const color      = getStatusHex(truck.status);
        const isSelected = selectedTruckId === truck.id;
        return (
          // Fragment keeps react-leaflet happy — no plain DOM wrapper around map layers
          <React.Fragment key={truck.id}>
            {truck.route && truck.route.length > 1 && (
              <>
                {/* Faint halo for contrast on light tiles */}
                <Polyline
                  positions={truck.route}
                  pathOptions={{ color: '#ffffff', weight: 7, opacity: 0.55 }}
                />
                {/* Main route line */}
                <Polyline
                  positions={truck.route}
                  pathOptions={{ color, weight: 4, opacity: 0.9 }}
                />
              </>
            )}
            <Marker
              position={truck.position}
              icon={createTruckIcon(color, isSelected)}
              eventHandlers={{ click: () => onTruckSelect?.(truck.id) }}
            >
              <Popup>
                <div style={{ minWidth: 180 }}>
                  <p style={{ fontWeight: 600, fontSize: 13, color: '#0f172a', marginBottom: 2 }}>{truck.name}</p>
                  <p style={{ fontSize: 11, color: '#64748b', marginBottom: 8 }}>{truck.driver}</p>
                  <div style={{ fontSize: 11, color: '#334155', lineHeight: 1.8 }}>
                    <p><b>Status:</b> {truck.status}</p>
                    <p><b>Speed:</b>  {truck.speed} km/h</p>
                    <p><b>Fuel:</b>   {truck.fuel}%</p>
                    <p><b>Distance:</b> {truck.distance} km</p>
                  </div>
                </div>
              </Popup>
            </Marker>
          </React.Fragment>
        );
      })}
    </MapContainer>
  );
}
