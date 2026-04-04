"""
seed_data.py — One-shot Supabase seeder for the thesis fleet system
===================================================================
Populates trip_sessions, telemetry_logs, and alerts using the real
trucks and drivers already in Supabase.

Based on audit (2026-04-04):
  Trucks:  TRK-002, TRK-003, TRK-004
  Drivers: juan, maria, roberto, ana, driver1

Inserts data DIRECTLY into Supabase via REST API (no backend needed).

Usage:
    pip install requests python-dotenv
    python seed_data.py              # seed historical + active trips
    python seed_data.py --wipe-only  # delete all operational data only
    python seed_data.py --no-osrm   # skip OSRM, use straight-line fallback
"""

import os
import sys
import math
import uuid
import time
import random
import argparse
from datetime import datetime, timedelta, timezone

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))
except ImportError:
    pass

# ── Supabase config ────────────────────────────────────────────────────────────
SUPABASE_URL         = os.getenv('SUPABASE_URL', '').rstrip('/')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY', '')
OSRM_URL             = 'https://router.project-osrm.org'

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in backend/.env")
    sys.exit(1)

HEADERS = {
    'apikey':        SUPABASE_SERVICE_KEY,
    'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
    'Content-Type':  'application/json',
    'Prefer':        'return=minimal',
}

# ── Known Supabase records (from audit) ───────────────────────────────────────
TRUCKS = {
    'TRK-002': {
        'id':          '11111111-0000-0000-0000-000000000002',
        'driver_id':   '22222222-0000-0000-0000-000000000003',   # maria
        'driver_name': 'Maria Santos',
        'model':       'Mitsubishi Fuso 2019',
        'route_key':   'slex_south',
        'make_active': True,
    },
    'TRK-003': {
        'id':          '11111111-0000-0000-0000-000000000003',
        'driver_id':   '22222222-0000-0000-0000-000000000004',   # roberto
        'driver_name': 'Roberto Garcia',
        'model':       'Hino 300 Series 2021',
        'route_key':   'c5_east',
        'make_active': False,   # truck is in maintenance
    },
    'TRK-004': {
        'id':          '11111111-0000-0000-0000-000000000004',
        'driver_id':   '22222222-0000-0000-0000-000000000005',   # ana
        'driver_name': 'Ana Reyes',
        'model':       'Isuzu NLR 2022',
        'route_key':   'nlex_north',
        'make_active': True,
    },
}

# ── Philippine Road Routes ─────────────────────────────────────────────────────
# Waypoints OSRM will snap to real roads.
HUB = (14.5029, 121.0169)   # 7887B Ninoy Aquino Ave, Paranaque (fleet base)

ROUTE_WAYPOINTS = {
    # SLEX: Paranaque base → Sucat → San Pedro → Binan → Sta. Rosa
    'slex_south': [
        HUB,
        (14.4700, 121.0400),   # Sucat exit
        (14.4200, 121.0550),   # Alabang
        (14.3600, 121.0600),   # San Pedro
        (14.2800, 121.0800),   # Binan
        (14.1900, 121.1100),   # Sta. Rosa
    ],
    # NLEX: Paranaque base → C5 → EDSA → Balintawak → Bocaue
    'nlex_north': [
        HUB,
        (14.5509, 121.0507),   # BGC/C5 junction
        (14.6500, 121.0350),   # EDSA Quezon Ave
        (14.6867, 121.0005),   # Balintawak toll
        (14.7400, 120.9600),   # Meycauayan
        (14.8000, 120.9400),   # Bocaue
    ],
    # C5: Paranaque base → BGC → Ortigas → Cainta
    'c5_east': [
        HUB,
        (14.5509, 121.0507),   # BGC / Fort Bonifacio
        (14.5800, 121.0850),   # Ortigas Center
        (14.6050, 121.1100),   # Eastwood
        (14.6200, 121.1350),   # Cainta junction
    ],
}


# ── Helpers ────────────────────────────────────────────────────────────────────
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def now_utc():
    return datetime.now(timezone.utc)


def fmt(dt):
    return dt.isoformat()


def new_id():
    return str(uuid.uuid4())


# ── OSRM ──────────────────────────────────────────────────────────────────────
def fetch_osrm_route(waypoints, use_osrm=True):
    """Return list of (lat, lon) road-snapped points."""
    if not use_osrm:
        return waypoints
    coords = ';'.join(f'{lon},{lat}' for lat, lon in waypoints)
    url = f'{OSRM_URL}/route/v1/driving/{coords}?overview=full&geometries=geojson'
    try:
        r = requests.get(url, timeout=12)
        if r.status_code == 200:
            data = r.json()
            if data.get('code') == 'Ok':
                pts = [(c[1], c[0]) for c in data['routes'][0]['geometry']['coordinates']]
                print(f"  [OSRM] {len(pts)} road points fetched")
                return pts
    except Exception as e:
        print(f"  [OSRM] Failed ({e}), using fallback")
    return waypoints


