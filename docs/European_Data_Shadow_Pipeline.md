# European Data Shadow Pipeline

This implementation adds a shadow-only European avalanche data layer. It is intentionally not wired into public production scoring. The current public scorer remains the existing RF baseline until European shadow metrics beat that baseline and promotion gates pass.

## What Is Implemented

| Layer | File | Purpose |
|---|---|---|
| Source registry | `backend/common/european_shadow_sources.py` | Catalogues Swiss SPOT6, French EPA/CLPA, Norwegian SAR, AvalCD, SLF, and EAWS sources with region, data lane, record-count, license, attribution, and risk metadata. |
| License gates | `backend/common/european_shadow_sources.py` | Blocks benchmark/shadow-training use until a `license_review_id` is attached for sources requiring review. |
| Production guard | `backend/common/european_shadow_sources.py` | Blocks `production_scoring` for every European source, even after license review. |
| Staged records | `normalize_staged_european_record` | Normalizes downloaded or externally staged records into a manifest-safe internal shape without database writes. |
| SAR reuse | `build_sar_training_manifest_from_staged_records` | Converts reviewed AvalCD/Norway SAR staged records into the existing `sar_training_manifest_v1` contract. |
| Updated recommendation ratings | `dataset_family_assessments` | Stores the 1-5 enhancement values, best-use guidance, cautions, implementation status, and remaining work for the seven European dataset families. |
| Manifest CLI | `backend/scripts/build_european_shadow_manifest.py` | Emits a reviewable JSON manifest and usage-gate report for all or selected European sources. |
| Real-data staging | `backend/common/european_shadow_ingest.py`, `backend/scripts/stage_european_shadow_data.py` | Stages reviewed local CSV, JSON, JSONL, GeoJSON, zip, and shapefile exports into checksum manifests plus `staged_records.jsonl`. |
| Shadow benchmarks | `backend/common/european_shadow_benchmarks.py`, `backend/scripts/run_european_shadow_benchmarks.py` | Builds source-quality, bias-audit, readiness, calibration, SAR-compatibility, and promotion-blocker reports without changing public scoring. |
| SAR prediction artifacts | `european_sar_prediction_artifact_v1`, `--sar-prediction-artifact` | Allows AvalCD/SAR reports to compute real precision, recall, F1, IoU, false-positive rate, and confusion counts when validation predictions are attached. |
| AvalCD governed split | `backend/scripts/build_avalcd_shadow_split_manifest.py` | Builds the deterministic train5/val2 AvalCD shadow split and the matching remote `train_sar_unet_request.json`. |
| Remote-safe SAR training | `backend/sar_unet_training.py`, `backend/scripts/trigger_and_poll_sar_training.py`, `backend/scripts/run_modal_sar_training_direct.py` | Supports scratch materialization outside persistent artifacts and emits validation prediction artifacts for benchmark consumption. Direct Modal invocation is available when the HTTP worker bearer-token path is not aligned. |
| SAR checkpoint evaluation | `backend/scripts/evaluate_sar_checkpoint.py`, `backend/scripts/run_modal_sar_checkpoint_evaluation_direct.py` | Re-evaluates an existing SAR checkpoint against dense threshold/post-processing grids without another training run, locally or through the direct Modal.com function path. Use `evaluation_mode=scene_blended` for AvalCD promotion or SnowSlide prerequisites. |
| SAR validation error diagnostics | `sar_validation_error_diagnostics_v1` | Reports scene-level false-negative/false-positive burden and largest missed components before any new training spend. |
| SnowSlide materialization guard | `backend/scripts/run_modal_sar_prediction_materialization_direct.py` | Refuses held-out prediction-mask uploads until AvalCD precision and recall gates pass. |
| SnowSlide research-grade acceptance | `backend/common/sar_acceptance_policy.py`, `backend/scripts/build_snowslide_acceptance_report.py` | Classifies SnowSlide dry-run evidence against research-grade precision, recall, F1, false-positive, provenance, scene-coverage, and no-promotion gates. |
| SnowSlide threshold sweep | `backend/scripts/run_snowslide_threshold_sweep.py` | Runs evaluation-only threshold/component-area screening against existing held-out masks before any new GPU training. Passing sweep candidates still require AvalCD recheck and fresh final hold-out approval. |
| SAR promotion acceptance guard | `backend/sar_release_promote.py`, `backend/scripts/run_authoritative_release_gate.py` | Prevents SAR promotion from `beats_baseline=true` alone; promotion now requires an attached accepted SnowSlide research-grade report. |
| Modal cost guard | `backend/scripts/modal_cost_guard.py` | Reasserts zero warm containers for GPU Modal functions so GPU is used only when a job is running. |

