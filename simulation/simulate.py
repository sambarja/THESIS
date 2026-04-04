"""
SO2 / SO3 / SO4 / SO5 — Fleet Simulation Pipeline (v2)
=======================================================
Generates realistic truck telemetry and POSTs it to the backend
using the new schema (trucks / trip_sessions / telemetry_logs).

Features:
  - Multiple trucks with real Supabase UUIDs
  - Auto start/end trip sessions via API
  - Realistic Philippine GPS routes (Manila-area base)
  - 5-second GPS update intervals (SO3 requirement)
  - Normal + anomaly scenarios (theft, leak, overspeed)
  - SO2-c: records sent_at for latency benchmarking
  - Outputs simulation log CSV for thesis documentation

Usage:
    pip install requests
    python simulate.py --dry-run            # print without posting
    python simulate.py                      # post to http://localhost:5000
    python simulate.py --scenario theft
    python simulate.py --duration 120       # run for 120 seconds then stop

After running seed.js, use the exact UUIDs from Supabase:
    python simulate.py \\
      --truck-ids  "11111111-0000-0000-0000-000000000001,11111111-0000-0000-0000-000000000002" \\
      --driver-ids "22222222-0000-0000-0000-000000000002,22222222-0000-0000-0000-000000000003"
"""

import time
import math
import random
import argparse
import csv
import os
from datetime import datetime, timezone

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False
    print("[simulate] WARNING: 'requests' not installed — dry-run only.")

# ── Configuration ──────────────────────────────────────────────────────────────
BACKEND_URL    = 'http://localhost:5000'
GPS_INTERVAL_S = 5          # SO3: GPS update every 5 seconds
LOG_DIR        = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Default UUIDs matching seed.js — override with --truck-ids / --driver-ids
DEFAULT_TRUCKS  = [
    '11111111-0000-0000-0000-000000000001',
    '11111111-0000-0000-0000-000000000002',
    '11111111-0000-0000-0000-000000000004',
]
DEFAULT_DRIVERS = [
    '22222222-0000-0000-0000-000000000002',  # Juan
    '22222222-0000-0000-0000-000000000003',  # Maria
    '22222222-0000-0000-0000-000000000005',  # Ana
]

# ── Philippine Routes (Manila area) ───────────────────────────────────────────
ROUTES = {
    'north': [
        (14.5995, 120.9842),
        (14.6500, 120.9700),
        (14.7200, 120.9500),
        (14.7900, 120.9300),
        (14.8500, 120.9000),
    ],
    'south': [
        (14.5995, 120.9842),
        (14.5000, 121.0200),
        (14.3500, 121.0800),
        (14.2000, 121.1400),
        (14.0800, 121.1800),
    ],
    'east': [
        (14.5995, 120.9842),
        (14.5800, 121.0500),
        (14.5600, 121.1200),
        (14.5300, 121.2000),
        (14.5000, 121.2800),
    ],
}


