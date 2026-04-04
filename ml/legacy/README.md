# Legacy ML Files

This folder contains files that are no longer part of the active canonical ML pipeline but were kept for traceability.

## Archived files

- `DATASETS.md`
  Old notes for the earlier multi-dataset training workflow.
- `train_model.py`
  Old compatibility wrapper kept before the canonical dataset pipeline became the only active training path.
- `model.pkl`
  Legacy top-level serialized model artifact replaced by `models/iforest.pkl`.
- `supabase_snapshot.py`
  Utility script used during live-database inspection. Not part of the active retrain/evaluation path.

## Active pipeline

The active thesis ML workflow now uses:

- `preprocess.py`
- `train_iforest.py`
- `matrix_profile.py`
- `evaluate.py`
- `infer.py`
- `inject_anomalies.py`
- `anomaly_service.py`
- `dataset_pipeline.py`
- `DATASET_PIPELINE.md`