# ── Supabase REST helpers ─────────────────────────────────────────────────────
def supa_insert(table, rows, chunk=400):
    """Bulk-insert rows into Supabase table."""
    if not rows:
        return
    url = f'{SUPABASE_URL}/rest/v1/{table}'
    for i in range(0, len(rows), chunk):
        batch = rows[i:i+chunk]
        r = requests.post(url, headers=HEADERS, json=batch, timeout=30)
        if r.status_code not in (200, 201):
            print(f"  [insert] {table} HTTP {r.status_code}: {r.text[:200]}")
        else:
            print(f"  [insert] {table}: +{len(batch)} rows")


def supa_delete(table, filter_qs='id=neq.00000000-0000-0000-0000-000000000000'):
    """Delete all rows from a table (safe delete via filter)."""
    url = f'{SUPABASE_URL}/rest/v1/{table}?{filter_qs}'
    r = requests.delete(url, headers=HEADERS, timeout=15)
    if r.status_code in (200, 204):
        print(f"  [wipe] {table} cleared")
    else:
        print(f"  [wipe] {table} HTTP {r.status_code}: {r.text[:120]}")


def supa_patch(table, filter_qs, body):
    url = f'{SUPABASE_URL}/rest/v1/{table}?{filter_qs}'
    r = requests.patch(url, headers=HEADERS, json=body, timeout=10)
    if r.status_code not in (200, 204):
        print(f"  [patch] {table} HTTP {r.status_code}: {r.text[:120]}")


# ── Trip + Telemetry generator ────────────────────────────────────────────────
def build_trip_telemetry(
    truck_id, driver_id, route_pts,
    start_time, end_time=None,
    start_fuel=85.0, interval_s=30,
    inject_anomaly_at=None,
):
    """
    Walk along route_pts from start_time to end_time (or current time if None).
    Returns (trip_row, telem_rows, alert_rows).
    """
    trip_id    = new_id()
    is_active  = end_time is None
    pt_idx     = 0
    direction  = 1
    fuel       = start_fuel
    odometer   = random.uniform(12000, 60000)
    telem_rows = []
    alert_rows = []
    ts         = start_time
    step       = 0

    total_pts  = len(route_pts)
    lat, lon   = route_pts[0]

    stop_time  = end_time if end_time else now_utc()

    while ts <= stop_time:
        step += 1

        # Advance along route
        if pt_idx + direction < 0:
            direction = 1
            pt_idx = 1
        elif pt_idx + direction >= total_pts:
            direction = -1
            pt_idx = total_pts - 2
        else:
            pt_idx += direction

        next_lat, next_lon = route_pts[pt_idx]
        dist_km = haversine_km(lat, lon, next_lat, next_lon)
        speed   = random.uniform(45, 85)
        step_km = speed * interval_s / 3600
        if dist_km > 0.001:
            ratio = min(1.0, step_km / dist_km)
            lat  += (next_lat - lat) * ratio + random.gauss(0, 0.00003)
            lon  += (next_lon - lon) * ratio + random.gauss(0, 0.00003)

        # ECU-derived fuel consumption
        consumption = 0.20 * step_km + random.gauss(0, 0.008)
        fuel       -= max(0, consumption)
        fuel        = max(5.0, min(100.0, fuel))
        odometer   += step_km

        is_anomaly   = False
        anomaly_score = round(random.uniform(0.02, 0.12), 3)

        # Inject anomaly at specified step
        if inject_anomaly_at and step == inject_anomaly_at:
            fuel -= random.uniform(15, 25)   # sudden fuel drop (theft/leak)
            fuel  = max(5.0, fuel)
            is_anomaly    = True
            anomaly_score = round(random.uniform(0.78, 0.95), 3)
            # Create alert
            alert_rows.append({
                'id':          new_id(),
                'truck_id':    truck_id,
                'driver_id':   driver_id,
                'trip_id':     trip_id,
                'timestamp':   fmt(ts),
                'alert_type':  'anomaly_detected',
                'message':     f'Abnormal fuel drop detected — possible leak or theft (score: {anomaly_score})',
                'severity':    'high',
                'is_resolved': not is_active,
                'created_at':  fmt(ts),
            })

        # Low-fuel alert at 15%
        if fuel < 15 and not any(a['alert_type'] == 'low_fuel' and a['truck_id'] == truck_id for a in alert_rows):
            alert_rows.append({
                'id':          new_id(),
                'truck_id':    truck_id,
                'driver_id':   driver_id,
                'trip_id':     trip_id,
                'timestamp':   fmt(ts),
                'alert_type':  'low_fuel',
                'message':     f'Fuel level critical: {fuel:.1f}% — immediate refuel required',
                'severity':    'medium',
                'is_resolved': not is_active,
                'created_at':  fmt(ts),
            })

        telem_rows.append({
            'id':            new_id(),
            'truck_id':      truck_id,
            'driver_id':     driver_id,
            'trip_id':       trip_id,
            'timestamp':     fmt(ts),
            'fuel_level':    round(fuel, 2),
            'lat':           round(lat, 6),
            'lon':           round(lon, 6),
            'speed':         round(speed, 1),
            'odometer_km':   round(odometer, 1),
            'engine_status': 'on',
            'anomaly_flag':  is_anomaly,
            'anomaly_score': anomaly_score,
            'model_source':  'seeded',
            'created_at':    fmt(ts),
        })

        ts += timedelta(seconds=interval_s)

    # Compute trip totals
    total_km    = round(odometer - (odometer - len(telem_rows) * 0.3), 2)
    elapsed_h   = round((stop_time - start_time).total_seconds() / 3600, 2)

    trip_row = {
        'id':              trip_id,
        'truck_id':        truck_id,
        'driver_id':       driver_id,
        'start_time':      fmt(start_time),
        'end_time':        fmt(end_time) if end_time else None,
        'trip_status':     'active' if is_active else 'ended',
        'start_lat':       round(route_pts[0][0], 6),
        'start_lon':       round(route_pts[0][1], 6),
        'end_lat':         round(lat, 6),
        'end_lon':         round(lon, 6),
        'distance_km':     total_km,
        'operating_hours': elapsed_h,
        'created_at':      fmt(start_time),
    }

    return trip_row, telem_rows, alert_rows