## Updated Recommendation Status

| Dataset family | Enhancement value /5 | Current implementation status | Still pending |
|---|---:|---|---|
| Norway 472k SAR detections | 5.0 | Local staging and activity-rate benchmark reporting implemented for CSV/JSON/GeoJSON exports. | Verify source package/license and attach reviewed real export before relying on counts. |
| Swiss SPOT6 24,778 outlines | 4.5 | Local polygon staging, archive checksums, fixed event dates, bbox extraction, and extreme-event split reporting implemented. | Download/checksum EnviDat exports only after license review; keep extreme-event split separate from normal-season validation. |
| French EPA/CLPA | 4.5 | EPA dated-event staging, CLPA path-prior staging, and observability-bias audit reporting implemented. | Verify avalanches.fr export terms and field schema before staging real exports. |
| Swiss weather/snowpack/danger ratings | 4.0 | Local API/export staging, feature refs, danger-rating records, and calibration-slice reporting implemented. | Forecast ratings remain benchmark/context labels, not observed avalanche occurrence truth. |
| AvalCD | 4.0 | Local scene/archive staging, corrected region keys, `sar_training_manifest_v1` emission, patch-level SAR metrics, scene-blended SAR checkpoint evaluation, gated SnowSlide dry-run execution, research-grade acceptance reporting, and promotion guard tightening implemented. | v3 with area-64 postprocessing passes the aggregate AvalCD scene-blended floor and beats the weak SnowSlide baseline, but fails the research-grade SnowSlide acceptance gate. The bounded v5 attempt was stopped for cost control after the Modal run stalled without a result artifact. |
| SLF accident datasets | 3.0 | Accident export staging, uncertainty/casualty metadata, and accident-only bias audit reporting implemented. | Accident frequency remains blocked from avalanche occurrence-frequency training. |
| EAWS/SLF bulletins | 2.5 | Bulletin/context staging and warning-semantics audit reporting implemented. | Bulletin text and danger scales remain context/calibration surfaces only. |

Overall enhancement average across the seven families is `3.93 / 5`, with five families at `4.0 / 5` or higher. The strongest value is validation and shadow-model qualification, not immediate public production scoring.

## Usage

Generate a full registry manifest:

```bash
python3 -m backend.scripts.build_european_shadow_manifest
```

Generate a reviewed subset manifest:

```bash
python3 -m backend.scripts.build_european_shadow_manifest \
  --source swiss_spot6_2018 \
  --source avalcd_zenodo_v1 \
  --license-review swiss_spot6_2018=license-review-spot6-2026-05-16 \
  --license-review avalcd_zenodo_v1=license-review-avalcd-2026-05-16 \
  --snapshot-id european-shadow-reviewed-v1 \
  --output backend/artifacts/european-shadow-reviewed-v1.json
```

Stage a reviewed local export:

```bash
python3 -m backend.scripts.stage_european_shadow_data \
  --source-key swiss_spot6_2018 \
  --raw-path /path/to/SPOT6_Avalanche_outlines_2018.zip \
  --license-review license-review-spot6-2026-05-16 \
  --snapshot-id european-shadow-reviewed-v1 \
  --output-root backend/artifacts/european-shadow-staging
```

The staging command writes:

| Artifact | Purpose |
|---|---|
| `checksum_manifest.json` | SHA256 for files or per-file checksums for directories, plus zip member size/CRC metadata. |
| `staged_records.jsonl` | Normalized `european_staged_record_v1` rows with source, region, role, attribution, asset refs, metadata, and `production_eligible=false`. |
| `staged_manifest.json` | Reviewable manifest pointing at the raw checksum and staged records. |
| `sar_training_manifest.json` | Optional `sar_training_manifest_v1` when SAR rows include non-zip-fragment `stack_ref` and `truth_mask_ref`. |

Run a shadow benchmark/readiness report:

```bash
python3 -m backend.scripts.run_european_shadow_benchmarks \
  --manifest backend/artifacts/european-shadow-staging/european-shadow-reviewed-v1/swiss_spot6_2018/staged_manifest.json \
  --output backend/artifacts/european-shadow-reviewed-v1/european_shadow_benchmark_report.json
```

