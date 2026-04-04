"""
Fleet Simulation Pipeline v6
============================
Realistic multi-truck thesis demo with:
- Persistent truck state across scenario runs (truck_state.json)
- New dispatch hub: 1232 United Nations Ave, Paco, Manila
- 13+ route destinations across Metro Manila / nearby provinces
- All four fleet trucks: TRK-001 through TRK-004
- 13 named scenarios across Groups A–G plus quick-test variants
- ML anomaly detection via existing /detect endpoint
- REST / maintenance / overspeed alert integration
- Historical backfill via seed_data.py

Usage:
  pip install requests python-dotenv
  python simulate.py --scenario fleet
  python simulate.py --scenario group_a
  python simulate.py --scenario group_b
  python simulate.py --scenario group_f  --reset   # alert testing
  python simulate.py --scenario quick              # single fast run
  python simulate.py --scenario quick_anomaly
  python simulate.py --scenario quick_rest
  python simulate.py --list-scenarios
  python simulate.py --reset-only
  python simulate.py --reset-state                 # clear persistent positions
  python simulate.py --scenario fleet --no-osrm    # skip OSRM routing
  python simulate.py --scenario anomaly --print-rundown-only
"""

import argparse
import copy
import csv
import json
import math
import os
import random
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

HTTP = requests.Session() if REQUESTS_OK else None

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
except ImportError:
    pass

BACKEND       = os.getenv("BACKEND_URL", os.getenv("SIM_BACKEND_URL", "http://127.0.0.1:5000")).rstrip("/")
OSRM          = "https://router.project-osrm.org"
SUPABASE_URL  = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SVC_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
ADMIN_TOKEN   = os.getenv("SIM_ADMIN_TOKEN", "00000000-0000-0000-0000-000000000001")
GPS_INTERVAL_S = 5
LOG_DIR       = os.path.join(os.path.dirname(__file__), "logs")
STATE_FILE    = os.path.join(os.path.dirname(__file__), "truck_state.json")
os.makedirs(LOG_DIR, exist_ok=True)
MANILA_TZ = timezone(timedelta(hours=8))
HISTORICAL_SCENARIO = "historical_backfill"
HISTORICAL_TEMPLATE_SCENARIOS = ["fleet", "anomaly", "rest_alert", "handover", "full_demo"]
DEFAULT_BACKFILL_START = f"{datetime.now(MANILA_TZ).year}-02-01"
DEFAULT_BACKFILL_END = f"{datetime.now(MANILA_TZ).year}-03-31"

# ── Dispatch hub ────────────────────────────────────────────────────────────────
HUB       = (14.5878, 120.9830)
HUB_LABEL = "1232 United Nations Ave, Paco, Manila, 1000"

# ── Destinations reachable from the Manila hub ──────────────────────────────────
DESTINATIONS = {
    # ── Short urban (10–20 min) ────────────────────────────────────────────────
    "port_manila": {
        "coords": (14.5953, 120.9710),
        "label": "Port Area, Manila",
        "summary": "Short harbour delivery near Manila South Port.",
    },
    "divisoria": {
        "coords": (14.6113, 120.9717),
        "label": "Divisoria Market, Tondo",
        "summary": "Dense urban dispatch to Divisoria trading area.",
    },
    "moa_pasay": {
        "coords": (14.5354, 120.9815),
        "label": "Mall of Asia Complex, Pasay",
        "summary": "South Manila waterfront delivery run.",
    },
    "makati_cbd": {
        "coords": (14.5547, 121.0244),
        "label": "Makati Central Business District",
        "summary": "Business-district urban run with moderate traffic.",
    },
    "market_loop": {
        "coords": (14.5580, 121.0180),
        "label": "Pasay–Taguig market loop",
        "summary": "Short urban dispatch near Pasay and Taguig.",
    },
    # ── Medium routes (20–40 min) ──────────────────────────────────────────────
    "bgc_taguig": {
        "coords": (14.5344, 121.0494),
        "label": "Bonifacio Global City, Taguig",
        "summary": "Modern CBD run through Fort Bonifacio corridor.",
    },
    "navotas": {
        "coords": (14.6663, 120.9556),
        "label": "Navotas Fish Port",
        "summary": "North-west delivery run to Navotas cold-chain port.",
    },
    "caloocan": {
        "coords": (14.7056, 120.9696),
        "label": "Caloocan City",
        "summary": "North Metro Manila urban corridor run.",
    },
    "marikina": {
        "coords": (14.6509, 121.1027),
        "label": "Marikina City",
        "summary": "East corridor run through Marikina valley.",
    },
    "c5_east": {
        "coords": (14.6200, 121.1350),
        "label": "Cainta, Rizal via C5 corridor",
        "summary": "East-bound C5 corridor run with moderate city traffic.",
    },
    "quezon_ne": {
        "coords": (14.7258, 121.0400),
        "label": "Novaliches, Quezon City",
        "summary": "North-east dispatch through Metro Manila arterials.",
    },
    # ── Long routes (40+ min) ─────────────────────────────────────────────────
    "cavite_sw": {
        "coords": (14.4081, 120.8970),
        "label": "Bacoor, Cavite",
        "summary": "South-west delivery run toward Cavite province.",
    },
    "nlex_north": {
        "coords": (14.8000, 120.9400),
        "label": "Bocaue, Bulacan via NLEX",
        "summary": "Longer north-bound expressway delivery run.",
    },
    "slex_south": {
        "coords": (14.1900, 121.1100),
        "label": "Sta. Rosa, Laguna via SLEX",
        "summary": "Long south-bound expressway run via SLEX.",
    },
}

# ── All fleet trucks (UUIDs match Supabase seed) ────────────────────────────────
TRUCKS = {
    "TRK-001": "11111111-0000-0000-0000-000000000001",
    "TRK-002": "11111111-0000-0000-0000-000000000002",
    "TRK-003": "11111111-0000-0000-0000-000000000003",
    "TRK-004": "11111111-0000-0000-0000-000000000004",
}

# ── Drivers (UUIDs match Supabase seed) ─────────────────────────────────────────
DRIVERS = {
    "juan":    "22222222-0000-0000-0000-000000000002",
    "maria":   "22222222-0000-0000-0000-000000000003",
    "roberto": "22222222-0000-0000-0000-000000000004",
    "ana":     "22222222-0000-0000-0000-000000000005",
}

DRIVER_NAMES = {
    "juan":    "Juan Dela Cruz",
    "maria":   "Maria Santos",
    "roberto": "Roberto Garcia",
    "ana":     "Ana Reyes",
}

# ── Truck behaviour profiles ────────────────────────────────────────────────────
PROFILES = {
    "standard":  {"consumption": 0.18, "jitter_kmh": 5.0},   # typical city truck
    "efficient": {"consumption": 0.14, "jitter_kmh": 4.0},   # newer/lighter truck
    "heavy":     {"consumption": 0.24, "jitter_kmh": 4.5},   # heavy-payload vehicle
    "stopngo":   {"consumption": 0.22, "jitter_kmh": 7.0},   # stop-and-go congestion
}

