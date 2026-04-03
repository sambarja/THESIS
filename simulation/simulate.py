"""
SO2 / SO3 / SO4 / SO5 — Fleet Simulation Pipeline
====================================================
Generates realistic truck telemetry and POSTs it to the backend
at configurable intervals. Used for thesis demo, testing, and
validation when real hardware is unavailable.

Features:
  - Multiple trucks with unique IDs
  - Realistic Philippine GPS routes (Manila-area base)
  - 5-second GPS update intervals (SO3 requirement)
  - Normal + anomaly scenarios (theft, leak, overspeed)
  - SO2-c: records sent_at for latency benchmarking
  - Outputs simulation log CSV for thesis documentation

Usage:
    pip install -r requirements.txt
    python simulate.py                         # normal fleet, 5 trucks
    python simulate.py --trucks 3 --scenario theft
    python simulate.py --trucks 2 --scenario leak --duration 120
    python simulate.py --dry-run               # print data without POSTing
"""

import time
import math
import random
import argparse
import csv
import os
import json
import threading
from datetime import datetime, timezone

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False
    print("[simulate] WARNING: requests not installed — dry-run only.")

# ── Configuration ──────────────────────────────────────────────────────────────
BACKEND_URL    = 'http://localhost:5000'
GPS_INTERVAL_S = 5          # SO3: GPS update every 5 seconds
LOG_DIR        = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# ── Philippine base coordinates (Manila area) ──────────────────────────────────
# Routes simulate trucks moving between these waypoints
ROUTES = {
    'north': [
        (14.5995, 120.9842),   # Manila (base)
        (14.6500, 120.9700),
        (14.7200, 120.9500),
        (14.7900, 120.9300),
        (14.8500, 120.9000),   # Bulacan area
    ],
    'south': [
        (14.5995, 120.9842),
        (14.5000, 121.0200),
        (14.3500, 121.0800),
        (14.2000, 121.1400),
        (14.0800, 121.1800),   # Laguna area
    ],
    'east': [
        (14.5995, 120.9842),
        (14.5800, 121.0500),
        (14.5600, 121.1200),
        (14.5300, 121.2000),
        (14.5000, 121.2800),   # Rizal area
    ],
}