Multiple `--manifest` arguments can be supplied to combine staged sources into one report.

Attach SAR prediction metrics when a detector run exists:

```bash
python3 -m backend.scripts.run_european_shadow_benchmarks \
  --manifest backend/artifacts/european-shadow-staging/european-shadow-real-avalcd-assembled-2026-05-16/avalcd_zenodo_v1/staged_manifest.json \
  --sar-prediction-artifact backend/artifacts/european-shadow-sar-training/avalcd-shadow-train5-val2-2026-05-16/sar_training_metrics.json \
  --snapshot-id european-shadow-real-avalcd-predictions-2026-05-16 \
  --output backend/artifacts/european-shadow-real-benchmarks/european-shadow-real-avalcd-predictions-2026-05-16/european_shadow_benchmark_report.json
```

The prediction artifact can be either `european_sar_prediction_artifact_v1` or the repo-native `sar_training_metrics.json` emitted by `train_sar_unet`. Patch-level training metrics are useful for diagnostics, but `scene_blended` metrics are required before SnowSlide materialization or promotion discussion. The benchmark report stays shadow-only: `production_scoring_allowed=false` and `decision=blocked_shadow_only`.

## Expected Local Export Shapes

| Source family | Accepted local shapes | Expected useful fields |
|---|---|---|
| SPOT6 outlines | GeoJSON, shapefile, zipped shapefile, JSON/JSONL | `id`, polygon geometry, optional `area_m2`; event dates are fixed by source key. |
| Norway SAR activity | CSV, JSON, JSONL, GeoJSON | `detection_id`, `event_time`, `region_key`, `detection_probability`, `temporal_uncertainty_hours`, `false_positive_review_status`. |
| Norway SAR masks | JSON/JSONL/CSV scene manifests | `scene_id`, `region_key`, `stack_ref`, `truth_mask_ref`. |
| AvalCD | JSON scene manifests, raw Zenodo zip archives, or assembled AvalCD scene directories | Raw zips provide checksum/provenance and scene inventory; assembled scene directories with `stack_manifest.json` and `truth_mask.tif` emit `sar_training_manifest_v1`. |
| French EPA | CSV, JSON, JSONL, shapefile/GeoJSON | `event_id`, `date`, `site_id` or `path_id`, optional geometry. |
| French CLPA | Shapefile/GeoJSON/JSON | path-prior geometry and `path_id`; no dated occurrence label required. |
| SLF weather/snowpack | CSV, JSON, JSONL | `station_id`, `date` or `event_time`, weather/snowpack variables, optional `predicted_danger_level`. |
| SLF/EAWS bulletins | JSON, JSONL, CSV | `id`, `activeAt`, `region_key`, `danger_level`, danger problem/context fields. |
| SLF accidents | CSV, JSON, JSONL | `event_id`, `date`, `caught_count`, `dead_count` or `fatality_count`, `date_accuracy`, `location_accuracy_m`. |

## Real AvalCD Archive Flow

The Zenodo `AvalCD.zip` contains raw per-scene GeoTIFF members such as `preVV`, `preVH`, `postVV`, `postVH`, `GT.tif`, and `GT.gpkg`. Direct zip staging records checksum/provenance and scene inventory. Current v1 SAR model input intentionally uses the four core bi-temporal channels, pre/post VV and VH. Ancillary layers such as local incidence angle, slope, or DEM-derived covariates are a later experiment and are not part of the current qualification gate.

To emit repo-native SAR training manifests, first assemble the raw archive into the existing AvalCD patch layout:

```bash
python3 -m backend.scripts.assemble_seed_archive \
  --truth-zip backend/artifacts/european-real-exports/avalcd_zenodo_v1/AvalCD.zip \
  --sar-zip backend/artifacts/european-real-exports/avalcd_zenodo_v1/AvalCD.zip \
  --output-dir backend/artifacts/european-real-exports/avalcd_zenodo_v1/assembled
```

Then stage the assembled directory:

```bash
python3 -m backend.scripts.stage_european_shadow_data \
  --source-key avalcd_zenodo_v1 \
  --raw-path backend/artifacts/european-real-exports/avalcd_zenodo_v1/assembled \
  --license-review license-review-avalcd-zenodo-cc-by-nc-2026-05-16 \
  --snapshot-id european-shadow-real-avalcd-assembled-2026-05-16 \
  --output-root backend/artifacts/european-shadow-staging \
  --sar-split val
```

