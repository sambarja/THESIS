# Public Datasets for SO4 Anomaly Detection Training

Drop any downloaded CSV into `ml/data/` and run `python train_model.py`.
The script auto-detects it. No code changes needed.

---

## Recommended Datasets (best to worst for this thesis)

### 1. NREL Fleet DNA — Best choice
**Why:** Real commercial truck fleet data (GPS, speed, fuel usage). Closest to SGSA fleet.
**Search:** "NREL Fleet DNA Commercial Fleet" or go to nrel.gov → Transportation → Fleet DNA
**Download:** Select "Vocational Trucks" dataset → download CSV
**Key columns the loader expects:** `vehicle_id`, `local_time`, `speed_mph`, `fuel_gallons_per_hour`

---

### 2. Kaggle — Fleet Vehicle Log
**Why:** Has odometer, fuel fills, dates per vehicle. Good for consumption patterns.
**Search on kaggle.com:** "fleet vehicle fuel log" by pgabriel19
**Key columns:** `Date`, `Vehicle`, `Mileage`, `Fuel_Quantity`

---

### 3. Kaggle — OBD-II Vehicle Data
**Why:** Real car sensor readings including speed and fuel level at intervals.
**Search on kaggle.com:** "obd2 vehicle speed fuel level"
**Key columns:** `SPEED`, `FUEL_LEVEL`, `DISTANCE` (or similar)

---

### 4. EPA Fuel Economy Dataset
**Why:** Large dataset of fuel consumption rates by vehicle class. Good for calibrating normal consumption range.
**Search:** "EPA fuel economy data download" → fueleconomy.gov → Download Data
**Key columns:** `VClass`, `comb08`, `highway08`, `city08`
**Note:** This is per-model averages, not time-series — useful to supplement other data.

---

### 5. Kaggle — GPS Tracking Dataset
**Why:** Time-series GPS + speed data from vehicles. Combine with consumption rates.
**Search on kaggle.com:** "vehicle gps tracking dataset"

---

## How to use multiple datasets at once

```bash
# Auto-load the first CSV found in ml/data/
python train_model.py

# Specify a specific file
python train_model.py --csv data/nrel_fleet.csv
```

If you have multiple CSVs, merge them first:
```python
import pandas as pd
import glob

files = glob.glob('data/*.csv')
combined = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
combined.to_csv('data/combined.csv', index=False)
```
Then run: `python train_model.py --csv data/combined.csv`

---

## Column name auto-detection

The loader recognises these column names automatically (case-insensitive):

| Internal field   | Recognised CSV column names |
|------------------|-----------------------------|
| `fuel_level`     | fuel_level, fuel_pct, fuel_%, fuel_quantity, fuel_gallons, fuel_liters, FUEL_LEVEL |
| `speed_kmph`     | speed_kmph, speed_kph, speed, speed_mph, SPEED, avg_speed |
| `odometer_km`    | odometer_km, odometer, mileage, distance_km, distance, DISTANCE, trip_distance |
| `vehicle_id`     | vehicle_id, vehicle, truck_id, unit, car_id |
| `timestamp`      | created_at, timestamp, local_time, Date, datetime, time |

mph and miles are automatically converted to km/h and km.

---

## Without any external data

The built-in fleet simulator (10 trucks × 30 days) runs automatically as fallback.
It models realistic diesel truck consumption and injects known anomalies for validation.
This is good enough for a working thesis demo.