# ══════════════════════════════════════════════════════════════════════════════
class TruckSimulator:
    def __init__(self, truck_id: str, driver_id: str,
                 route_name: str = 'north', scenario: str = 'normal',
                 tank_pct: float = None):
        self.truck_id    = truck_id
        self.driver_id   = driver_id
        self.trip_id     = None          # set after /trip/start
        self.route       = ROUTES[route_name]
        self.scenario    = scenario
        self.fuel        = tank_pct if tank_pct is not None else random.uniform(70, 95)
        self.odometer    = random.uniform(5000, 80000)
        self.waypoint_idx = 0
        self.direction   = 1
        self.speed       = 0.0
        self.lat, self.lon = self.route[0]
        self.reading_count = 0
        self._theft_done   = False
        self._leak_active  = False
        self._inject_at    = random.randint(20, 40)

    @property
    def current_waypoint(self):
        return self.route[self.waypoint_idx]

    def _move(self):
        target_lat, target_lon = self.current_waypoint
        dlat = target_lat - self.lat
        dlon = target_lon - self.lon
        dist = math.sqrt(dlat**2 + dlon**2)

        if dist < 0.001:
            self.waypoint_idx += self.direction
            if self.waypoint_idx >= len(self.route):
                self.waypoint_idx = len(self.route) - 2
                self.direction = -1
            elif self.waypoint_idx < 0:
                self.waypoint_idx = 1
                self.direction = 1
            return

        self.speed  = random.uniform(55, 90)
        step_km     = self.speed * GPS_INTERVAL_S / 3600
        step_deg    = step_km / 111.0
        ratio       = min(1.0, step_deg / (dist + 1e-9))
        self.lat   += dlat * ratio + random.gauss(0, 0.00005)
        self.lon   += dlon * ratio + random.gauss(0, 0.00005)

    def _consume_fuel(self):
        step_km       = self.speed * GPS_INTERVAL_S / 3600
        base_rate     = 0.18
        consumption   = base_rate * step_km + random.gauss(0, 0.01)
        self.fuel    -= max(0, consumption)
        self.odometer += step_km
        if self._leak_active:
            self.fuel -= base_rate * 4 * step_km

    def tick(self) -> dict:
        self.reading_count += 1
        self._move()
        self._consume_fuel()

        is_anomaly   = False
        anomaly_type = None

        if self.scenario == 'theft' and not self._theft_done:
            if self.reading_count == self._inject_at:
                self.fuel       -= random.uniform(22, 38)
                self.speed       = 0.0
                self._theft_done = True
                is_anomaly       = True
                anomaly_type     = 'theft'

        elif self.scenario == 'leak':
            if self.reading_count == self._inject_at:
                self._leak_active = True
            if self._leak_active:
                is_anomaly   = True
                anomaly_type = 'leak'

        elif self.scenario == 'overspeed':
            if self.reading_count == self._inject_at:
                self.speed   = random.uniform(130, 160)
                is_anomaly   = True
                anomaly_type = 'overspeed'

        self.fuel = max(0.5, min(100.0, self.fuel))
        if self.fuel < 10:
            self.fuel = random.uniform(88, 98)

        return {
            'truck_id':    self.truck_id,
            'driver_id':   self.driver_id,
            'trip_id':     self.trip_id,
            'fuel_level':  round(self.fuel, 2),
            'speed':       round(self.speed, 1),
            'odometer_km': round(self.odometer, 1),
            'lat':         round(self.lat, 6),
            'lon':         round(self.lon, 6),
            'engine_status': 'on',
            'sent_at':     datetime.now(timezone.utc).isoformat(),
            '_is_anomaly':   is_anomaly,
            '_anomaly_type': anomaly_type,
        }


# ══════════════════════════════════════════════════════════════════════════════
def start_trip(truck_id: str, driver_id: str, lat: float, lon: float,
               dry_run: bool = False) -> str | None:
    """Call POST /trip/start and return the trip_id."""
    if dry_run or not REQUESTS_OK:
        fake_id = f'dry-run-trip-{truck_id[:8]}'
        print(f"  [dry-run] trip started: {fake_id}")
        return fake_id
    try:
        res = requests.post(
            f'{BACKEND_URL}/trip/start',
            json={'truck_id': truck_id, 'driver_id': driver_id,
                  'start_lat': lat, 'start_lon': lon},
            timeout=5,
        )
        if res.status_code in (200, 201, 409):
            body = res.json()
            trip_id = body.get('id') or body.get('trip_id')
            print(f"  Trip started: {trip_id} (truck={truck_id[:8]}...)")
            return trip_id
        print(f"  WARNING: /trip/start returned HTTP {res.status_code}: {res.text[:80]}")
    except Exception as e:
        print(f"  ERROR starting trip: {e}")
    return None


def end_trip(trip_id: str, lat: float, lon: float, dry_run: bool = False):
    if dry_run or not REQUESTS_OK or not trip_id or trip_id.startswith('dry-run'):
        print(f"  [dry-run] trip ended: {trip_id}")
        return
    try:
        res = requests.post(
            f'{BACKEND_URL}/trip/end',
            json={'trip_id': trip_id, 'end_lat': lat, 'end_lon': lon},
            timeout=5,
        )
        print(f"  Trip ended: {trip_id} (HTTP {res.status_code})")
    except Exception as e:
        print(f"  ERROR ending trip: {e}")


def post_telemetry(payload: dict, dry_run: bool = False) -> dict:
    clean = {k: v for k, v in payload.items() if not k.startswith('_')}

    if dry_run or not REQUESTS_OK:
        flag = ' *** ANOMALY ***' if payload.get('_is_anomaly') else ''
        print(f"  [dry-run] {clean['truck_id'][:8]}... | "
              f"fuel={clean['fuel_level']}% | speed={clean['speed']}km/h | "
              f"({clean['lat']}, {clean['lon']}){flag}")
        return {'latency_ms': 0}

    try:
        t0  = time.time()
        res = requests.post(f'{BACKEND_URL}/telemetry', json=clean, timeout=5)
        lat_ms = round((time.time() - t0) * 1000)
        flag = ' *** ANOMALY ***' if payload.get('_is_anomaly') else ''
        print(f"  {clean['truck_id'][:8]}... | fuel={clean['fuel_level']}% | "
              f"speed={clean['speed']}km/h | HTTP {res.status_code} | {lat_ms}ms{flag}")
        return {'latency_ms': lat_ms}
    except Exception as e:
        print(f"  ERROR: {e}")
        return {'latency_ms': -1}