Materialize the emitted SAR manifest into the existing repo-native patch dataset:

```bash
python3 -c "import json; from pathlib import Path; from backend.common.sar_training_dataset import materialize_sar_training_dataset; sm=json.loads(Path('backend/artifacts/european-shadow-staging/european-shadow-real-avalcd-assembled-2026-05-16/avalcd_zenodo_v1/staged_manifest.json').read_text()); audit=materialize_sar_training_dataset(manifest_source=sm['sar_training_manifest_path'], output_root=Path('backend/artifacts/european-shadow-sar-materialized/avalcd-2026-05-16'), patch_size=128, stride=64); print(json.dumps(audit, indent=2, sort_keys=True))"
```

Current real-run checkpoint from the local AvalCD archive:

| Checkpoint | Result |
|---|---|
| Raw archive checksum | `AvalCD.zip` MD5 matched Zenodo: `f632099eaa2ff30101a2151e1ef1ddbb`. |
| Assembled scenes | 7 scenes across Italian Alps, Greenland/Nuuk, Tajikistan/Pamir, and Scandinavia/Norway. |
| SAR manifest scenes | 7 `sar_training_manifest_v1` scenes with stack and truth-mask refs. |
| Materialized patches | 11,627 total patches at `128` patch size and `64` stride: 6,218 train and 5,409 validation. |
| Positive pixel rate | Train `0.006607217626120738`; validation `0.004010672136427713`. |
| Production scoring | Still `false`; report decision remains `blocked_shadow_only`. |

## AvalCD SAR Prediction Metrics And Remote Training

AvalCD currently has real staged scenes and a repo-native SAR manifest. The next qualification layer is model-output evidence: attach prediction masks or a `train_sar_unet` metrics artifact so the benchmark can replace `pending_predictions` with computed SAR metrics.

The benchmark consumes this governed artifact shape:

| Field | Required meaning |
|---|---|
| `version` | `european_sar_prediction_artifact_v1`. |
| `source_key` | `avalcd_zenodo_v1` for this run. |
| `dataset_version` | The staged SAR dataset or training manifest version. |
| `model_family`, `model_version` | Detector family and immutable candidate version. |
| `evaluation_mode` | `scene_blended` is required before SnowSlide materialization or promotion discussion. Patch-level reports are benchmark evidence only. |
| `split`, `threshold` | Validation split and binary mask threshold used for metrics. |
| `license_review_id` | Reviewed license identifier for the dataset/model-output run. |
| `predictions[]` | Optional per-scene `prediction_mask_ref` plus `truth_mask_ref`; the benchmark computes TP/FP/FN/TN from masks. |
| `metrics`, `scene_breakdown`, `region_breakdown` | Optional precomputed metrics from `sar_training_metrics.json`; coverage must match validation scenes. |

Build the deterministic AvalCD train/validation split:

```bash
python3 -m backend.scripts.build_avalcd_shadow_split_manifest \
  --source-manifest backend/artifacts/european-shadow-staging/european-shadow-real-avalcd-assembled-2026-05-16/avalcd_zenodo_v1/sar_training_manifest.json \
  --local-assembled-root backend/artifacts/european-real-exports/avalcd_zenodo_v1/assembled \
  --runtime-assembled-root /artifacts/european-shadow-sar/avalcd-shadow-v1/assembled \
  --snapshot-id avalcd-shadow-train5-val2-2026-05-16 \
  --license-review license-review-avalcd-zenodo-cc-by-nc-2026-05-16 \
  --output backend/artifacts/european-shadow-sar-manifests/avalcd-shadow-train5-val2-2026-05-16/sar_training_manifest.json
```

The split policy is fixed:

| Split | Scenes |
|---|---|
| `train` | `livigno_20240403`, `livigno_20250129`, `nuuk_20160413`, `pish_20230221`, `tromso_20241220` |
| `val` | `livigno_20250318`, `nuuk_20210411` |
| `authoritative_test` | none for AvalCD; SnowSlide held-out remains separate |

Upload the assembled scenes and governed manifest to the Modal.com artifact volume before remote training:

```bash
modal volume put avalanche-artifacts \
  backend/artifacts/european-real-exports/avalcd_zenodo_v1/assembled \
  /european-shadow-sar/avalcd-shadow-v1/ \
  --force
```