# ══════════════════════════════════════════════════════════════════════════════
#  Truck simulator state
# ══════════════════════════════════════════════════════════════════════════════
class TruckSimulator:
    def __init__(self, vehicle_id: str, route_name: str = 'north',
                 scenario: str = 'normal', tank_pct: float = None):
        self.vehicle_id  = vehicle_id
        self.route       = ROUTES[route_name]
        self.scenario    = scenario
        self.fuel        = tank_pct if tank_pct is not None else random.uniform(70, 95)
        self.odometer    = random.uniform(5000, 80000)
        self.waypoint_idx = 0
        self.direction   = 1   # 1=forward, -1=backward
        self.speed       = 0.0
        self.lat, self.lon = self.route[0]
        self.reading_count = 0

        # Anomaly injection state
        self._theft_done   = False
        self._leak_active  = False
        self._inject_at    = random.randint(20, 40)  # reading number to inject

    @property
    def current_waypoint(self):
        return self.route[self.waypoint_idx]

    def _move_towards_waypoint(self):
        """Move truck incrementally towards current waypoint."""
        target_lat, target_lon = self.current_waypoint
        dlat = target_lat - self.lat
        dlon = target_lon - self.lon
        dist = math.sqrt(dlat**2 + dlon**2)

        if dist < 0.001:   # close enough — advance waypoint
            self.waypoint_idx += self.direction
            if self.waypoint_idx >= len(self.route):
                self.waypoint_idx = len(self.route) - 2
                self.direction = -1
            elif self.waypoint_idx < 0:
                self.waypoint_idx = 1
                self.direction = 1
            return

        # Simulate speed (km/h): highway 70-90, city 20-40
        self.speed  = random.uniform(55, 90)
        # Convert speed to lat/lon delta per 5-second step
        step_km     = self.speed * GPS_INTERVAL_S / 3600
        step_deg    = step_km / 111.0   # rough: 1 deg ≈ 111 km

        ratio = min(1.0, step_deg / (dist + 1e-9))
        self.lat += dlat * ratio + random.gauss(0, 0.00005)
        self.lon += dlon * ratio + random.gauss(0, 0.00005)

    def _consume_fuel(self):
        """Normal fuel consumption based on speed and distance."""
        step_km      = self.speed * GPS_INTERVAL_S / 3600
        base_rate    = 0.18    # %/km normal consumption
        consumption  = base_rate * step_km + random.gauss(0, 0.01)
        self.fuel   -= max(0, consumption)
        self.odometer += step_km

        if self._leak_active:
            # Leak: 5× normal consumption
            extra = base_rate * 4 * step_km
            self.fuel -= extra

    def tick(self) -> dict:
        """Advance simulation by one GPS_INTERVAL_S step."""
        self.reading_count += 1

        self._move_towards_waypoint()
        self._consume_fuel()

        # ── Inject anomaly based on scenario ──────────────────────────────────
        is_anomaly = False
        anomaly_type = None

        if self.scenario == 'theft' and not self._theft_done:
            if self.reading_count == self._inject_at:
                self.fuel        -= random.uniform(22, 38)   # sudden drop
                self.speed        = 0.0                       # vehicle parked
                self._theft_done  = True
                is_anomaly        = True
                anomaly_type      = 'theft'

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

        # Clamp fuel
        self.fuel = max(0.5, min(100.0, self.fuel))

        # Refuel when critically low
        if self.fuel < 10:
            self.fuel = random.uniform(88, 98)

        return {
            'vehicle_id':  self.vehicle_id,
            'fuel_level':  round(self.fuel, 2),
            'speed_kmph':  round(self.speed, 1),
            'odometer_km': round(self.odometer, 1),
            'latitude':    round(self.lat, 6),
            'longitude':   round(self.lon, 6),
            'sent_at':     datetime.now(timezone.utc).isoformat(),
            '_is_anomaly': is_anomaly,
            '_anomaly_type': anomaly_type,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  POST to backend
# ══════════════════════════════════════════════════════════════════════════════
def post_reading(payload: dict, dry_run: bool = False) -> dict:
    """POST one telemetry reading. Returns response summary."""
    clean = {k: v for k, v in payload.items() if not k.startswith('_')}

    if dry_run or not REQUESTS_OK:
        print(f"  [dry-run] {clean['vehicle_id']} | "
              f"fuel={clean['fuel_level']}% | "
              f"speed={clean['speed_kmph']}km/h | "
              f"({clean['latitude']}, {clean['longitude']})"
              + (' *** ANOMALY ***' if payload.get('_is_anomaly') else ''))
        return {'latency_ms': 0, 'status': 'dry-run'}

    try:
        t0  = time.time()
        res = requests.post(
            f"{BACKEND_URL}/telemetry",
            json=clean,
            timeout=5,
        )
        latency = round((time.time() - t0) * 1000)
        status  = res.status_code

        flag = ' *** ANOMALY ***' if payload.get('_is_anomaly') else ''
        print(f"  {clean['vehicle_id']} | fuel={clean['fuel_level']}% | "
              f"speed={clean['speed_kmph']}km/h | "
              f"lat={clean['latitude']} | HTTP {status} | {latency}ms{flag}")

        return {'latency_ms': latency, 'status': status}

    except Exception as e:
        print(f"  ERROR posting {clean['vehicle_id']}: {e}")
        return {'latency_ms': -1, 'status': 'error'}


# ══════════════════════════════════════════════════════════════════════════════
#  CSV logger
# ══════════════════════════════════════════════════════════════════════════════
class SimLogger:
    def __init__(self, filename: str):
        self.path = os.path.join(LOG_DIR, filename)
        self.file = open(self.path, 'w', newline='', encoding='utf-8')
        self.writer = csv.DictWriter(self.file, fieldnames=[
            'timestamp', 'vehicle_id', 'fuel_level', 'speed_kmph',
            'odometer_km', 'latitude', 'longitude',
            'latency_ms', 'is_anomaly', 'anomaly_type',
        ])
        self.writer.writeheader()

    def log(self, payload: dict, latency_ms: int):
        self.writer.writerow({
            'timestamp':   payload.get('sent_at', ''),
            'vehicle_id':  payload['vehicle_id'],
            'fuel_level':  payload['fuel_level'],
            'speed_kmph':  payload['speed_kmph'],
            'odometer_km': payload['odometer_km'],
            'latitude':    payload['latitude'],
            'longitude':   payload['longitude'],
            'latency_ms':  latency_ms,
            'is_anomaly':  payload.get('_is_anomaly', False),
            'anomaly_type': payload.get('_anomaly_type', ''),
        })
        self.file.flush()

    def close(self):
        self.file.close()
        print(f"\n  Simulation log saved: {self.path}")


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════
def run_simulation(n_trucks: int, scenario: str, duration_s: int,
                   dry_run: bool, vehicle_ids: list = None):
    routes    = list(ROUTES.keys())
    scenarios = [scenario] + ['normal'] * (n_trucks - 1)

    trucks = []
    for i in range(n_trucks):
        vid   = vehicle_ids[i] if (vehicle_ids and i < len(vehicle_ids)) else f'SIM-TRUCK-{i+1:02d}'
        route = routes[i % len(routes)]
        sc    = scenarios[i]
        trucks.append(TruckSimulator(vid, route_name=route, scenario=sc))

    ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
    logger   = SimLogger(f'simulation_{ts}_{scenario}.csv')
    stop_at  = time.time() + duration_s if duration_s > 0 else float('inf')
    step     = 0

    print(f"\n[simulate] Starting {n_trucks} truck(s) | scenario={scenario} | "
          f"interval={GPS_INTERVAL_S}s | duration={'∞' if duration_s == 0 else f'{duration_s}s'}")
    print(f"[simulate] Backend: {BACKEND_URL}\n")

    try:
        while time.time() < stop_at:
            step += 1
            print(f"── Step {step} ──────────────────────────────")

            for truck in trucks:
                payload  = truck.tick()
                result   = post_reading(payload, dry_run=dry_run)
                logger.log(payload, result.get('latency_ms', -1))

            time.sleep(GPS_INTERVAL_S)

    except KeyboardInterrupt:
        print("\n[simulate] Stopped by user.")
    finally:
        logger.close()


def main():
    parser = argparse.ArgumentParser(description='Fleet Simulation Pipeline')
    parser.add_argument('--trucks',    type=int,   default=3,
                        help='Number of trucks to simulate (default: 3)')
    parser.add_argument('--scenario',  type=str,   default='normal',
                        choices=['normal', 'theft', 'leak', 'overspeed'],
                        help='Anomaly scenario for truck 1 (default: normal)')
    parser.add_argument('--duration',  type=int,   default=0,
                        help='Duration in seconds (0 = run forever, default: 0)')
    parser.add_argument('--backend',   type=str,   default=BACKEND_URL,
                        help=f'Backend URL (default: {BACKEND_URL})')
    parser.add_argument('--dry-run',   action='store_true',
                        help='Print data without POSTing to backend')
    parser.add_argument('--vehicle-ids', type=str, default=None,
                        help='Comma-separated vehicle IDs from your Supabase DB')
    args = parser.parse_args()

    global BACKEND_URL
    BACKEND_URL = args.backend

    vids = args.vehicle_ids.split(',') if args.vehicle_ids else None

    run_simulation(
        n_trucks   = args.trucks,
        scenario   = args.scenario,
        duration_s = args.duration,
        dry_run    = args.dry_run,
        vehicle_ids= vids,
    )


if __name__ == '__main__':
    main()