# ── Scenario definitions ────────────────────────────────────────────────────────
# Each scenario key maps to a set of truck runs.
# Truck starting positions are loaded from truck_state.json if available.
#
# trip fields:
#   driver          — key in DRIVERS
#   route           — key in DESTINATIONS
#   profile         — key in PROFILES
#   event           — "normal" | "theft" | "leak" | "overspeed"
#   planned_minutes — approximate trip time in real minutes (GPS_INTERVAL_S = 5 s)
#   event_minute    — (optional) minute into trip to inject event
#   pause_on_rest   — (optional) True: auto-pause when rest alert fires
#   pause_minutes   — (optional) real minutes to stay paused
#   handover_gap_min — (optional) minutes gap before next driver takes over
#   title           — human-readable label
SCENARIO_DEFS = {
    # ── Originals (kept, hub updated) ──────────────────────────────────────────
    "fleet": {
        "description": (
            "Baseline three-truck staggered fleet demo from Manila hub. "
            "Normal operations, no anomalies."
        ),
        "runs": [
            {
                "truck_code": "TRK-002",
                "depart_min": 0,
                "trips": [
                    {
                        "driver": "maria",
                        "route": "c5_east",
                        "profile": "standard",
                        "event": "normal",
                        "planned_minutes": 18,
                        "title": "Maria — C5 east dispatch",
                    }
                ],
            },
            {
                "truck_code": "TRK-003",
                "depart_min": 5,
                "trips": [
                    {
                        "driver": "roberto",
                        "route": "quezon_ne",
                        "profile": "heavy",
                        "event": "normal",
                        "planned_minutes": 24,
                        "title": "Roberto — Quezon NE dispatch",
                    }
                ],
            },
            {
                "truck_code": "TRK-004",
                "depart_min": 10,
                "trips": [
                    {
                        "driver": "ana",
                        "route": "cavite_sw",
                        "profile": "efficient",
                        "event": "normal",
                        "planned_minutes": 16,
                        "title": "Ana — Cavite south-west dispatch",
                    }
                ],
            },
        ],
    },

    "anomaly": {
        "description": (
            "ML anomaly validation. TRK-002 has a sudden fuel theft, "
            "TRK-003 has a gradual fuel leak. TRK-004 is the clean control."
        ),
        "runs": [
            {
                "truck_code": "TRK-002",
                "depart_min": 0,
                "trips": [
                    {
                        "driver": "maria",
                        "route": "c5_east",
                        "profile": "standard",
                        "event": "theft",
                        "event_minute": 11,
                        "planned_minutes": 18,
                        "title": "Maria — sudden fuel theft anomaly",
                    }
                ],
            },
            {
                "truck_code": "TRK-003",
                "depart_min": 3,
                "trips": [
                    {
                        "driver": "roberto",
                        "route": "quezon_ne",
                        "profile": "heavy",
                        "event": "leak",
                        "event_minute": 9,
                        "planned_minutes": 24,
                        "title": "Roberto — gradual fuel leak",
                    }
                ],
            },
            {
                "truck_code": "TRK-004",
                "depart_min": 8,
                "trips": [
                    {
                        "driver": "ana",
                        "route": "market_loop",
                        "profile": "efficient",
                        "event": "normal",
                        "planned_minutes": 14,
                        "title": "Ana — clean control run",
                    }
                ],
            },
        ],
    },

    "rest_alert": {
        "description": (
            "Rest-alert validation. Lower rest_distance_km in Settings first "
            "(e.g. 5 km). TRK-003 pauses automatically when rest alert fires."
        ),
        "runs": [
            {
                "truck_code": "TRK-003",
                "depart_min": 0,
                "trips": [
                    {
                        "driver": "roberto",
                        "route": "nlex_north",
                        "profile": "heavy",
                        "event": "normal",
                        "planned_minutes": 32,
                        "pause_on_rest": True,
                        "pause_minutes": 3,
                        "title": "Roberto — rest compliance demonstration",
                    }
                ],
            },
            {
                "truck_code": "TRK-004",
                "depart_min": 6,
                "trips": [
                    {
                        "driver": "ana",
                        "route": "cavite_sw",
                        "profile": "efficient",
                        "event": "normal",
                        "planned_minutes": 16,
                        "title": "Ana — parallel clean run",
                    }
                ],
            },
        ],
    },

    "handover": {
        "description": (
            "Same-truck driver handover demo. TRK-002 completes a short trip "
            "with Maria then pauses 3 min before Juan takes over for a longer run."
        ),
        "runs": [
            {
                "truck_code": "TRK-002",
                "depart_min": 0,
                "trips": [
                    {
                        "driver": "maria",
                        "route": "market_loop",
                        "profile": "standard",
                        "event": "normal",
                        "planned_minutes": 12,
                        "handover_gap_min": 3,
                        "title": "Maria — first dispatch before handover",
                    },
                    {
                        "driver": "juan",
                        "route": "quezon_ne",
                        "profile": "stopngo",
                        "event": "normal",
                        "planned_minutes": 22,
                        "title": "Juan — second dispatch after driver handover",
                    },
                ],
            },
            {
                "truck_code": "TRK-003",
                "depart_min": 3,
                "trips": [
                    {
                        "driver": "roberto",
                        "route": "c5_east",
                        "profile": "heavy",
                        "event": "normal",
                        "planned_minutes": 20,
                        "title": "Roberto — parallel city run",
                    }
                ],
            },
            {
                "truck_code": "TRK-004",
                "depart_min": 8,
                "trips": [
                    {
                        "driver": "ana",
                        "route": "cavite_sw",
                        "profile": "efficient",
                        "event": "normal",
                        "planned_minutes": 16,
                        "title": "Ana — parallel south-west dispatch",
                    }
                ],
            },
        ],
    },

    "full_demo": {
        "description": (
            "Comprehensive thesis showcase: staggered departures, anomaly on TRK-003, "
            "TRK-002 driver handover, rest-compliance pause, and long expressway run."
        ),
        "runs": [
            {
                "truck_code": "TRK-002",
                "depart_min": 0,
                "trips": [
                    {
                        "driver": "maria",
                        "route": "c5_east",
                        "profile": "standard",
                        "event": "normal",
                        "planned_minutes": 18,
                        "pause_on_rest": True,
                        "pause_minutes": 3,
                        "handover_gap_min": 2,
                        "title": "Maria — primary dispatch with rest compliance",
                    },
                    {
                        "driver": "juan",
                        "route": "market_loop",
                        "profile": "stopngo",
                        "event": "normal",
                        "planned_minutes": 14,
                        "title": "Juan — follow-up short loop by a different driver",
                    },
                ],
            },
            {
                "truck_code": "TRK-003",
                "depart_min": 4,
                "trips": [
                    {
                        "driver": "roberto",
                        "route": "quezon_ne",
                        "profile": "heavy",
                        "event": "leak",
                        "event_minute": 9,
                        "planned_minutes": 24,
                        "title": "Roberto — leak anomaly demonstration",
                    }
                ],
            },
            {
                "truck_code": "TRK-004",
                "depart_min": 8,
                "trips": [
                    {
                        "driver": "ana",
                        "route": "nlex_north",
                        "profile": "efficient",
                        "event": "normal",
                        "planned_minutes": 30,
                        "title": "Ana — long expressway run",
                    }
                ],
            },
        ],
    },

    # ── Group A — Normal operations, 4 trucks ──────────────────────────────────
    "group_a": {
        "description": (
            "Group A — Normal four-truck fleet operations from Manila hub. "
            "Staggered departures, no anomalies, varied routes and profiles."
        ),
        "runs": [
            {
                "truck_code": "TRK-001",
                "depart_min": 0,
                "trips": [
                    {
                        "driver": "juan",
                        "route": "port_manila",
                        "profile": "standard",
                        "event": "normal",
                        "planned_minutes": 10,
                        "title": "Juan — short harbour delivery from hub",
                    }
                ],
            },
            {
                "truck_code": "TRK-002",
                "depart_min": 5,
                "trips": [
                    {
                        "driver": "maria",
                        "route": "makati_cbd",
                        "profile": "efficient",
                        "event": "normal",
                        "planned_minutes": 18,
                        "title": "Maria — Makati CBD business run",
                    }
                ],
            },
            {
                "truck_code": "TRK-003",
                "depart_min": 12,
                "trips": [
                    {
                        "driver": "roberto",
                        "route": "marikina",
                        "profile": "heavy",
                        "event": "normal",
                        "planned_minutes": 22,
                        "title": "Roberto — Marikina valley heavy run",
                    }
                ],
            },
            {
                "truck_code": "TRK-004",
                "depart_min": 18,
                "trips": [
                    {
                        "driver": "ana",
                        "route": "moa_pasay",
                        "profile": "standard",
                        "event": "normal",
                        "planned_minutes": 14,
                        "title": "Ana — Mall of Asia waterfront delivery",
                    }
                ],
            },
        ],
    },

    # ── Group B — Anomaly events for ML testing ────────────────────────────────
    "group_b": {
        "description": (
            "Group B — Anomaly events. TRK-002 has sudden fuel theft, "
            "TRK-003 has a progressive fuel leak, TRK-001 and TRK-004 are controls."
        ),
        "runs": [
            {
                "truck_code": "TRK-001",
                "depart_min": 0,
                "trips": [
                    {
                        "driver": "juan",
                        "route": "makati_cbd",
                        "profile": "standard",
                        "event": "normal",
                        "planned_minutes": 16,
                        "title": "Juan — clean control run",
                    }
                ],
            },
            {
                "truck_code": "TRK-002",
                "depart_min": 2,
                "trips": [
                    {
                        "driver": "maria",
                        "route": "c5_east",
                        "profile": "standard",
                        "event": "theft",
                        "event_minute": 9,
                        "planned_minutes": 18,
                        "title": "Maria — fuel theft mid-route",
                    }
                ],
            },
            {
                "truck_code": "TRK-003",
                "depart_min": 5,
                "trips": [
                    {
                        "driver": "roberto",
                        "route": "quezon_ne",
                        "profile": "heavy",
                        "event": "leak",
                        "event_minute": 7,
                        "planned_minutes": 22,
                        "title": "Roberto — progressive fuel leak",
                    }
                ],
            },
            {
                "truck_code": "TRK-004",
                "depart_min": 8,
                "trips": [
                    {
                        "driver": "ana",
                        "route": "nlex_north",
                        "profile": "efficient",
                        "event": "normal",
                        "planned_minutes": 28,
                        "title": "Ana — long clean run (control)",
                    }
                ],
            },
        ],
    },

    # ── Group C — Driver reassignment on same truck ────────────────────────────
    "group_c": {
        "description": (
            "Group C — Driver reassignment. TRK-001 is driven by Juan then "
            "Ana takes over. TRK-002 is driven by Maria then Roberto continues."
        ),
        "runs": [
            {
                "truck_code": "TRK-001",
                "depart_min": 0,
                "trips": [
                    {
                        "driver": "juan",
                        "route": "port_manila",
                        "profile": "standard",
                        "event": "normal",
                        "planned_minutes": 12,
                        "handover_gap_min": 4,
                        "title": "Juan — first leg on TRK-001",
                    },
                    {
                        "driver": "ana",
                        "route": "marikina",
                        "profile": "standard",
                        "event": "normal",
                        "planned_minutes": 20,
                        "title": "Ana — takes over TRK-001 for second leg",
                    },
                ],
            },
            {
                "truck_code": "TRK-002",
                "depart_min": 3,
                "trips": [
                    {
                        "driver": "maria",
                        "route": "moa_pasay",
                        "profile": "efficient",
                        "event": "normal",
                        "planned_minutes": 14,
                        "handover_gap_min": 3,
                        "title": "Maria — first leg on TRK-002",
                    },
                    {
                        "driver": "roberto",
                        "route": "bgc_taguig",
                        "profile": "heavy",
                        "event": "normal",
                        "planned_minutes": 18,
                        "title": "Roberto — takes over TRK-002",
                    },
                ],
            },
            {
                "truck_code": "TRK-003",
                "depart_min": 5,
                "trips": [
                    {
                        "driver": "roberto",
                        "route": "navotas",
                        "profile": "heavy",
                        "event": "normal",
                        "planned_minutes": 18,
                        "title": "Roberto — parallel Navotas run on TRK-003",
                    }
                ],
            },
        ],
    },

    # ── Group D — Different truck behaviour profiles ────────────────────────────
    "group_d": {
        "description": (
            "Group D — Truck behaviour profiles. TRK-001 stop-and-go in Navotas, "
            "TRK-002 smooth expressway run, TRK-003 heavy payload, TRK-004 efficient city run."
        ),
        "runs": [
            {
                "truck_code": "TRK-001",
                "depart_min": 0,
                "trips": [
                    {
                        "driver": "juan",
                        "route": "navotas",
                        "profile": "stopngo",
                        "event": "normal",
                        "planned_minutes": 22,
                        "title": "Juan — stop-and-go in congested Navotas",
                    }
                ],
            },
            {
                "truck_code": "TRK-002",
                "depart_min": 4,
                "trips": [
                    {
                        "driver": "maria",
                        "route": "slex_south",
                        "profile": "efficient",
                        "event": "normal",
                        "planned_minutes": 38,
                        "title": "Maria — smooth SLEX expressway run",
                    }
                ],
            },
            {
                "truck_code": "TRK-003",
                "depart_min": 8,
                "trips": [
                    {
                        "driver": "roberto",
                        "route": "quezon_ne",
                        "profile": "heavy",
                        "event": "normal",
                        "planned_minutes": 22,
                        "title": "Roberto — heavy-payload city run",
                    }
                ],
            },
            {
                "truck_code": "TRK-004",
                "depart_min": 14,
                "trips": [
                    {
                        "driver": "ana",
                        "route": "market_loop",
                        "profile": "standard",
                        "event": "normal",
                        "planned_minutes": 12,
                        "title": "Ana — efficient short urban loop",
                    }
                ],
            },
        ],
    },

    # ── Group E — Multi-truck fleet, all 4 trucks staggered ────────────────────
    "group_e": {
        "description": (
            "Group E — Full fleet demo: all four trucks active with staggered "
            "departures, varied routes and profiles. Looks like a real operating day."
        ),
        "runs": [
            {
                "truck_code": "TRK-001",
                "depart_min": 0,
                "trips": [
                    {
                        "driver": "juan",
                        "route": "divisoria",
                        "profile": "stopngo",
                        "event": "normal",
                        "planned_minutes": 16,
                        "title": "Juan — Divisoria market delivery",
                    }
                ],
            },
            {
                "truck_code": "TRK-002",
                "depart_min": 5,
                "trips": [
                    {
                        "driver": "maria",
                        "route": "bgc_taguig",
                        "profile": "efficient",
                        "event": "normal",
                        "planned_minutes": 20,
                        "title": "Maria — BGC commercial run",
                    }
                ],
            },
            {
                "truck_code": "TRK-003",
                "depart_min": 12,
                "trips": [
                    {
                        "driver": "roberto",
                        "route": "nlex_north",
                        "profile": "heavy",
                        "event": "normal",
                        "planned_minutes": 32,
                        "title": "Roberto — long NLEX expressway run",
                    }
                ],
            },
            {
                "truck_code": "TRK-004",
                "depart_min": 20,
                "trips": [
                    {
                        "driver": "ana",
                        "route": "c5_east",
                        "profile": "standard",
                        "event": "normal",
                        "planned_minutes": 18,
                        "title": "Ana — C5 corridor run",
                    }
                ],
            },
        ],
    },

    # ── Group F — Alert testing (lower thresholds in Settings first) ───────────
    "group_f": {
        "description": (
            "Group F — Alert testing. Lower rest_distance_km to ~5 km in Settings "
            "before running. TRK-003 will pause on rest, TRK-002 triggers anomaly, "
            "TRK-004 triggers overspeed, TRK-001 runs cleanly for comparison."
        ),
        "runs": [
            {
                "truck_code": "TRK-001",
                "depart_min": 0,
                "trips": [
                    {
                        "driver": "juan",
                        "route": "makati_cbd",
                        "profile": "standard",
                        "event": "normal",
                        "planned_minutes": 18,
                        "title": "Juan — clean run for comparison",
                    }
                ],
            },
            {
                "truck_code": "TRK-002",
                "depart_min": 2,
                "trips": [
                    {
                        "driver": "maria",
                        "route": "c5_east",
                        "profile": "standard",
                        "event": "leak",
                        "event_minute": 8,
                        "planned_minutes": 20,
                        "title": "Maria — fuel leak for ML anomaly alert",
                    }
                ],
            },
            {
                "truck_code": "TRK-003",
                "depart_min": 0,
                "trips": [
                    {
                        "driver": "roberto",
                        "route": "quezon_ne",
                        "profile": "heavy",
                        "event": "normal",
                        "planned_minutes": 28,
                        "pause_on_rest": True,
                        "pause_minutes": 4,
                        "title": "Roberto — rest alert compliance (lower threshold first)",
                    }
                ],
            },
            {
                "truck_code": "TRK-004",
                "depart_min": 5,
                "trips": [
                    {
                        "driver": "ana",
                        "route": "nlex_north",
                        "profile": "efficient",
                        "event": "overspeed",
                        "event_minute": 12,
                        "planned_minutes": 30,
                        "title": "Ana — overspeed alert trigger",
                    }
                ],
            },
        ],
    },

    # ── Group G — Persistent fleet state demonstration ─────────────────────────
    "group_g": {
        "description": (
            "Group G — Persistent state demo. Run group_a first, then run group_g. "
            "Each truck starts from where it ended in the previous scenario run. "
            "This shows cross-run fleet continuity."
        ),
        "runs": [
            {
                "truck_code": "TRK-001",
                "depart_min": 0,
                "trips": [
                    {
                        "driver": "juan",
                        "route": "divisoria",
                        "profile": "stopngo",
                        "event": "normal",
                        "planned_minutes": 18,
                        "title": "Juan — continues from TRK-001 last position",
                    }
                ],
            },
            {
                "truck_code": "TRK-002",
                "depart_min": 5,
                "trips": [
                    {
                        "driver": "roberto",
                        "route": "navotas",
                        "profile": "heavy",
                        "event": "normal",
                        "planned_minutes": 22,
                        "title": "Roberto — continues from TRK-002 last position",
                    }
                ],
            },
            {
                "truck_code": "TRK-003",
                "depart_min": 8,
                "trips": [
                    {
                        "driver": "maria",
                        "route": "port_manila",
                        "profile": "efficient",
                        "event": "normal",
                        "planned_minutes": 14,
                        "title": "Maria — continues from TRK-003 last position",
                    }
                ],
            },
            {
                "truck_code": "TRK-004",
                "depart_min": 12,
                "trips": [
                    {
                        "driver": "ana",
                        "route": "moa_pasay",
                        "profile": "standard",
                        "event": "normal",
                        "planned_minutes": 12,
                        "title": "Ana — continues from TRK-004 last position",
                    }
                ],
            },
        ],
    },

    # ── Quick single-truck tests ───────────────────────────────────────────────
    "quick": {
        "description": "Quick single-truck normal run. Fast end-to-end test.",
        "runs": [
            {
                "truck_code": "TRK-002",
                "depart_min": 0,
                "trips": [
                    {
                        "driver": "maria",
                        "route": "port_manila",
                        "profile": "standard",
                        "event": "normal",
                        "planned_minutes": 8,
                        "title": "Maria — quick port delivery test",
                    }
                ],
            }
        ],
    },

    "quick_anomaly": {
        "description": (
            "Quick ML anomaly test. Theft event fires early so detection "
            "shows in dashboard within a few minutes."
        ),
        "runs": [
            {
                "truck_code": "TRK-002",
                "depart_min": 0,
                "trips": [
                    {
                        "driver": "maria",
                        "route": "makati_cbd",
                        "profile": "standard",
                        "event": "theft",
                        "event_minute": 4,
                        "planned_minutes": 12,
                        "title": "Maria — quick theft anomaly for ML detection",
                    }
                ],
            }
        ],
    },

    "quick_rest": {
        "description": (
            "Quick rest alert test. Lower rest_distance_km to 5 km in Settings "
            "first. TRK-003 pauses automatically when the threshold fires."
        ),
        "runs": [
            {
                "truck_code": "TRK-003",
                "depart_min": 0,
                "trips": [
                    {
                        "driver": "roberto",
                        "route": "quezon_ne",
                        "profile": "heavy",
                        "event": "normal",
                        "planned_minutes": 20,
                        "pause_on_rest": True,
                        "pause_minutes": 3,
                        "title": "Roberto — quick rest alert demo",
                    }
                ],
            }
        ],
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# PERSISTENT TRUCK STATE
# ══════════════════════════════════════════════════════════════════════════════

def load_truck_states():
    """Load last-known truck positions / fuel from disk.  Returns {} if not found."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as fh:
                data = json.load(fh)
            print(f"[state] Loaded persistent truck state from {STATE_FILE}")
            return data
        except Exception as exc:
            print(f"[state] Could not read {STATE_FILE}: {exc}")
    return {}


def save_truck_states(truck_states):
    """Persist truck positions / fuel to disk after a scenario completes."""
    try:
        with open(STATE_FILE, "w") as fh:
            json.dump(truck_states, fh, indent=2)
        print(f"[state] Truck state saved → {STATE_FILE}")
    except Exception as exc:
        print(f"[state] Could not save state: {exc}")


def reset_truck_state():
    """Delete the state file so trucks reset to hub on next run."""
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        print(f"[state] Persistent state cleared ({STATE_FILE})")
    else:
        print("[state] No persistent state file found — nothing to clear.")


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def haversine_km(lat1, lon1, lat2, lon2):
    radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return radius_km * 2 * math.asin(math.sqrt(a))


def polyline_distance_km(points):
    total = 0.0
    for idx in range(1, len(points)):
        total += haversine_km(points[idx - 1][0], points[idx - 1][1], points[idx][0], points[idx][1])
    return total


def minutes_to_clock_label(base_dt, minute_offset):
    return (base_dt + timedelta(minutes=minute_offset)).strftime("%H:%M")


def fetch_route(origin, destination, use_osrm=True):
    if not use_osrm:
        return [origin, destination]
    coords = f"{origin[1]},{origin[0]};{destination[1]},{destination[0]}"
    url = f"{OSRM}/route/v1/driving/{coords}?overview=full&geometries=geojson"
    try:
        response = requests.get(url, timeout=12)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == "Ok":
                return [(coord[1], coord[0]) for coord in data["routes"][0]["geometry"]["coordinates"]]
    except Exception as exc:
        print(f"    [OSRM] Failed ({exc}), using straight-line fallback")
    return [origin, destination]


def api_post(path, body, dry_run=False):
    return api_request("POST", path, body=body, dry_run=dry_run)


def api_patch(path, body=None, dry_run=False):
    return api_request("PATCH", path, body=body or {}, dry_run=dry_run)


def api_request(method, path, body=None, dry_run=False, headers=None, timeout=8, retries=4):
    if dry_run or not REQUESTS_OK:
        return {"_dry": True, "_ok": True, "_status": 0, "_latency_ms": 0}

    last_error = None
    for attempt in range(1, retries + 1):
        started = time.time()
        try:
            request_kwargs = {"timeout": timeout}
            if headers:
                request_kwargs["headers"] = headers
            if body is not None:
                request_kwargs["json"] = body

            response = HTTP.request(method, f"{BACKEND}{path}", **request_kwargs)
            latency_ms = round((time.time() - started) * 1000)
            try:
                payload = response.json() if response.content else {}
            except ValueError:
                payload = {}

            if response.ok:
                result = payload if isinstance(payload, dict) else {"data": payload}
                result.update({
                    "_ok": True,
                    "_status": response.status_code,
                    "_latency_ms": latency_ms,
                })
                return result

            error_text = (
                payload.get("error")
                if isinstance(payload, dict)
                else response.text[:200].strip()
            ) or response.reason
            last_error = f"HTTP {response.status_code}: {error_text}"
            print(f"  [api] {method} {path} attempt {attempt}/{retries} -> {last_error} ({latency_ms}ms)")
            if response.status_code < 500 and response.status_code != 429:
                break
        except requests.RequestException as exc:
            last_error = str(exc)
            print(f"  [api] {method} {path} attempt {attempt}/{retries} failed: {exc}")

        if attempt < retries:
            time.sleep(min(2 ** (attempt - 1), 5))

    return {
        "_ok": False,
        "_error": last_error or "Unknown backend error",
        "_status": None,
        "_latency_ms": None,
    }


def wait_for_backend(timeout_s=30):
    if not REQUESTS_OK:
        return False

    print(f"[sim] Checking backend health at {BACKEND} ...")
    deadline = time.time() + timeout_s
    attempt = 0

    while time.time() < deadline:
        attempt += 1
        try:
            response = HTTP.get(f"{BACKEND}/", timeout=4)
            if response.ok:
                print(f"[sim] Backend reachable at {BACKEND} (attempt {attempt})")
                return True
            print(f"[sim] Backend health check returned HTTP {response.status_code}")
        except requests.RequestException as exc:
            print(f"[sim] Backend not ready yet (attempt {attempt}): {exc}")
        time.sleep(min(2 ** (attempt - 1), 5))

    print(
        f"[sim] Backend unavailable at {BACKEND} after {timeout_s}s."
        " Start the backend first or set BACKEND_URL."
    )
    return False


def get_thresholds():
    response = api_request(
        "GET",
        "/settings/thresholds",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        timeout=5,
        retries=2,
    )
    if response.get("_ok"):
        return {
            "rest_hours":        response.get("rest_hours", 6),
            "rest_distance_km":  response.get("rest_distance_km", 300),
            "maintenance_km":    response.get("maintenance_km", 5000),
            "overspeed_kmh":     response.get("overspeed_kmh", 100),
        }
    return {
        "rest_hours": 6, "rest_distance_km": 300,
        "maintenance_km": 5000, "overspeed_kmh": 100,
    }


def supa_headers():
    return {
        "apikey":        SUPABASE_SVC_KEY,
        "Authorization": f"Bearer {SUPABASE_SVC_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal",
    }


def supa_delete(table):
    if not SUPABASE_URL or not SUPABASE_SVC_KEY:
        print(f"  [reset] Cannot delete {table} — SUPABASE_SERVICE_KEY not set")
        return
    filter_qs = "id=neq.00000000-0000-0000-0000-000000000000"
    response = requests.delete(
        f"{SUPABASE_URL}/rest/v1/{table}?{filter_qs}",
        headers=supa_headers(),
        timeout=15,
    )
    print(f"  [reset] {table}: HTTP {response.status_code}")


def supa_patch_all(table, body):
    if not SUPABASE_URL or not SUPABASE_SVC_KEY:
        return
    filter_qs = "id=neq.00000000-0000-0000-0000-000000000000"
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/{table}?{filter_qs}",
        headers=supa_headers(),
        json=body,
        timeout=10,
    )


def supa_insert(table, rows, chunk=400):
    if not rows:
        return 0
    if not SUPABASE_URL or not SUPABASE_SVC_KEY:
        raise RuntimeError(f"SUPABASE_SERVICE_KEY not set for {table}")

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    inserted = 0
    for index in range(0, len(rows), chunk):
        batch = rows[index:index + chunk]
        response = requests.post(url, headers=supa_headers(), json=batch, timeout=60)
        if response.status_code not in (200, 201, 204):
            raise RuntimeError(
                f"Supabase insert failed for {table}: HTTP {response.status_code} {response.text[:240]}"
            )
        inserted += len(batch)
    return inserted


def supa_rpc(function_name, payload):
    if not SUPABASE_URL or not SUPABASE_SVC_KEY:
        raise RuntimeError(f"SUPABASE_SERVICE_KEY not set for RPC {function_name}")

    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/rpc/{function_name}",
        headers=supa_headers(),
        json=payload,
        timeout=60,
    )
    if response.status_code not in (200, 201, 204):
        raise RuntimeError(
            f"Supabase RPC failed for {function_name}: HTTP {response.status_code} {response.text[:240]}"
        )
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def reset_db():
    print("\n[reset] Clearing operational data...")
    supa_delete("telemetry_logs")
    supa_delete("archived_telemetry_logs")
    supa_delete("alerts")
    supa_delete("trip_summaries")
    supa_delete("trip_sessions")
    supa_patch_all("trucks", {"status": "idle"})
    print("[reset] Done.\n")


# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════

class SimLogger:
    def __init__(self, tag):
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.base_tag  = f"{self.timestamp}_{tag}"
        self.csv_path  = os.path.join(LOG_DIR, f"sim_{self.base_tag}.csv")
        self._file     = open(self.csv_path, "w", newline="", encoding="utf-8")
        self._writer   = csv.DictWriter(
            self._file,
            fieldnames=[
                "ts", "scenario", "truck", "driver", "trip_label",
                "trip_id", "fuel", "speed", "lat", "lon",
                "odometer", "engine_status", "anomaly", "latency_ms",
            ],
        )
        self._writer.writeheader()
        self._lock = threading.Lock()

    def log(self, row):
        with self._lock:
            self._writer.writerow(row)
            self._file.flush()

    def write_text(self, suffix, content):
        path = os.path.join(LOG_DIR, f"{suffix}_{self.base_tag}")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def close(self):
        self._file.close()


# ══════════════════════════════════════════════════════════════════════════════
# ROUTE / TRIP SIMULATION
# ══════════════════════════════════════════════════════════════════════════════

class RoutePlayback:
    def __init__(self, route_points, planned_minutes):
        self.route_points = route_points
        self.total_ticks  = max(1, int(planned_minutes * 60 / GPS_INTERVAL_S))
        self.cumulative_km = [0.0]
        for idx in range(1, len(route_points)):
            prev = route_points[idx - 1]
            curr = route_points[idx]
            self.cumulative_km.append(
                self.cumulative_km[-1] + haversine_km(prev[0], prev[1], curr[0], curr[1])
            )
        self.total_distance_km = self.cumulative_km[-1] if len(self.cumulative_km) > 1 else 0.0

    def position_at_tick(self, moving_tick):
        if self.total_distance_km <= 0:
            lat, lon = self.route_points[-1]
            return lat, lon, 0.0

        target_distance = min(
            self.total_distance_km,
            self.total_distance_km * moving_tick / self.total_ticks,
        )
        for idx in range(1, len(self.cumulative_km)):
            left  = self.cumulative_km[idx - 1]
            right = self.cumulative_km[idx]
            if target_distance <= right:
                segment_km = max(right - left, 1e-9)
                ratio      = max(0.0, min(1.0, (target_distance - left) / segment_km))
                start = self.route_points[idx - 1]
                end   = self.route_points[idx]
                lat = start[0] + (end[0] - start[0]) * ratio
                lon = start[1] + (end[1] - start[1]) * ratio
                return lat, lon, target_distance
        lat, lon = self.route_points[-1]
        return lat, lon, self.total_distance_km


class TripSimulator:
    def __init__(self, prepared_trip, truck_state):
        self.trip    = prepared_trip
        self.profile = PROFILES[prepared_trip["profile"]]
        self.route   = RoutePlayback(prepared_trip["route_points"], prepared_trip["planned_minutes"])
        self.wall_tick    = 0
        self.moving_tick  = 0
        self.finished     = False
        self.trip_id      = None
        self.fuel         = truck_state["fuel"]
        self.odometer     = truck_state["odometer"]
        self.lat          = truck_state["lat"]
        self.lon          = truck_state["lon"]
        self.prev_distance = 0.0
        self.pause_active  = False
        self.pause_start_tick    = prepared_trip.get("pause_start_tick")
        self.pause_duration_ticks = prepared_trip.get("pause_duration_ticks", 0)
        self.pause_end_tick = (
            self.pause_start_tick + self.pause_duration_ticks
            if self.pause_start_tick is not None
            else None
        )
        self.pause_started  = False
        self.pause_resumed  = False
        self.leak_active    = False
        self.event_done     = False

    def _apply_event(self, delta_km):
        event      = self.trip["event"]
        event_tick = self.trip.get("event_tick")
        anomaly    = False

        if event == "theft" and event_tick is not None and self.wall_tick >= event_tick and not self.event_done:
            self.fuel = max(3.0, self.fuel - random.uniform(16, 24))
            self.event_done = True
            anomaly = True
        elif event == "leak" and event_tick is not None and self.wall_tick >= event_tick:
            self.leak_active = True
            anomaly = True
        elif event == "overspeed" and event_tick is not None and self.wall_tick >= event_tick and not self.event_done:
            self.event_done = True
            anomaly = True

        if self.leak_active and delta_km > 0:
            self.fuel = max(3.0, self.fuel - self.profile["consumption"] * 2.6 * delta_km)

        return anomaly

    def should_pause_now(self):
        return (
            self.pause_start_tick is not None
            and not self.pause_started
            and self.wall_tick >= self.pause_start_tick
        )

    def should_resume_now(self):
        return self.pause_active and self.pause_end_tick is not None and self.wall_tick >= self.pause_end_tick

    def tick(self):
        self.wall_tick += 1

        if self.pause_active:
            anomaly = False
            speed   = 0.0
            engine_status = "off"
            delta_km = 0.0
        else:
            self.moving_tick = min(self.route.total_ticks, self.moving_tick + 1)
            lat, lon, cumulative_distance = self.route.position_at_tick(self.moving_tick)
            delta_km = max(0.0, cumulative_distance - self.prev_distance)
            speed    = delta_km / GPS_INTERVAL_S * 3600
            speed   += random.uniform(-self.profile["jitter_kmh"], self.profile["jitter_kmh"])
            speed    = max(0.0, speed)
            self.lat = lat
            self.lon = lon
            self.odometer   += delta_km
            base_consumption = self.profile["consumption"] * delta_km + random.gauss(0, 0.01)
            self.fuel = max(3.0, min(100.0, self.fuel - max(0.0, base_consumption)))
            anomaly   = self._apply_event(delta_km)
            engine_status    = "on"
            self.prev_distance = cumulative_distance
            if self.trip["event"] == "overspeed" and self.trip.get("event_tick") == self.wall_tick:
                speed = max(speed, 112.0)

        if not self.pause_active and self.moving_tick >= self.route.total_ticks:
            self.finished = True

        return {
            "truck_id":   self.trip["truck_id"],
            "driver_id":  self.trip["driver_id"],
            "trip_id":    self.trip_id,
            "fuel_level": round(self.fuel, 2),
            "speed":      round(speed, 1),
            "odometer_km": round(self.odometer, 1),
            "lat":        round(self.lat, 6),
            "lon":        round(self.lon, 6),
            "engine_status": engine_status,
            "sent_at":    datetime.now(timezone.utc).isoformat(),
            "_anomaly":   anomaly,
        }


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO PREPARATION
# ══════════════════════════════════════════════════════════════════════════════

def build_trip_events(trip, thresholds):
    rest_minute        = None
    maintenance_minute = None

    rest_candidates    = []
    rest_distance_km   = thresholds.get("rest_distance_km", 0) or 0
    rest_hours         = thresholds.get("rest_hours", 0) or 0
    if rest_distance_km > 0 and trip["route_distance_km"] >= rest_distance_km:
        rest_candidates.append(
            (rest_distance_km / max(trip["route_distance_km"], 0.001)) * trip["planned_minutes"]
        )
    if rest_hours > 0 and trip["planned_minutes"] >= rest_hours * 60:
        rest_candidates.append(rest_hours * 60)
    if rest_candidates:
        rest_minute = round(min(rest_candidates), 1)

    maintenance_km = thresholds.get("maintenance_km", 0) or 0
    if maintenance_km > 0 and trip["route_distance_km"] >= maintenance_km:
        maintenance_minute = round(
            (maintenance_km / max(trip["route_distance_km"], 0.001)) * trip["planned_minutes"],
            1,
        )

    event_minute = trip.get("event_minute")
    if event_minute is None and trip["event"] in {"theft", "leak", "overspeed"}:
        event_minute = round(max(4.0, trip["planned_minutes"] * 0.55), 1)

    pause_start_min = None
    pause_end_min   = None
    if trip.get("pause_on_rest") and rest_minute is not None:
        pause_start_min = round(min(trip["planned_minutes"] - 1, rest_minute + 1), 1)
        pause_end_min   = round(pause_start_min + trip.get("pause_minutes", 0), 1)

    return {
        "rest_minute":        rest_minute,
        "maintenance_minute": maintenance_minute,
        "event_minute":       event_minute,
        "pause_start_minute": pause_start_min,
        "pause_end_minute":   pause_end_min,
        "rest_expected":        rest_minute is not None,
        "maintenance_expected": maintenance_minute is not None,
        "anomaly_expected":     trip["event"] in {"theft", "leak", "overspeed"},
        "pause_expected":       pause_start_min is not None,
    }


def build_progress_markers(trip):
    markers     = []
    total_minutes = int(math.ceil(trip["duration_minutes_total"]))
    local_checks  = sorted({minute for minute in range(0, total_minutes + 1, 5)})
    if total_minutes not in local_checks:
        local_checks.append(total_minutes)

    for local_minute in local_checks:
        absolute_minute = round(trip["start_offset_min"] + local_minute, 1)
        if local_minute == 0:
            message = (
                f'{trip["truck_code"]} departs from {trip["origin_label"]} with '
                f'{trip["driver_name"]} toward {trip["destination_label"]}.'
            )
        elif absolute_minute >= trip["end_offset_min"]:
            message = f'{trip["truck_code"]} ends the trip and becomes idle at {trip["destination_label"]}.'
        elif trip["pause_expected"] and trip["pause_start_minute"] <= local_minute < trip["pause_end_minute"]:
            message = f'{trip["truck_code"]} is paused for driver rest.'
        else:
            drive_window = trip["planned_minutes"]
            progress = min(99, int((min(local_minute, drive_window) / max(drive_window, 1)) * 100))
            message = (
                f'{trip["truck_code"]} is en route on {trip["route_label"]} '
                f'({progress}% progress).'
            )
        markers.append({"minute": absolute_minute, "message": message})
    return markers


def build_trip_timeline(trip):
    timeline = []
    timeline.extend(build_progress_markers(trip))

    if trip["anomaly_expected"]:
        detail = {
            "theft":    "Sudden ECU fuel drop — ML anomaly detection expected.",
            "leak":     "Gradual fuel leak pattern begins — ML anomaly detection expected.",
            "overspeed": "Overspeed event injected.",
        }.get(trip["event"], "Anomaly injected.")
        timeline.append({
            "minute":  trip["start_offset_min"] + trip["event_minute"],
            "message": f'{trip["truck_code"]}: {detail}',
        })

    if trip["rest_expected"]:
        timeline.append({
            "minute":  trip["start_offset_min"] + trip["rest_minute"],
            "message": f'{trip["truck_code"]}: Rest threshold reached — rest alert expected.',
        })

    if trip["maintenance_expected"]:
        timeline.append({
            "minute":  trip["start_offset_min"] + trip["maintenance_minute"],
            "message": f'{trip["truck_code"]}: Maintenance threshold reached.',
        })

    if trip["pause_expected"]:
        timeline.append({
            "minute":  trip["start_offset_min"] + trip["pause_start_minute"],
            "message": f'{trip["truck_code"]}: Driver presses pause/rest.',
        })
        timeline.append({
            "minute":  trip["start_offset_min"] + trip["pause_end_minute"],
            "message": f'{trip["truck_code"]}: Driver resumes after rest.',
        })

    if trip.get("handover_gap_min"):
        timeline.append({
            "minute":  trip["end_offset_min"],
            "message": f'{trip["truck_code"]}: Driver handoff window begins.',
        })

    deduped = {}
    for event in timeline:
        key = (round(event["minute"], 1), event["message"])
        deduped[key] = event
    return sorted(deduped.values(), key=lambda item: (item["minute"], item["message"]))


def build_scenario_timeline(prepared_runs):
    timeline_map = {}
    for run in prepared_runs:
        for trip in run["prepared_trips"]:
            for item in build_trip_timeline(trip):
                minute_key = round(item["minute"], 1)
                timeline_map.setdefault(minute_key, []).append(item["message"])

    timeline = []
    for minute in sorted(timeline_map):
        messages = sorted(set(timeline_map[minute]))
        timeline.append({"minute": minute, "messages": messages})
    return timeline


def prepare_scenario(scenario_name, thresholds, use_osrm, truck_states=None):
    """
    Build prepared_runs for execution.

    truck_states — dict keyed by truck_code with {lat, lon, fuel, odometer}.
    If provided, each truck's FIRST trip starts from its last-known position
    instead of the hub.  Subsequent trips in the same run chain from the
    previous trip's endpoint (unchanged existing behaviour).
    """
    scenario_def  = copy.deepcopy(SCENARIO_DEFS[scenario_name])
    prepared_runs = []
    route_cache   = {}

    for run in scenario_def["runs"]:
        truck_code = run["truck_code"]

        # Determine starting position for this truck's first trip.
        # Use persistent last-known position if available; fall back to hub.
        if truck_states and truck_code in truck_states:
            saved = truck_states[truck_code]
            current_origin = (saved["lat"], saved["lon"])
            current_origin_label = saved.get("location_label", "Last Known Position")
        else:
            current_origin       = HUB
            current_origin_label = HUB_LABEL

        current_offset = float(run["depart_min"])
        prepared_trips = []

        for trip_index, trip in enumerate(run["trips"], start=1):
            destination = DESTINATIONS[trip["route"]]
            route_key   = (
                round(current_origin[0], 5),
                round(current_origin[1], 5),
                trip["route"],
            )
            if route_key not in route_cache:
                route_cache[route_key] = fetch_route(current_origin, destination["coords"], use_osrm)
            route_points   = route_cache[route_key]
            route_distance = round(polyline_distance_km(route_points), 2)

            prepared_trip = {
                "trip_label":        f'{truck_code}-{trip_index}',
                "title":             trip["title"],
                "truck_code":        truck_code,
                "truck_id":          TRUCKS[truck_code],
                "driver":            trip["driver"],
                "driver_name":       DRIVER_NAMES[trip["driver"]],
                "driver_id":         DRIVERS[trip["driver"]],
                "route_key":         trip["route"],
                "route_label":       destination["summary"],
                "origin_label":      current_origin_label,
                "destination_label": destination["label"],
                "profile":           trip["profile"],
                "event":             trip["event"],
                "planned_minutes":   float(trip["planned_minutes"]),
                "route_points":      route_points,
                "route_distance_km": route_distance,
                "start_offset_min":  round(current_offset, 1),
            }

            prepared_trip.update(build_trip_events({**trip, **prepared_trip}, thresholds))
            prepared_trip["pause_start_tick"] = (
                int(prepared_trip["pause_start_minute"] * 60 / GPS_INTERVAL_S)
                if prepared_trip["pause_expected"]
                else None
            )
            prepared_trip["pause_duration_ticks"] = int(
                trip.get("pause_minutes", 0) * 60 / GPS_INTERVAL_S
            )
            prepared_trip["event_tick"] = (
                int(prepared_trip["event_minute"] * 60 / GPS_INTERVAL_S)
                if prepared_trip["event_minute"] is not None
                else None
            )
            prepared_trip["duration_minutes_total"] = round(
                prepared_trip["planned_minutes"]
                + (trip.get("pause_minutes", 0) if prepared_trip["pause_expected"] else 0),
                1,
            )
            prepared_trip["end_offset_min"] = round(
                prepared_trip["start_offset_min"] + prepared_trip["duration_minutes_total"],
                1,
            )
            prepared_trip["handover_gap_min"] = float(trip.get("handover_gap_min", 0))

            prepared_trips.append(prepared_trip)
            current_offset        = prepared_trip["end_offset_min"] + prepared_trip["handover_gap_min"]
            current_origin        = route_points[-1]
            current_origin_label  = destination["label"]

        prepared_runs.append({**run, "prepared_trips": prepared_trips})

    scenario_timeline = build_scenario_timeline(prepared_runs)
    total_duration = max(
        (trip["end_offset_min"] for run in prepared_runs for trip in run["prepared_trips"]),
        default=0,
    )
    return {
        "name":             scenario_name,
        "description":      scenario_def["description"],
        "prepared_runs":    prepared_runs,
        "timeline":         scenario_timeline,
        "duration_minutes": round(total_duration, 1),
    }


def print_scenario_rundown(prepared, thresholds, scenario_start_dt):
    print("\n[rundown] Scenario:", prepared["name"])
    print("[rundown]", prepared["description"])
    print(
        "[rundown] Thresholds:",
        f'rest_distance={thresholds.get("rest_distance_km")} km |',
        f'rest_hours={thresholds.get("rest_hours")} h |',
        f'maintenance={thresholds.get("maintenance_km")} km |',
        f'overspeed={thresholds.get("overspeed_kmh")} km/h',
    )
    print(f"[rundown] Approx total duration: {prepared['duration_minutes']} minutes\n")

    for run in prepared["prepared_runs"]:
        for trip in run["prepared_trips"]:
            start_clock = minutes_to_clock_label(scenario_start_dt, trip["start_offset_min"])
            end_clock   = minutes_to_clock_label(scenario_start_dt, trip["end_offset_min"])
            print(
                f"  {trip['trip_label']} | {trip['truck_code']} | {trip['driver_name']} |"
                f" start T+{trip['start_offset_min']}m ({start_clock}) |"
                f" end T+{trip['end_offset_min']}m ({end_clock})"
            )
            print(
                f"    origin={trip['origin_label']} -> destination={trip['destination_label']}"
                f" | anomaly={trip['anomaly_expected']}"
                f" | rest_alert={trip['rest_expected']}"
                f" | maintenance={trip['maintenance_expected']}"
                f" | pause_action={trip['pause_expected']}"
            )

    print("\n[timeline]")
    for item in prepared["timeline"]:
        minute_label = f"T+{item['minute']}m"
        joined = " | ".join(item["messages"])
        print(f"  {minute_label}: {joined}")


def rundown_to_markdown(prepared, thresholds, scenario_start_dt):
    lines = [
        f"# Scenario Rundown — {prepared['name']}",
        "",
        prepared["description"],
        "",
        "## Thresholds",
        "",
        f"- Rest distance: {thresholds.get('rest_distance_km')} km",
        f"- Rest hours: {thresholds.get('rest_hours')} h",
        f"- Maintenance: {thresholds.get('maintenance_km')} km",
        f"- Overspeed: {thresholds.get('overspeed_kmh')} km/h",
        "",
        "## Approximate duration",
        "",
        f"- {prepared['duration_minutes']} minutes",
        "",
        "## Trips",
        "",
    ]

    for run in prepared["prepared_runs"]:
        for trip in run["prepared_trips"]:
            lines.extend([
                f"### {trip['trip_label']} — {trip['truck_code']}",
                "",
                f"- Driver: {trip['driver_name']}",
                f"- Start: T+{trip['start_offset_min']}m"
                f" ({minutes_to_clock_label(scenario_start_dt, trip['start_offset_min'])})",
                f"- End: T+{trip['end_offset_min']}m"
                f" ({minutes_to_clock_label(scenario_start_dt, trip['end_offset_min'])})",
                f"- Origin: {trip['origin_label']}",
                f"- Destination: {trip['destination_label']}",
                f"- Route behaviour: {trip['route_label']}",
                f"- Anomaly expected: {trip['anomaly_expected']}",
                f"- Rest alert expected: {trip['rest_expected']}",
                f"- Maintenance alert expected: {trip['maintenance_expected']}",
                f"- Pause/rest action expected: {trip['pause_expected']}",
                "",
            ])

    lines.extend(["## Timeline", ""])
    for item in prepared["timeline"]:
        lines.append(f"- T+{item['minute']}m: {' | '.join(item['messages'])}")
    lines.append("")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# TRUCK STATE INITIALISATION
# ══════════════════════════════════════════════════════════════════════════════

def initialize_truck_states(force_hub=False):
    """
    Return a dict of truck states keyed by truck_code.

    Priority:
      1. truck_state.json (persistent last-known position)  — unless force_hub=True
      2. HUB origin with randomised fuel / odometer
    """
    saved = {} if force_hub else load_truck_states()
    states = {}
    for truck_code in TRUCKS:
        if truck_code in saved:
            s = saved[truck_code]
            states[truck_code] = {
                "fuel":           float(s.get("fuel",     random.uniform(70, 92))),
                "odometer":       float(s.get("odometer", random.uniform(16000, 52000))),
                "lat":            float(s.get("lat",      HUB[0])),
                "lon":            float(s.get("lon",      HUB[1])),
                "location_label": s.get("location_label", HUB_LABEL),
            }
        else:
            states[truck_code] = {
                "fuel":           round(random.uniform(76, 92), 2),
                "odometer":       round(random.uniform(16000, 52000), 1),
                "lat":            HUB[0],
                "lon":            HUB[1],
                "location_label": HUB_LABEL,
            }
    return states


def emit_idle_baseline(truck_states, dry_run):
    print("[sim] Seeding idle baseline telemetry for all demo trucks...")
    for truck_code, truck_id in TRUCKS.items():
        state = truck_states[truck_code]
        payload = {
            "truck_id":     truck_id,
            "fuel_level":   state["fuel"],
            "speed":        0,
            "odometer_km":  state["odometer"],
            "lat":          state["lat"],
            "lon":          state["lon"],
            "engine_status": "off",
            "sent_at":      datetime.now(timezone.utc).isoformat(),
        }
        api_post("/telemetry", payload, dry_run=dry_run)
        time.sleep(0.15)


# ══════════════════════════════════════════════════════════════════════════════
# TRIP EXECUTION
# ══════════════════════════════════════════════════════════════════════════════

def wait_until_offset(scenario_started_at, offset_minutes, stop_event):
    target = scenario_started_at + offset_minutes * 60
    while not stop_event.is_set():
        remaining = target - time.time()
        if remaining <= 0:
            return True
        time.sleep(min(1.0, remaining))
    return False


def run_trip(prepared_trip, truck_state, logger, stop_event, dry_run, scenario_name):
    simulator = TripSimulator(prepared_trip, truck_state)

    start_body = {
        "truck_id":  prepared_trip["truck_id"],
        "driver_id": prepared_trip["driver_id"],
        "start_lat": truck_state["lat"],
        "start_lon": truck_state["lon"],
    }
    start_resp = api_post("/trip/start", start_body, dry_run=dry_run)
    if not start_resp.get("_ok", True):
        print(
            f"\n  [{prepared_trip['trip_label']}] could not start trip:"
            f" {start_resp.get('_error', 'backend unavailable')}"
        )
        return truck_state
    simulator.trip_id = (
        start_resp.get("id") or start_resp.get("trip_id") or f"dry-{uuid.uuid4().hex[:8]}"
    )

    print(
        f"\n  [{prepared_trip['trip_label']}] started"
        f" | truck={prepared_trip['truck_code']}"
        f" | driver={prepared_trip['driver_name']}"
        f" | route={prepared_trip['destination_label']}"
        f" | event={prepared_trip['event']}"
        f" | trip={str(simulator.trip_id)[:8]}..."
    )

    while not stop_event.is_set():
        if simulator.should_pause_now():
            api_post("/trip/pause", {"trip_id": simulator.trip_id}, dry_run=dry_run)
            simulator.pause_active  = True
            simulator.pause_started = True
            print(f"  [{prepared_trip['trip_label']}] pause/rest started")

        if simulator.should_resume_now():
            api_post("/trip/resume", {"trip_id": simulator.trip_id}, dry_run=dry_run)
            simulator.pause_active  = False
            simulator.pause_resumed = True
            print(f"  [{prepared_trip['trip_label']}] trip resumed after rest")

        payload = simulator.tick()
        clean   = {k: v for k, v in payload.items() if not k.startswith("_")}
        flag    = " *** ANOMALY CANDIDATE ***" if payload["_anomaly"] else ""

        if not dry_run and REQUESTS_OK:
            response  = api_post("/telemetry", clean, dry_run=dry_run)
            latency_ms = response.get("_latency_ms")
            status_code = response.get("_status", "ERR")
            if response.get("_ok"):
                print(
                    f"  [{prepared_trip['trip_label']}] step={simulator.wall_tick:>4}"
                    f" fuel={clean['fuel_level']:>5.1f}% speed={clean['speed']:>5.1f}"
                    f" {clean['engine_status']:>3} {status_code} {latency_ms}ms{flag}"
                )
            else:
                latency_ms = -1
                print(
                    f"  [{prepared_trip['trip_label']}] telemetry retry exhausted"
                    f" | status={status_code} | error={response.get('_error')}{flag}"
                )
        else:
            latency_ms = 0
            print(
                f"  [{prepared_trip['trip_label']}] [dry] step={simulator.wall_tick:>4}"
                f" fuel={clean['fuel_level']:>5.1f}% speed={clean['speed']:>5.1f}"
                f" {clean['engine_status']:>3}{flag}"
            )

        logger.log({
            "ts":           clean["sent_at"],
            "scenario":     scenario_name,
            "truck":        prepared_trip["truck_code"],
            "driver":       prepared_trip["driver"],
            "trip_label":   prepared_trip["trip_label"],
            "trip_id":      str(simulator.trip_id)[:8],
            "fuel":         clean["fuel_level"],
            "speed":        clean["speed"],
            "lat":          clean["lat"],
            "lon":          clean["lon"],
            "odometer":     clean["odometer_km"],
            "engine_status": clean["engine_status"],
            "anomaly":      payload["_anomaly"],
            "latency_ms":   latency_ms,
        })

        if simulator.finished:
            break
        time.sleep(GPS_INTERVAL_S)

    api_post(
        "/trip/end",
        {"trip_id": simulator.trip_id, "end_lat": simulator.lat, "end_lon": simulator.lon},
        dry_run=dry_run,
    )
    print(f"  [{prepared_trip['trip_label']}] ended | trip={str(simulator.trip_id)[:8]}")

    return {
        "fuel":           simulator.fuel,
        "odometer":       simulator.odometer,
        "lat":            simulator.lat,
        "lon":            simulator.lon,
        "location_label": prepared_trip["destination_label"],
    }


def run_truck_sequence(run, scenario_started_at, logger, stop_event, dry_run, truck_states, scenario_name):
    if not run["prepared_trips"]:
        return

    first_start = run["prepared_trips"][0]["start_offset_min"]
    if not wait_until_offset(scenario_started_at, first_start, stop_event):
        return

    truck_code  = run["truck_code"]
    truck_state = truck_states[truck_code]

    for index, trip in enumerate(run["prepared_trips"]):
        if stop_event.is_set():
            return

        if index > 0:
            handover_gap = run["prepared_trips"][index - 1].get("handover_gap_min", 0)
            if handover_gap > 0:
                print(
                    f"  [{truck_code}] driver handover gap: {handover_gap} minute(s)"
                    f" before {trip['driver_name']} takes over"
                )

        truck_state = run_trip(trip, truck_state, logger, stop_event, dry_run, scenario_name)
        truck_states[truck_code] = truck_state


# ══════════════════════════════════════════════════════════════════════════════
# SIMULATION ORCHESTRATION
# ══════════════════════════════════════════════════════════════════════════════

def parse_backfill_date(value, label):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{label} must use YYYY-MM-DD format") from exc


def iter_backfill_dates(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def build_backfill_day_states(rolling_odometer, rng):
    states = {}
    for truck_code in TRUCKS:
        states[truck_code] = {
            "fuel": round(rng.uniform(78, 96), 2),
            "odometer": round(rolling_odometer.get(truck_code, rng.uniform(16000, 52000)), 1),
            "lat": HUB[0],
            "lon": HUB[1],
            "location_label": HUB_LABEL,
        }
    return states


def choose_backfill_bundle_count(rng, day, min_bundles, max_bundles):
    min_bundles = max(1, int(min_bundles))
    max_bundles = max(min_bundles, int(max_bundles))
    if day.weekday() >= 5 and max_bundles > min_bundles:
        max_bundles -= 1
    return rng.randint(min_bundles, max_bundles)


def build_historical_alert_rows(prepared_trip, trip_id, trip_start_dt, trip_end_dt, final_fuel):
    rows = []

    def add_alert(minute_offset, alert_type, message, severity):
        timestamp = (trip_start_dt + timedelta(minutes=minute_offset)).isoformat()
        rows.append({
            "id": str(uuid.uuid4()),
            "truck_id": prepared_trip["truck_id"],
            "driver_id": prepared_trip["driver_id"],
            "trip_id": trip_id,
            "timestamp": timestamp,
            "alert_type": alert_type,
            "message": message,
            "severity": severity,
            "is_resolved": True,
            "created_at": timestamp,
        })

    if prepared_trip["rest_expected"] and prepared_trip["rest_minute"] is not None:
        add_alert(
            prepared_trip["rest_minute"],
            "rest_alert",
            f"Historical backfill: rest threshold reached on {prepared_trip['truck_code']}.",
            "medium",
        )

    if prepared_trip["maintenance_expected"] and prepared_trip["maintenance_minute"] is not None:
        add_alert(
            prepared_trip["maintenance_minute"],
            "maintenance",
            f"Historical backfill: maintenance threshold reached on {prepared_trip['truck_code']}.",
            "medium",
        )

    if prepared_trip["anomaly_expected"] and prepared_trip["event_minute"] is not None:
        event_label = {
            "theft": "sudden ECU fuel drop",
            "leak": "gradual fuel leak",
            "overspeed": "overspeed",
        }.get(prepared_trip["event"], "anomaly")
        add_alert(
            prepared_trip["event_minute"],
            "fuel_anomaly" if prepared_trip["event"] != "overspeed" else "overspeed",
            f"Historical backfill: {event_label} detected on {prepared_trip['truck_code']}.",
            "high",
        )

    if final_fuel <= 20:
        low_fuel_time = max(trip_start_dt + timedelta(minutes=1), trip_end_dt - timedelta(minutes=1))
        rows.append({
            "id": str(uuid.uuid4()),
            "truck_id": prepared_trip["truck_id"],
            "driver_id": prepared_trip["driver_id"],
            "trip_id": trip_id,
            "timestamp": low_fuel_time.isoformat(),
            "alert_type": "low_fuel",
            "message": f"Historical backfill: low fuel observed on {prepared_trip['truck_code']}.",
            "severity": "medium",
            "is_resolved": True,
            "created_at": low_fuel_time.isoformat(),
        })

    return rows


def simulate_historical_trip(prepared_trip, truck_state, scenario_name, scenario_start_dt, logger, rng):
    simulator = TripSimulator(prepared_trip, truck_state)
    simulator.trip_id = str(uuid.uuid4())

    trip_start_dt = scenario_start_dt + timedelta(minutes=prepared_trip["start_offset_min"])
    trip_end_dt = scenario_start_dt + timedelta(minutes=prepared_trip["end_offset_min"])
    trip_start_odometer = truck_state["odometer"]
    telemetry_rows = []

    while True:
        if simulator.should_pause_now():
            simulator.pause_active = True
            simulator.pause_started = True

        if simulator.should_resume_now():
            simulator.pause_active = False
            simulator.pause_resumed = True

        payload = simulator.tick()
        event_ts = trip_start_dt + timedelta(seconds=simulator.wall_tick * GPS_INTERVAL_S)
        anomaly_flag = bool(payload["_anomaly"])
        telemetry_rows.append({
            "id": str(uuid.uuid4()),
            "truck_id": prepared_trip["truck_id"],
            "driver_id": prepared_trip["driver_id"],
            "trip_id": simulator.trip_id,
            "timestamp": event_ts.isoformat(),
            "fuel_level": round(payload["fuel_level"], 2),
            "lat": round(payload["lat"], 6),
            "lon": round(payload["lon"], 6),
            "speed": round(payload["speed"], 1),
            "odometer_km": round(payload["odometer_km"], 1),
            "engine_status": payload["engine_status"],
            "anomaly_flag": anomaly_flag,
            "anomaly_score": round(rng.uniform(0.76, 0.95), 3) if anomaly_flag else None,
            "model_source": "combined" if anomaly_flag else None,
            "created_at": event_ts.isoformat(),
        })

        logger.log({
            "ts": event_ts.isoformat(),
            "scenario": scenario_name,
            "truck": prepared_trip["truck_code"],
            "driver": prepared_trip["driver"],
            "trip_label": prepared_trip["trip_label"],
            "trip_id": str(simulator.trip_id)[:8],
            "fuel": payload["fuel_level"],
            "speed": payload["speed"],
            "lat": payload["lat"],
            "lon": payload["lon"],
            "odometer": payload["odometer_km"],
            "engine_status": payload["engine_status"],
            "anomaly": anomaly_flag,
            "latency_ms": 0,
        })

        if simulator.finished:
            break

    trip_row = {
        "id": simulator.trip_id,
        "truck_id": prepared_trip["truck_id"],
        "driver_id": prepared_trip["driver_id"],
        "start_time": trip_start_dt.isoformat(),
        "end_time": trip_end_dt.isoformat(),
        "trip_status": "ended",
        "start_lat": truck_state["lat"],
        "start_lon": truck_state["lon"],
        "end_lat": round(simulator.lat, 6),
        "end_lon": round(simulator.lon, 6),
        "distance_km": round(max(0.0, simulator.odometer - trip_start_odometer), 1),
        "operating_hours": round(prepared_trip["duration_minutes_total"] / 60.0, 2),
        "created_at": trip_start_dt.isoformat(),
    }

    return {
        "trip_row": trip_row,
        "telemetry_rows": telemetry_rows,
        "alert_rows": build_historical_alert_rows(
            prepared_trip,
            simulator.trip_id,
            trip_start_dt,
            trip_end_dt,
            simulator.fuel,
        ),
        "trip_id": simulator.trip_id,
        "final_state": {
            "fuel": simulator.fuel,
            "odometer": simulator.odometer,
            "lat": simulator.lat,
            "lon": simulator.lon,
            "location_label": prepared_trip["destination_label"],
        },
        "trip_end_dt": trip_end_dt,
    }


def run_historical_backfill(
    start_date_str,
    end_date_str,
    use_osrm,
    dry_run,
    min_bundles_per_day,
    max_bundles_per_day,
    seed,
    archive_retention_days,
):
    start_date = parse_backfill_date(start_date_str, "backfill start date")
    end_date = parse_backfill_date(end_date_str, "backfill end date")
    if end_date < start_date:
        raise ValueError("backfill end date must be on or after the start date")

    thresholds = get_thresholds()
    rng = random.Random(seed)
    logger = SimLogger(HISTORICAL_SCENARIO)
    rolling_odometer = {
        truck_code: round(rng.uniform(16000, 52000), 1)
        for truck_code in TRUCKS
    }

    summary = {
        "mode": HISTORICAL_SCENARIO,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "seed": seed,
        "thresholds": thresholds,
        "bundles": [],
        "trip_count": 0,
        "telemetry_count": 0,
        "alert_count": 0,
        "summary_refresh_count": 0,
        "scenario_counts": {},
        "archive_result": None,
    }

    print(
        f"\n[backfill] Historical backfill from {summary['start_date']} to {summary['end_date']}"
        f" | bundles/day={min_bundles_per_day}-{max_bundles_per_day} | seed={seed}"
    )

    for day in iter_backfill_dates(start_date, end_date):
        day_states = build_backfill_day_states(rolling_odometer, rng)
        bundle_count = choose_backfill_bundle_count(rng, day, min_bundles_per_day, max_bundles_per_day)
        next_start_minute = rng.randint(5 * 60 + 30, 9 * 60 + 30)

        for _bundle_index in range(bundle_count):
            template_name = rng.choice(HISTORICAL_TEMPLATE_SCENARIOS)
            summary["scenario_counts"][template_name] = summary["scenario_counts"].get(template_name, 0) + 1
            scenario_start_dt = datetime(day.year, day.month, day.day, tzinfo=MANILA_TZ) + timedelta(minutes=next_start_minute)
            prepared = prepare_scenario(template_name, thresholds, use_osrm, day_states)

            trip_rows = []
            telemetry_rows = []
            alert_rows = []
            bundle_end_dt = scenario_start_dt

            for run in prepared["prepared_runs"]:
                truck_code = run["truck_code"]
                truck_state = day_states[truck_code]
                for trip in run["prepared_trips"]:
                    generated = simulate_historical_trip(trip, truck_state, template_name, scenario_start_dt, logger, rng)
                    trip_rows.append(generated["trip_row"])
                    telemetry_rows.extend(generated["telemetry_rows"])
                    alert_rows.extend(generated["alert_rows"])
                    truck_state = generated["final_state"]
                    day_states[truck_code] = truck_state
                    bundle_end_dt = max(bundle_end_dt, generated["trip_end_dt"])

            if dry_run:
                print(
                    f"[backfill] [dry] {day.isoformat()} {template_name}"
                    f" | trips={len(trip_rows)} | logs={len(telemetry_rows)} | alerts={len(alert_rows)}"
                )
            else:
                supa_insert("trip_sessions", trip_rows)
                supa_insert("telemetry_logs", telemetry_rows)
                if alert_rows:
                    supa_insert("alerts", alert_rows)
                for row in trip_rows:
                    supa_rpc("refresh_trip_summary", {"p_trip_id": row["id"]})
                    summary["summary_refresh_count"] += 1
                print(
                    f"[backfill] {day.isoformat()} {template_name}"
                    f" | trips={len(trip_rows)} | logs={len(telemetry_rows)} | alerts={len(alert_rows)}"
                )

            summary["trip_count"] += len(trip_rows)
            summary["telemetry_count"] += len(telemetry_rows)
            summary["alert_count"] += len(alert_rows)
            summary["bundles"].append({
                "date": day.isoformat(),
                "template": template_name,
                "scenario_start": scenario_start_dt.isoformat(),
                "trip_count": len(trip_rows),
                "telemetry_count": len(telemetry_rows),
                "alert_count": len(alert_rows),
            })

            next_start_minute = int(
                (bundle_end_dt - datetime(day.year, day.month, day.day, tzinfo=MANILA_TZ)).total_seconds() / 60
            ) + rng.randint(40, 120)

        for truck_code, state in day_states.items():
            rolling_odometer[truck_code] = round(state["odometer"], 1)

    if not dry_run and summary["trip_count"] > 0:
        summary["archive_result"] = supa_rpc(
            "archive_ended_trip_logs",
            {
                "p_retention_days": int(archive_retention_days),
                "p_max_trips": max(summary["trip_count"] + 20, 200),
                "p_dry_run": False,
            },
        )

    markdown_lines = [
        "# Historical Backfill Summary",
        "",
        f"- Date range: {summary['start_date']} to {summary['end_date']}",
        f"- Seed: {summary['seed']}",
        f"- Trips inserted: {summary['trip_count']}",
        f"- Telemetry rows inserted: {summary['telemetry_count']}",
        f"- Alerts inserted: {summary['alert_count']}",
        f"- Trip summaries refreshed: {summary['summary_refresh_count']}",
        "",
        "## Scenario usage",
        "",
    ]
    for template_name in sorted(summary["scenario_counts"]):
        markdown_lines.append(f"- {template_name}: {summary['scenario_counts'][template_name]} bundle(s)")
    markdown_lines.extend(["", "## Bundles", ""])
    for bundle in summary["bundles"]:
        markdown_lines.append(
            f"- {bundle['date']} | {bundle['template']} | start={bundle['scenario_start']} |"
            f" trips={bundle['trip_count']} | logs={bundle['telemetry_count']} | alerts={bundle['alert_count']}"
        )

    logger.write_text("historical_backfill.md", "\n".join(markdown_lines) + "\n")
    logger.write_text("historical_backfill.json", json.dumps(summary, indent=2))
    logger.close()

    print(
        f"\n[backfill] Completed | trips={summary['trip_count']}"
        f" | logs={summary['telemetry_count']} | alerts={summary['alert_count']}"
    )
    if summary["archive_result"] is not None:
        print(f"[backfill] Archive RPC result: {summary['archive_result']}")


def run_simulation(scenario_name, use_osrm, dry_run, print_rundown_only, force_hub=False):
    if not dry_run and not print_rundown_only and not wait_for_backend():
        return

    # Load persistent state BEFORE preparing scenarios so routes start
    # from each truck's last known position.
    truck_states = initialize_truck_states(force_hub=force_hub)

    thresholds        = get_thresholds()
    scenario_started_at = time.time()
    scenario_start_dt   = datetime.now()
    prepared = prepare_scenario(scenario_name, thresholds, use_osrm, truck_states)

    logger   = SimLogger(scenario_name)
    markdown = rundown_to_markdown(prepared, thresholds, scenario_start_dt)
    json_blob = json.dumps(
        {
            "scenario":         prepared["name"],
            "description":      prepared["description"],
            "duration_minutes": prepared["duration_minutes"],
            "thresholds":       thresholds,
            "runs":             prepared["prepared_runs"],
            "timeline":         prepared["timeline"],
        },
        indent=2,
        default=str,
    )
    md_path   = logger.write_text("scenario_rundown.md", markdown)
    json_path = logger.write_text("scenario_rundown.json", json_blob)

    print_scenario_rundown(prepared, thresholds, scenario_start_dt)
    print(f"\n[rundown] Markdown saved to: {md_path}")
    print(f"[rundown] JSON saved to: {json_path}")

    if print_rundown_only:
        logger.close()
        return

    emit_idle_baseline(truck_states, dry_run=dry_run)

    stop_event = threading.Event()

    print(
        f"\n[sim] Scenario={scenario_name}"
        f" | trucks={len(prepared['prepared_runs'])}"
        f" | duration~{prepared['duration_minutes']} min"
        f" | osrm={'on' if use_osrm else 'off'}"
    )
    print(f"[sim] Backend: {BACKEND}")
    print(f"[sim] Hub: {HUB_LABEL}")
    print("[sim] Ctrl+C to stop all trucks cleanly\n")

    threads = []
    for run in prepared["prepared_runs"]:
        thread = threading.Thread(
            target=run_truck_sequence,
            args=(run, scenario_started_at, logger, stop_event, dry_run, truck_states, scenario_name),
            daemon=True,
        )
        thread.start()
        threads.append(thread)

    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        print("\n[sim] Keyboard interrupt — signaling all trucks to stop...")
        stop_event.set()
        for thread in threads:
            thread.join(timeout=10)

    logger.close()

    # Persist truck positions so the next scenario starts from where they ended.
    if not dry_run:
        save_truck_states(truck_states)

    print("\n[sim] All scheduled trips completed.")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    scenario_choices = sorted(set(SCENARIO_DEFS.keys()) | {HISTORICAL_SCENARIO})

    parser = argparse.ArgumentParser(
        description="Fleet Simulation v6 — thesis IoT fleet demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join([
            "Available scenarios:",
            *[
                f"  {name:<18} "
                f"{(SCENARIO_DEFS.get(name) or {'description': 'Generate completed historical trips directly in Supabase.'})['description'][:70]}"
                for name in scenario_choices
            ],
        ]),
    )
    parser.add_argument(
        "--scenario",
        default="fleet",
        choices=scenario_choices,
        help="Simulation scenario to run (default: fleet)",
    )
    parser.add_argument(
        "--no-osrm",
        action="store_true",
        help="Skip OSRM and use straight-line fallback routes",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payloads without posting to the backend",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe operational data in Supabase before starting",
    )
    parser.add_argument(
        "--reset-only",
        action="store_true",
        help="Wipe operational data and exit (does not reset truck state)",
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Clear persistent truck_state.json so trucks start from hub",
    )
    parser.add_argument(
        "--force-hub",
        action="store_true",
        help="Ignore persistent state; start all trucks from hub this run only",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="List all available scenarios and exit",
    )
    parser.add_argument(
        "--print-rundown-only",
        action="store_true",
        help="Print scenario rundown without running the live simulation",
    )
    parser.add_argument(
        "--backfill-start",
        default=DEFAULT_BACKFILL_START,
        help=f"Historical backfill start date YYYY-MM-DD (default: {DEFAULT_BACKFILL_START})",
    )
    parser.add_argument(
        "--backfill-end",
        default=DEFAULT_BACKFILL_END,
        help=f"Historical backfill end date YYYY-MM-DD (default: {DEFAULT_BACKFILL_END})",
    )
    parser.add_argument(
        "--backfill-min-bundles-per-day",
        type=int,
        default=1,
        help="Minimum historical scenario bundles to generate per day (default: 1)",
    )
    parser.add_argument(
        "--backfill-max-bundles-per-day",
        type=int,
        default=2,
        help="Maximum historical scenario bundles to generate per day (default: 2)",
    )
    parser.add_argument(
        "--backfill-seed",
        type=int,
        default=20260405,
        help="Random seed for historical backfill reproducibility",
    )
    parser.add_argument(
        "--backfill-retention-days",
        type=int,
        default=30,
        help="Retention threshold passed to archive_ended_trip_logs after backfill (default: 30)",
    )
    args = parser.parse_args()

    if args.list_scenarios:
        print("\nAvailable simulation scenarios:\n")
        for name in scenario_choices:
            desc = (SCENARIO_DEFS.get(name) or {"description": "Generate completed historical trips directly in Supabase."})["description"]
            print(f"  {name:<18} {desc[:80]}")
        print()
        sys.exit(0)

    if args.reset_state:
        reset_truck_state()
        if not args.reset_only and "--scenario" not in sys.argv:
            sys.exit(0)

    if args.reset_only:
        reset_db()
        sys.exit(0)

    if args.reset:
        reset_db()

    if args.scenario == HISTORICAL_SCENARIO:
        run_historical_backfill(
            start_date_str=args.backfill_start,
            end_date_str=args.backfill_end,
            use_osrm=not args.no_osrm,
            dry_run=args.dry_run,
            min_bundles_per_day=args.backfill_min_bundles_per_day,
            max_bundles_per_day=args.backfill_max_bundles_per_day,
            seed=args.backfill_seed,
            archive_retention_days=args.backfill_retention_days,
        )
        return

    run_simulation(
        scenario_name=args.scenario,
        use_osrm=not args.no_osrm,
        dry_run=args.dry_run,
        print_rundown_only=args.print_rundown_only,
        force_hub=args.force_hub,
    )


if __name__ == "__main__":
    main()