```bash
modal volume put avalanche-artifacts \
  backend/artifacts/european-shadow-sar-manifests/avalcd-shadow-train5-val2-2026-05-16/sar_training_manifest.json \
  /european-shadow-sar/avalcd-shadow-v1/manifests/avalcd_shadow_train5_val2.json \
  --force
```

Trigger and poll the existing `/train-sar-unet` Modal worker:

```bash
python3 -m backend.scripts.trigger_and_poll_sar_training \
  --env-file .env \
  --request backend/artifacts/european-shadow-sar-manifests/avalcd-shadow-train5-val2-2026-05-16/train_sar_unet_request.json \
  --output backend/artifacts/european-shadow-sar-training/avalcd-shadow-train5-val2-2026-05-16/train_sar_unet_result.json
```

If the HTTP worker route returns `401` because the Modal UI secret and local operator token are not aligned, use the governed direct Modal function path instead. This path uses the selected Modal profile and does not require `MODAL_WORKER_TOKEN`:

```bash
MODAL_PROFILE=sanjabh1103_limit30 python3 -m backend.scripts.run_modal_sar_training_direct \
  --modal-profile sanjabh1103_limit30 \
  --request backend/artifacts/european-shadow-sar-manifests/avalcd-shadow-train5-val2-2026-05-16/train_sar_unet_request.json \
  --output backend/artifacts/european-shadow-sar-training/avalcd-shadow-train5-val2-2026-05-16/train_sar_unet_result_direct.json
```

The request defaults are intentionally remote-safe: SAR patches materialize under `/tmp/avalcd-shadow-train5-val2`, while the model checkpoint, metrics, and prediction artifact remain in the persistent artifact directory.

Build precision diagnostics before any additional training run:

```bash
python3 -m backend.scripts.build_sar_precision_diagnostics \
  --metrics backend/artifacts/european-shadow-sar-training/avalcd-shadow-train5-val2-2026-05-16/precision-v2/20260516T153431Z/sar_training_metrics.json \
  --output backend/artifacts/european-shadow-sar-training/avalcd-shadow-train5-val2-2026-05-16/precision-v2/20260516T153431Z/sar_precision_diagnostics.json \
  --precision-floor 0.60 \
  --recall-floor 0.50
```

Historical v2 diagnostics showed `precision_floor_met=false`, `max_precision=0.3783384251502907`, weakest precision scene `livigno_20250318`, and largest false-positive volume scene `nuuk_20210411`. That evidence justified a bounded v3 precision run, not an open-ended sweep.

Evaluate an existing checkpoint without another training run:

```bash
python3 -m backend.scripts.evaluate_sar_checkpoint \
  --scene-blended \
  --training-manifest backend/artifacts/european-shadow-sar-manifests/avalcd-shadow-train5-val2-2026-05-16/sar_training_manifest.json \
  --checkpoint-path backend/artifacts/european-shadow-sar-training/avalcd-shadow-train5-val2-2026-05-16/precision-v3/20260516T164730Z/sar_model.pt \
  --output-root backend/artifacts/european-shadow-sar-training/avalcd-shadow-train5-val2-2026-05-16/scene-blended-v3-local \
  --candidate-model-version avalcd_swinunet_tiny_diff_precision_shadow_20260516_v3_scene_blended \
  --license-review license-review-avalcd-zenodo-cc-by-nc-2026-05-16 \
  --precision-floor 0.60 \
  --postprocess-recall-floor 0.50 \
  --postprocess-min-component-area-px 32 \
  --threshold-grid 0.990,0.991,0.992,0.993,0.994,0.995,0.996,0.997 \
  --device cpu
```

Build false-negative diagnostics for the selected checkpoint threshold:

```bash
python3 -m backend.scripts.evaluate_sar_checkpoint \
  --diagnostics \
  --training-manifest backend/artifacts/european-shadow-sar-manifests/avalcd-shadow-train5-val2-2026-05-16/sar_training_manifest.json \
  --checkpoint-path backend/artifacts/european-shadow-sar-training/avalcd-shadow-train5-val2-2026-05-16/precision-v3/20260516T164730Z/sar_model.pt \
  --output-root backend/artifacts/european-shadow-sar-training/avalcd-shadow-train5-val2-2026-05-16/diagnostics-v3 \
  --materialized-dataset-root backend/artifacts/european-shadow-sar-materialized/diagnostics-v3 \
  --candidate-model-version avalcd_swinunet_tiny_diff_precision_shadow_20260516_v3 \
  --license-review license-review-avalcd-zenodo-cc-by-nc-2026-05-16 \
  --threshold 0.996999979019165 \
  --precision-floor 0.60 \
  --postprocess-recall-floor 0.50 \
  --postprocess-min-component-area-px 64 \
  --device cpu
```

