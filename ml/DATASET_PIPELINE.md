# Dataset Pipeline

Run:

```bash
python dataset_pipeline.py
```

Outputs are written to `ml/outputs/datasets/`.

## Core files

- `cleaned_telemetry.csv`
  The main clean trip pool used going forward. It combines:
  project-native canonical telemetry plus mapped clean public GeoLife route trips with clearly derived fuel fields.
- `trip_sessions.csv`
  Trip/session records derived from grouped telemetry.
- `trucks_seed.csv`
  Truck seed rows aligned with the project truck roster plus deterministic public demo trucks used by the added GeoLife trips.
- `drivers_seed.csv`
  Driver seed rows aligned with the SQL schema fields used by trip/session linkage, including deterministic demo drivers for the public route trips.
- `evaluation_dataset.csv`
  Realistic evaluation mix for ML validation. It includes:
  project-native controlled anomaly-injected trips plus clean public GeoLife route trips that widen normal trip diversity.
- `evaluation_dataset_summary.json`
  Composition summary for the evaluation dataset, including provenance counts and public-source usage notes.
- `trip_pool_summary.json`
  High-level count summary for the combined clean trip pool and the evaluation trip pool.
- `public_geolife_quality_summary.json`
  Quality and selection summary for the public GeoLife trip subset, including user caps, gap constraints, duration-band coverage, and mode counts.
- `alerts_seed.csv`
  Alert rows derived from the controlled anomaly injections.
- `public_geolife_routes.csv`
  Canonicalized public route telemetry built from GeoLife trajectories. GPS geometry and timestamps come from the public dataset; truck identifiers and fuel fields are derived for thesis simulation.

## Public reference files

- `public_primary_telematics.csv`
  Canonicalized rows from `vehicle_telematics.csv`. Fuel fields are derived from `kpl` using a nominal 60 L tank. GPS is unavailable in the source and remains null.
- `aux_fuel_reference.csv`
  Canonicalized heavy-vehicle fuel reference rows from `bus_fuel_sensors.csv`. Speed and fuel-level trajectories are controlled estimates based on the source `fuel_per_km` and stop-time fields using a nominal 150 L tank.
- `geolife_trajectories_1_3.zip`
  Official Microsoft Research GeoLife archive used as the primary public route-geometry source. Only labeled `bus`, `car`, and `taxi` trajectories that pass trip-quality checks are mapped into the canonical schema.

GeoLife quality rules in the active pipeline:

- median sample gap <= 30 seconds
- 95th percentile sample gap <= 120 seconds
- ratio of gaps above 30 seconds <= 0.30
- deterministic per-user cap to avoid one public user dominating the trip pool
- duration-band balancing across short, medium, and long trips

The public files serve different roles:

- `geolife_trajectories_1_3.zip`
  Supplies the real ordered GPS paths and timestamps that make route replay and dashboard trip diversity more realistic.
- `vehicle_telematics.csv`
  Supplies auxiliary startup/noise reference behavior.
- `bus_fuel_sensors.csv`
  Supplies auxiliary heavy-vehicle fuel-consumption ranges for the derived fuel traces on public routes.

Only GeoLife route geometry is inserted into the final clean/evaluation pools.
The fuel/driver/truck fields attached to those public routes remain explicitly derived.

## Provenance rules

- `record_origin`
  Distinguishes project-native simulation telemetry from public route-derived telemetry and auxiliary public references.
- `trip_id_source`
  Shows whether the trip ID came from the source logs or was deterministically derived from file and time gaps.
- `driver_id_source`
  Shows whether driver IDs come from the project roster or from deterministic public-route demo assignments.
- `label_source`
  `clean` means no injected anomaly labels.
  `controlled_injection` means the row belongs to the evaluation dataset built for ML validation.
  `clean_public_route` means the row comes from a mapped GeoLife route with derived truck-style fields.
- `is_injected`
  `True` means the row is part of a modified trajectory in the evaluation dataset, even if the anomaly peak occurs only on some rows.
- `augmentation_type`
  `none` for the current public-route expansion pass.
- `public_reference_source`
  Identifies which public reference datasets informed a public-route derivation or augmentation profile.