# ══════════════════════════════════════════════════════════════════════════════
class SimLogger:
    def __init__(self, filename: str):
        self.path   = os.path.join(LOG_DIR, filename)
        self.file   = open(self.path, 'w', newline='', encoding='utf-8')
        self.writer = csv.DictWriter(self.file, fieldnames=[
            'timestamp', 'truck_id', 'trip_id', 'fuel_level', 'speed',
            'odometer_km', 'lat', 'lon', 'latency_ms', 'is_anomaly', 'anomaly_type',
        ])
        self.writer.writeheader()

    def log(self, payload: dict, latency_ms: int):
        self.writer.writerow({
            'timestamp':   payload.get('sent_at', ''),
            'truck_id':    payload['truck_id'],
            'trip_id':     payload.get('trip_id', ''),
            'fuel_level':  payload['fuel_level'],
            'speed':       payload['speed'],
            'odometer_km': payload['odometer_km'],
            'lat':         payload['lat'],
            'lon':         payload['lon'],
            'latency_ms':  latency_ms,
            'is_anomaly':  payload.get('_is_anomaly', False),
            'anomaly_type': payload.get('_anomaly_type', ''),
        })
        self.file.flush()

    def close(self):
        self.file.close()
        print(f"\n  Simulation log saved: {self.path}")


# ══════════════════════════════════════════════════════════════════════════════
def run_simulation(truck_ids: list, driver_ids: list, scenario: str,
                   duration_s: int, dry_run: bool):
    routes     = list(ROUTES.keys())
    scenarios  = [scenario] + ['normal'] * (len(truck_ids) - 1)
    n          = len(truck_ids)

    trucks = []
    for i in range(n):
        trucks.append(TruckSimulator(
            truck_id  = truck_ids[i],
            driver_id = driver_ids[i] if i < len(driver_ids) else driver_ids[-1],
            route_name= routes[i % len(routes)],
            scenario  = scenarios[i],
        ))

    print(f"\n[simulate] {n} truck(s) | scenario={scenario} | "
          f"interval={GPS_INTERVAL_S}s | "
          f"duration={'∞' if duration_s == 0 else f'{duration_s}s'}")
    print(f"[simulate] Backend: {BACKEND_URL}\n")

    # Start trips
    for truck in trucks:
        trip_id = start_trip(truck.truck_id, truck.driver_id,
                             truck.lat, truck.lon, dry_run)
        truck.trip_id = trip_id

    ts      = datetime.now().strftime('%Y%m%d_%H%M%S')
    logger  = SimLogger(f'simulation_{ts}_{scenario}.csv')
    stop_at = time.time() + duration_s if duration_s > 0 else float('inf')
    step    = 0

    try:
        while time.time() < stop_at:
            step += 1
            print(f"-- Step {step} ----------------------------------")
            for truck in trucks:
                payload  = truck.tick()
                result   = post_telemetry(payload, dry_run)
                logger.log(payload, result.get('latency_ms', -1))
            time.sleep(GPS_INTERVAL_S)

    except KeyboardInterrupt:
        print("\n[simulate] Stopped by user.")
    finally:
        for truck in trucks:
            end_trip(truck.trip_id, truck.lat, truck.lon, dry_run)
        logger.close()


def main():
    parser = argparse.ArgumentParser(description='Fleet Simulation Pipeline v2')
    parser.add_argument('--scenario',   default='normal',
                        choices=['normal', 'theft', 'leak', 'overspeed'])
    parser.add_argument('--duration',   type=int, default=0,
                        help='Seconds to run (0 = forever)')
    parser.add_argument('--backend',    default=None)
    parser.add_argument('--dry-run',    action='store_true')
    parser.add_argument('--truck-ids',  default=','.join(DEFAULT_TRUCKS),
                        help='Comma-separated truck UUIDs from Supabase')
    parser.add_argument('--driver-ids', default=','.join(DEFAULT_DRIVERS),
                        help='Comma-separated driver UUIDs (same order as trucks)')
    args = parser.parse_args()

    global BACKEND_URL
    if args.backend:
        BACKEND_URL = args.backend

    run_simulation(
        truck_ids  = [t.strip() for t in args.truck_ids.split(',') if t.strip()],
        driver_ids = [d.strip() for d in args.driver_ids.split(',') if d.strip()],
        scenario   = args.scenario,
        duration_s = args.duration,
        dry_run    = args.dry_run,
    )


if __name__ == '__main__':
    main()