For Modal.com execution, use the direct checkpoint-evaluation function rather than the HTTP bearer-token route:

```bash
python3 -m backend.scripts.run_modal_sar_checkpoint_evaluation_direct \
  --modal-profile sanjabh1103_limit30 \
  --request backend/artifacts/european-shadow-sar-training/avalcd-shadow-train5-val2-2026-05-16/scene-blended-v3/evaluate_sar_checkpoint_request.json \
  --output backend/artifacts/european-shadow-sar-training/avalcd-shadow-train5-val2-2026-05-16/scene-blended-v3/evaluate_sar_checkpoint_result.json
```

If the evaluation-only report still has `quality_gate.passed=false`, run at most one bounded recall-balanced fine-tune. Do not launch additional sweeps without a new checkpoint decision.

```json
{
  "training_manifest_path": "/artifacts/european-shadow-sar/avalcd-shadow-v1/manifests/avalcd_shadow_train5_val2.json",
  "source_key": "avalcd_zenodo_v1",
  "model_family": "swinunet_tiny_diff",
  "candidate_model_version": "avalcd_swinunet_tiny_diff_recall_balanced_shadow_20260517_v4",
  "initial_checkpoint_path": "/artifacts/20260516T164730Z/sar_model.pt",
  "patch_size": 128,
  "stride": 64,
  "epochs": 6,
  "patience": 3,
  "batch_size": 8,
  "learning_rate": 0.00002,
  "negative_ratio": 4,
  "loss": "focal_tversky",
  "focal_tversky_alpha": 0.45,
  "focal_tversky_beta": 0.55,
  "focal_tversky_gamma": 1.33,
  "f_beta": 0.75,
  "precision_floor": 0.60,
  "threshold_grid": [0.990, 0.991, 0.992, 0.993, 0.994, 0.995, 0.996, 0.997],
  "postprocess_min_component_area_px": 32,
  "postprocess_opening_size_px": 0,
  "postprocess_recall_floor": 0.50,
  "postprocess_apply_to_threshold_selection": true,
  "materialized_dataset_root": "/tmp/avalcd-shadow-train5-val2-v4",
  "license_review_id": "license-review-avalcd-zenodo-cc-by-nc-2026-05-16",
  "export_validation_prediction_artifact": true
}
```

Current scene-blended bounded-run outcome:

| Candidate | Evaluation mode | Threshold/postprocess | Precision | Recall | F1 | Gate result |
|---|---|---:|---:|---:|---:|---|
| v3 precision candidate | `scene_blended` | `0.996999979`, area `32` | `0.6099` | `0.4674` | `0.5292` | Failed: precision passed, recall below `0.50`. |
| v4 recall-balanced | `scene_blended` | `0.996999979`, area `32` | `0.5208` | `0.5509` | `0.5354` | Failed: recall passed, precision below `0.60`. |
| v3 area-64 evaluation-only | `scene_blended` | `0.991999984`, area `64` | `0.6073` | `0.5022` | `0.5498` | Passed aggregate AvalCD scene-blended precision and recall floors. |

The scene-blended European shadow benchmarks were rebuilt at:

| Candidate | Benchmark artifact |
|---|---|
| v3 | `backend/artifacts/european-shadow-real-benchmarks/european-shadow-real-avalcd-scene-blended-v3-2026-05-17/european_shadow_benchmark_report.json` |
| v4 | `backend/artifacts/european-shadow-real-benchmarks/european-shadow-real-avalcd-scene-blended-v4-2026-05-17/european_shadow_benchmark_report.json` |
| v3 area-64 | `backend/artifacts/european-shadow-real-benchmarks/european-shadow-real-avalcd-scene-blended-v3-area64-2026-05-17/european_shadow_benchmark_report.json` |

All reports remain `production_scoring_allowed=false` with `decision=blocked_shadow_only`. The v3 area-64 run is the first aggregate AvalCD scene-blended pass, so SnowSlide prediction masks were materialized scene-by-scene through the guarded direct Modal path. No new training sweep should be launched without a new checkpoint decision.

Build the historical blocked-state operator packet for the pre-area64 v3/v4 comparison:

```bash
python3 -m backend.scripts.build_avalcd_blocked_state_summary \
  --v3-benchmark-report backend/artifacts/european-shadow-real-benchmarks/european-shadow-real-avalcd-scene-blended-v3-2026-05-17/european_shadow_benchmark_report.json \
  --v4-benchmark-report backend/artifacts/european-shadow-real-benchmarks/european-shadow-real-avalcd-scene-blended-v4-2026-05-17/european_shadow_benchmark_report.json \
  --snow-materialization-result backend/artifacts/european-shadow-heldout/snowslide-materialization/scene-blended-v3-blocked/sar_segment_result.json \
  --modal-profile sanjabh1103_limit30 \
  --output-json backend/artifacts/european-shadow-qualification/avalcd-blocked-state-2026-05-17/qualification_summary.json \
  --output-markdown backend/artifacts/european-shadow-qualification/avalcd-blocked-state-2026-05-17/qualification_summary.md
```

That packet reports `final_decision=blocked_shadow_only`, `snow_slide_materialization_allowed=false`, `training_freeze=true`, no active Modal containers, and no validation violations for the earlier v3/v4 checkpoint. The current v3 area-64 checkpoint supersedes only the AvalCD prerequisite; production scoring remains blocked.

Reassert Modal.com zero-warm GPU settings before and after remote jobs:

```bash
python3 -m backend.scripts.modal_cost_guard \
  --modal-profile sanjabh1103_limit30
```

Run the SnowSlide/non-European held-out check only as a dry-run. The direct Modal path avoids the HTTP bearer-token route and never performs promotion:

```bash
python3 -m backend.scripts.run_modal_sar_release_evaluation_direct \
  --modal-profile sanjabh1103_limit30 \
  --request backend/artifacts/european-shadow-heldout/snowslide-dry-run/evaluate_release_request.json \
  --output backend/artifacts/european-shadow-heldout/snowslide-dry-run/evaluate_release_result.json
```

SnowSlide prediction masks may be materialized only after an AvalCD benchmark report has `evaluation_mode=scene_blended`, `quality_gate.passed=true`, `precision_floor_met=true`, and `recall_floor_met=true`:

```bash
python3 -m backend.scripts.run_modal_sar_prediction_materialization_direct \
  --modal-profile sanjabh1103_limit30 \
  --request backend/artifacts/european-shadow-heldout/snowslide-materialization/materialize_prediction_masks_request.json \
  --avalcd-benchmark-report backend/artifacts/european-shadow-real-benchmarks/european-shadow-real-avalcd-scene-blended-v3-area64-2026-05-17/european_shadow_benchmark_report.json \
  --output backend/artifacts/european-shadow-heldout/snowslide-materialization/materialize_prediction_masks_result.json
```

Current SnowSlide v3 area-64 dry-run checkpoint:

| Check | Result |
|---|---|
| Materialization mode | Scene-by-scene guarded direct Modal calls, compact response enabled. |
| Prediction masks | 7 / 7 held-out scenes uploaded under `sar-masks/heldout/snowslide/2026-04-29/.../predictions/avalcd_swinunet_tiny_diff_precision_shadow_20260516_v3_scene_blended_area64/prediction_mask.tif`. |
| Dry-run status | `ok`; no production promotion or event persistence. |
| SnowSlide metrics | Precision `0.5859`, recall `0.4327`, F1 `0.4978`, IoU `0.3314`, false-positive rate `0.001605`. |
| Baseline comparison | `beats_baseline=true`; baseline F1 floor used `0.05008`. |
| Decision | Keep `blocked_shadow_only`; do not promote because held-out precision/recall policy and non-European regression sign-off are still not complete. |

## SnowSlide Research-Grade Acceptance Gate

The baseline-beating SnowSlide dry-run is useful shadow evidence but is not research-grade acceptance. The current policy is `snowslide_research_grade_v1`:

| Gate | Required value |
|---|---|
| Precision | `>= 0.70` |
| Recall | `>= 0.50` |
| F1 | `>= 0.60` |
| False-positive rate | `<= 0.002` |
| Baseline comparison | `beats_baseline=true` |
| Run mode | `status=ok`, `dry_run=true`, no production promotion, no event persistence |
| Scene coverage | exactly the 7 expected SnowSlide held-out scene IDs |
| Provenance | AvalCD `scene_blended` gate passed with the same threshold/postprocess rule; materialization proof covers all 7 scenes |

