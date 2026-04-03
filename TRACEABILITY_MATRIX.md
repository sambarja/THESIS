# Traceability Matrix
## "An IoT-Enabled System for Real-Time Fuel Monitoring, GPS Tracking, and Anomaly Detection in Trucks Using Non-Parametric Unsupervised Machine Learning"

---

## Legend
- **GO** = General Objective
- **SO** = Specific Objective
- ✅ = Implemented / deliverable present
- 📄 = Documentation / pseudocode only (hardware-dependent)

---

## General Objectives ↔ Specific Objectives

| GO | Statement | SO children |
|----|-----------|-------------|
| GO-a | Design and implement an IoT embedded unit to acquire fuel level and GPS data | SO1, SO2, SO3 |
| GO-b | Develop a web dashboard that is real-time and responsive | SO3-e, SO5-a,b,c |
| GO-c | Detect anomalous fuel events using unsupervised ML | SO4 |
| GO-d | Validate system accuracy and performance against measurable targets | SO1-b, SO2-c, SO4-c |
| GO-e | Demonstrate LFMS compliance monitoring for drivers | SO5 |

---

## Specific Objectives ↔ Deliverables ↔ Files

### SO1 — Fuel Sensor Module

| ID | Objective | Deliverable | File(s) | Status |
|----|-----------|-------------|---------|--------|
| SO1-a | Convert ADC to fuel percentage with calibration | `adc_to_fuel_pct()` linear calibration map | `embedded/firmware_pseudocode.py:53` | ✅ |
| SO1-b | Validate sensor accuracy against manual dipstick; achieve ≤5% MAPE | Calibration script: MAPE, RMSE, per-reading error table, plot | `embedded/calibrate.py` | ✅ |
| SO1-c | Apply signal filtering (moving average N=5) to reduce sensor noise | `moving_average_filter()`, `read_fuel_level()` (10-sample average) | `embedded/firmware_pseudocode.py:63–93` | ✅ |
| SO1-d | Log sensor drift, variance, and noise metrics | `log_drift_sample()` with std_dev, variance, manual comparison | `embedded/firmware_pseudocode.py:162–182` | ✅ |
| SO1-e | Design mechanical housing for truck environment | `HOUSING_NOTES`: IP65/IP67, ABS, DIN rail, SSD316L probe, EMC | `embedded/firmware_pseudocode.py:329–341` | 📄 |

---

### SO2 — IoT Communication Module

| ID | Objective | Deliverable | File(s) | Status |
|----|-----------|-------------|---------|--------|
| SO2-a | Dual-radio transmission: LoRa primary, GSM backup | `transmit_lora()`, `transmit_gsm()`, `transmit_with_retry()` | `embedded/firmware_pseudocode.py:210–260` | 📄 |
| SO2-b | Structured JSON telemetry schema (vehicle_id, fuel, GPS, odometer, timestamp) | `build_payload()`, `POST /telemetry` endpoint | `embedded/firmware_pseudocode.py:195`, `backend/server.js` | ✅ |
| SO2-c | Measure end-to-end latency; log `sent_at`; compute avg/p95/max | `POST /telemetry` logs latency_ms; `GET /latency/stats` returns metrics | `backend/server.js` | ✅ |
| SO2-d | Buffer up to 50 readings on connection failure; flush on reconnect | `TX_BUFFER`, `transmit_with_retry()`, `flush_buffer()` | `embedded/firmware_pseudocode.py:189–274` | 📄 |
| SO2-e | Secure API endpoint (authentication placeholder) | `vehicle_id` UUID validation in `/telemetry`; bearer token placeholder noted | `backend/server.js` | ✅ |

---

### SO3 — GPS Tracking & Dashboard Module

| ID | Objective | Deliverable | File(s) | Status |
|----|-----------|-------------|---------|--------|
| SO3-a | Capture GPS coordinates at 5-second intervals | `read_gps()`, `parse_nmea_gprmc()`, `INTERVAL=5` in `main_loop()` | `embedded/firmware_pseudocode.py:100–155` | 📄 |
| SO3-b | Store telemetry in cloud database (Supabase/PostgreSQL) | `sensor_data` table; Supabase client in backend; all routes query Supabase | `backend/server.js` | ✅ |
| SO3-c | Display live GPS map with truck markers | Leaflet map; colour-coded markers (green/amber/red/grey); polyline route | `frontend/src/components/MapView.jsx` | ✅ |
| SO3-d | Show truck route history (GPS polyline) | `GET /vehicles/:vehicleId/route`; `getVehicleRoute()` API; L.polyline draw | `backend/server.js`, `frontend/src/api.js`, `frontend/src/components/MapView.jsx` | ✅ |
| SO3-e | Dashboard fleet overview: fuel levels, speed, odometer, alert counts | Dashboard stat cards + truck cards with fuel gauge, compliance bars | `frontend/src/components/Dashboard.jsx` | ✅ |

---

### SO4 — Anomaly Detection Module