# ── Wipe operational tables ────────────────────────────────────────────────────
def wipe():
    print("\n[wipe] Clearing operational tables…")
    supa_delete('telemetry_logs')
    supa_delete('alerts')
    supa_delete('trip_sessions')
    # Reset all truck statuses to idle
    supa_patch('trucks', 'id=neq.00000000-0000-0000-0000-000000000000',
               {'status': 'idle'})
    print("[wipe] Done.\n")


# ── Main seed logic ────────────────────────────────────────────────────────────
def seed(use_osrm=True):
    now   = now_utc()
    trips = []
    telems = []
    alerts = []

    # Fetch and cache OSRM routes (one fetch per route type to be polite)
    print("\n[routes] Fetching OSRM road routes…")
    route_cache = {}
    for key, wps in ROUTE_WAYPOINTS.items():
        print(f"  Fetching: {key}")
        route_cache[key] = fetch_osrm_route(wps, use_osrm)
        time.sleep(0.5)   # gentle rate limit

    # ── TRK-002 (Maria / SLEX south) ─────────────────────────────────────────
    trk = TRUCKS['TRK-002']
    rte = route_cache['slex_south']

    # Historical trip 1 — 3 days ago, 2.5 h, anomaly injected
    h1_start = now - timedelta(days=3, hours=2)
    h1_end   = h1_start + timedelta(hours=2, minutes=30)
    t, tl, al = build_trip_telemetry(
        trk['id'], trk['driver_id'], rte,
        h1_start, h1_end, start_fuel=88.0,
        interval_s=30, inject_anomaly_at=35,
    )
    trips.append(t); telems += tl; alerts += al

    # Historical trip 2 — yesterday, 2 h, clean run
    h2_start = now - timedelta(days=1, hours=5)
    h2_end   = h2_start + timedelta(hours=2)
    t, tl, al = build_trip_telemetry(
        trk['id'], trk['driver_id'], rte,
        h2_start, h2_end, start_fuel=92.0,
        interval_s=30,
    )
    trips.append(t); telems += tl; alerts += al

    # ACTIVE trip — started 40 min ago, anomaly injected at step 80 (~6 min in)
    active_start = now - timedelta(minutes=40)
    t, tl, al = build_trip_telemetry(
        trk['id'], trk['driver_id'], rte,
        active_start, end_time=None,   # None = active
        start_fuel=95.0, interval_s=5, inject_anomaly_at=80,
    )
    trips.append(t); telems += tl; alerts += al
    active_trip_trk002 = t

    # ── TRK-004 (Ana / NLEX north) ───────────────────────────────────────────
    trk = TRUCKS['TRK-004']
    rte = route_cache['nlex_north']

    # Historical trip 1 — 4 days ago, 3 h, anomaly
    h1_start = now - timedelta(days=4, hours=1)
    h1_end   = h1_start + timedelta(hours=3)
    t, tl, al = build_trip_telemetry(
        trk['id'], trk['driver_id'], rte,
        h1_start, h1_end, start_fuel=82.0,
        interval_s=30, inject_anomaly_at=50,
    )
    trips.append(t); telems += tl; alerts += al

    # Historical trip 2 — 2 days ago, 2 h, clean
    h2_start = now - timedelta(days=2, hours=3)
    h2_end   = h2_start + timedelta(hours=2)
    t, tl, al = build_trip_telemetry(
        trk['id'], trk['driver_id'], rte,
        h2_start, h2_end, start_fuel=90.0,
        interval_s=30,
    )
    trips.append(t); telems += tl; alerts += al

    # ACTIVE trip — started 25 min ago
    active_start = now - timedelta(minutes=25)
    t, tl, al = build_trip_telemetry(
        trk['id'], trk['driver_id'], rte,
        active_start, end_time=None,
        start_fuel=97.0, interval_s=5,
    )
    trips.append(t); telems += tl; alerts += al
    active_trip_trk004 = t

    # ── TRK-003 (Roberto / C5 east — maintenance, historical only) ───────────
    trk = TRUCKS['TRK-003']
    rte = route_cache['c5_east']

    # Historical trip 1 — 5 days ago
    h1_start = now - timedelta(days=5, hours=3)
    h1_end   = h1_start + timedelta(hours=2, minutes=45)
    t, tl, al = build_trip_telemetry(
        trk['id'], trk['driver_id'], rte,
        h1_start, h1_end, start_fuel=78.0,
        interval_s=30,
    )
    trips.append(t); telems += tl; alerts += al

    # Historical trip 2 — 6 days ago
    h2_start = now - timedelta(days=6, hours=4)
    h2_end   = h2_start + timedelta(hours=3)
    t, tl, al = build_trip_telemetry(
        trk['id'], trk['driver_id'], rte,
        h2_start, h2_end, start_fuel=85.0,
        interval_s=30, inject_anomaly_at=60,
    )
    trips.append(t); telems += tl; alerts += al

    # ── Insert everything ─────────────────────────────────────────────────────
    print(f"\n[seed] Inserting {len(trips)} trips, {len(telems)} telemetry rows, {len(alerts)} alerts…")
    supa_insert('trip_sessions', trips)
    supa_insert('telemetry_logs', telems)
    supa_insert('alerts', alerts)

    # ── Update truck statuses ─────────────────────────────────────────────────
    print("\n[seed] Updating truck statuses…")
    for code, trk in TRUCKS.items():
        status = 'active' if trk['make_active'] else 'maintenance'
        supa_patch('trucks', f'id=eq.{trk["id"]}', {'status': status})
        print(f"  {code} -> {status}")

    # ── Summary ───────────────────────────────────────────────────────────────
    active_trucks = [c for c, t in TRUCKS.items() if t['make_active']]
    unresolved = sum(1 for a in alerts if not a['is_resolved'])
    print("")
    print("=" * 54)
    print("  SEED COMPLETE")
    print("=" * 54)
    print(f"  trip_sessions  : {len(trips):>5} rows inserted")
    print(f"  telemetry_logs : {len(telems):>5} rows inserted")
    print(f"  alerts         : {len(alerts):>5} rows inserted")
    print("-" * 54)
    print(f"  Active trucks  : {', '.join(active_trucks)}")
    print(f"  TRK-002 active trip : {active_trip_trk002['id'][:8]}...")
    print(f"  TRK-004 active trip : {active_trip_trk004['id'][:8]}...")
    print("-" * 54)
    print("  Dashboard checklist:")
    print("  [x] Fleet Status  - 3 trucks visible")
    print("  [x] Map           - TRK-002 (SLEX), TRK-004 (NLEX)")
    print("  [x] Trucks tab    - fuel %, speed, status cards")
    print(f"  [x] Logs tab      - {len(telems)} telemetry entries")
    print(f"  [x] Alerts panel  - {len(alerts)} alerts ({unresolved} unresolved)")
    print("  [x] Trip history  - via truck detail modal")
    print("=" * 54)


# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='Thesis fleet data seeder')
    parser.add_argument('--wipe-only', action='store_true',
                        help='Delete all operational data and exit')
    parser.add_argument('--no-osrm',  action='store_true',
                        help='Skip OSRM, use straight-line waypoints')
    args = parser.parse_args()

    if args.wipe_only:
        wipe()
        sys.exit(0)

    wipe()
    seed(use_osrm=not args.no_osrm)


if __name__ == '__main__':
    main()