Build the current acceptance packet:

```bash
python3 -m backend.scripts.build_snowslide_acceptance_report \
  --snow-report backend/artifacts/european-shadow-heldout/snowslide-dry-run/scene-blended-v3-area64/evaluate_release_result.json \
  --avalcd-benchmark-report backend/artifacts/european-shadow-real-benchmarks/european-shadow-real-avalcd-scene-blended-v3-area64-2026-05-17/european_shadow_benchmark_report.json \
  --materialization-result-dir backend/artifacts/european-shadow-heldout/snowslide-materialization/scene-blended-v3-area64/by-scene \
  --output-json backend/artifacts/european-shadow-qualification/snowslide-research-grade-v1-2026-05-18/acceptance_report.json \
  --output-markdown backend/artifacts/european-shadow-qualification/snowslide-research-grade-v1-2026-05-18/acceptance_report.md
```

Current output:

| Evidence | Result |
|---|---|
| Acceptance decision | `blocked_research_grade` |
| Failed floors | `precision_floor`, `recall_floor`, `f1_floor` |
| Passing guardrails | 7 / 7 scene coverage, no event persistence, false-positive rate under `0.002`, AvalCD scene-blended provenance attached |
| Production scoring | `false` |

Run evaluation-only recovery before any training spend:

```bash
python3 -m backend.scripts.run_snowslide_threshold_sweep \
  --env-file .env \
  --request backend/artifacts/european-shadow-heldout/snowslide-dry-run/scene-blended-v3-area64/evaluate_release_request.json \
  --output backend/artifacts/european-shadow-qualification/snowslide-research-grade-v1-2026-05-18/threshold_sweep_report.json
```

The 2026-05-18 sweep evaluated 48 threshold/component-area combinations. It found `passing_candidate_count=0`, `decision=blocked_research_grade`, and `bounded_candidate_warranted=true`. The best candidate still failed precision, recall, and F1 floors.

The only approved next GPU step was a single bounded v5 fine-tune:

```json
{
  "candidate_model_version": "avalcd_swinunet_tiny_diff_research_gate_shadow_20260518_v5",
  "initial_checkpoint_path": "/artifacts/20260516T164730Z/sar_model.pt",
  "epochs": 6,
  "patience": 3,
  "batch_size": 8,
  "learning_rate": 0.000015,
  "negative_ratio": 5,
  "loss": "focal_tversky",
  "focal_tversky_alpha": 0.40,
  "focal_tversky_beta": 0.60,
  "focal_tversky_gamma": 1.33,
  "f_beta": 1.0
}
```

That v5 direct Modal run did not produce a result artifact after an extended silent period. The active container was stopped to prevent unnecessary GPU spend, zero-warm autoscaler settings were reasserted, and `modal container list` was empty afterward. Treat v5 as `blocked_remote_training_stopped_for_cost_guard`, not as a model result.

Any future successful candidate must pass in this order:

| Step | Required checkpoint |
|---|---|
| 1 | AvalCD `scene_blended` precision `>= 0.60` and recall `>= 0.50`. |
| 2 | SnowSlide research-grade dry-run precision `>= 0.70`, recall `>= 0.50`, F1 `>= 0.60`, false-positive rate `<= 0.002`. |
| 3 | If SnowSlide influenced threshold/candidate choice, mark `requires_fresh_final_holdout=true`; no promotion discussion until a fresh final held-out set is approved and passes. |
| 4 | SAR promotion requires an attached acceptance report with `decision=accepted_research_grade`; `beats_baseline=true` alone is insufficient. |

## Promotion Rule

European data can support shadow validation, benchmark reconstruction, SAR candidate training, and calibration diagnostics. It must not change public production scoring until all of these are true:

| Gate | Required Evidence |
|---|---|
| License and attribution | Every included source has a recorded license review and required attribution. |
| RF comparator | Any recalibrated RF model has strictly better time-split Peirce Skill Score and no worse Brier score than the current RF baseline. |
| Local non-regression | Non-European/local validation slices do not materially degrade. |
| SAR qualification | SAR candidates pass AvalCD scene-blended gates and the SnowSlide research-grade acceptance report has `decision=accepted_research_grade`. |
| Final hold-out hygiene | If SnowSlide was used to select thresholds or tune a candidate, a fresh final held-out set must be created or explicitly approved before production discussion. |
| Product truth | Public UI and artifacts continue to show candidate/fallback state until promotion is explicit. |