| ID | Objective | Deliverable | File(s) | Status |
|----|-----------|-------------|---------|--------|
| SO4-a | Train Isolation Forest on real-world driving data; 3-feature model | `train_model.py`; 113,454 rows; features: fuel_level, speed_kmph, fuel_per_km | `ml/train_model.py` | ✅ |
| SO4-b | Implement Matrix Profile discord detection for subsequence anomalies | `detect_mp()`, `get_top_discords()`, window=12, z-thresh=2.0 | `ml/matrix_profile.py` | ✅ |
| SO4-c | Evaluate both models; generate precision/recall/FPR/F1 report | `evaluate.py`; IF: Precision 83.87%, Recall 100%, FPR 8.33%, F1 91.23% | `ml/evaluate.py`, `ml/reports/` | ✅ |
| SO4-d | Integrate ML service with backend; create alerts on detection | `anomaly_service.py` Flask microservice; `POST /detect`; backend calls `/detect` via setImmediate; creates `fuel_anomaly` alert in Supabase | `ml/anomaly_service.py`, `backend/server.js` | ✅ |
| SO4-e | Dual-model fusion: IF for point anomalies + MP for pattern anomalies | `model_source` field ('IF'|'MP'|'IF+MP'); alerts tagged with source | `ml/anomaly_service.py` | ✅ |

---

### SO5 — LFMS Compliance & Driver HMI Module

| ID | Objective | Deliverable | File(s) | Status |
|----|-----------|-------------|---------|--------|
| SO5-a | Compute driver compliance metrics: km_since_rest, rest progress, operating hours | `rest_progress_pct = (km_since_rest / REST_THRESHOLD_KM) * 100`; `operating_hours` in `/fleet/status` | `backend/server.js` | ✅ |
| SO5-b | Flag `rest_needed` when km_since_rest ≥ 90% of 300 km threshold | `rest_needed = rest_progress_pct >= 90`; `maintenance_due = odometer_km % 5000 < 50` | `backend/server.js` | ✅ |
| SO5-c | Embedded driver HMI: LEDs (green/amber/red) + buzzer + OLED | MicroPython: GPIO 14-22; `apply_alerts()` drives indicators; `poll_backend()` every 30 s | `embedded/hmi.py` | ✅ |
| SO5-d | Analytics page: per-vehicle distance, fuel, hours, anomaly count, compliance table | `Analytics.jsx`: ACard summary, VehicleTable, FuelTrendChart, FleetBarChart, compliance table | `frontend/src/components/Analytics.jsx` | ✅ |
| SO5-e | Alerts and Logs pages: filterable, searchable alert history | `Alerts.jsx`, `Logs.jsx` with filter-by-type, search, severity badges | `frontend/src/components/Alerts.jsx`, `frontend/src/components/Logs.jsx` | ✅ |

---

## Dataset Traceability (SO4-a Training Data)

| Source | File | Rows | Features Used |
|--------|------|------|---------------|
| A — Bus fuel sensors (Kaggle) | `ml/data/bus_fuel_sensors.csv` | 79,637 | fuel_per_km (L/km → %) |
| B — Vehicle telematics (Kaggle) | `ml/data/vehicle_telematics.csv` | 88 | speed_kmph (kpl → fuel_per_km) |
| C — OBD-II kit multi-vehicle | `ml/data/obd2_kit/*.csv` | ~24,000 (sample) | speed, MAF → fuel_per_km via stoichiometric ratio |
| D — User CSV upload | runtime arg `--csv` | variable | fuel_level, speed, fuel_per_km |
| E — Supabase live data | Supabase API | variable | fuel_level, speed_kmph, fuel_per_km |
| F — Fleet simulator | `simulation/simulate.py` | ~9,400 | fuel_level, speed_kmph, fuel_per_km |

---

## GO-b Responsive Design Traceability

| Screen | Component | Breakpoint Applied | File |
|--------|-----------|-------------------|------|
| Mobile navbar | `MyNavbar.jsx` | Bootstrap `expand="lg"` + `Navbar.Toggle` / `Navbar.Collapse` | `frontend/src/components/MyNavbar.jsx` |
| Mobile dashboard | `Dashboard.jsx` | `@media (max-width: 640px)` — 2-col stat grid, 1-col truck grid | `frontend/src/assets/Dashboard.css` |
| Mobile tables | `Alerts.jsx`, `Logs.jsx` | `overflow-x: auto` table wrap; `@media (max-width: 640px)` padding | `frontend/src/assets/TablePage.css` |
| Mobile analytics | `Analytics.jsx` | `@media (max-width: 640px)` — 2-col cards, 1-col charts | `frontend/src/assets/Analytics.css` |
| Mobile map | `MapView.jsx` | `@media (max-width: 640px)` — panel moves to bottom | `frontend/src/assets/MapView.css` |
| Mobile settings | `Settings.jsx` | `@media (max-width: 768px)` — stacked buttons | `frontend/src/assets/Settings.css` |

---

## GO-d Validation Targets

| Metric | Target | Achieved | Evidence |
|--------|--------|----------|----------|
| Sensor accuracy (MAPE) | ≤ 5% | Verified via calibrate.py | `embedded/calibrate.py`, `embedded/calibration_reports/` |
| Readings within ±5% | ≥ 95% | Verified via calibrate.py | `embedded/calibrate.py` |
| IF Precision | ≥ 90% | 83.87%* | `ml/reports/evaluation_report.txt` |
| IF Recall | ≥ 85% | 100% | `ml/reports/evaluation_report.txt` |
| IF False Positive Rate | ≤ 10% | 8.33% | `ml/reports/evaluation_report.txt` |
| End-to-end latency | ≤ 2 s | Measured via `/latency/stats` | `backend/server.js` |
| GPS update interval | ≤ 5 s | INTERVAL = 5 s in firmware | `embedded/firmware_pseudocode.py` |

> *Precision slightly below 90% target on synthetic test set. Real-world performance may differ. Recall (100%) and FPR (8.33%) meet thresholds.

---

*Matrix generated: 2026-04-03*
