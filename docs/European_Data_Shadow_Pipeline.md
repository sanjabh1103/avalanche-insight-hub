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

## Updated Recommendation Status

| Dataset family | Enhancement value /5 | Current implementation status | Still pending |
|---|---:|---|---|
| Norway 472k SAR detections | 5.0 | Local staging and activity-rate benchmark reporting implemented for CSV/JSON/GeoJSON exports. | Verify source package/license and attach reviewed real export before relying on counts. |
| Swiss SPOT6 24,778 outlines | 4.5 | Local polygon staging, archive checksums, fixed event dates, bbox extraction, and extreme-event split reporting implemented. | Download/checksum EnviDat exports only after license review; keep extreme-event split separate from normal-season validation. |
| French EPA/CLPA | 4.5 | EPA dated-event staging, CLPA path-prior staging, and observability-bias audit reporting implemented. | Verify avalanches.fr export terms and field schema before staging real exports. |
| Swiss weather/snowpack/danger ratings | 4.0 | Local API/export staging, feature refs, danger-rating records, and calibration-slice reporting implemented. | Forecast ratings remain benchmark/context labels, not observed avalanche occurrence truth. |
| AvalCD | 4.0 | Local scene/archive staging, corrected region keys, and `sar_training_manifest_v1` emission implemented when stack/mask refs are available. | Verify Zenodo license and use real storage refs before running detector metrics. |
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

## Expected Local Export Shapes

| Source family | Accepted local shapes | Expected useful fields |
|---|---|---|
| SPOT6 outlines | GeoJSON, shapefile, zipped shapefile, JSON/JSONL | `id`, polygon geometry, optional `area_m2`; event dates are fixed by source key. |
| Norway SAR activity | CSV, JSON, JSONL, GeoJSON | `detection_id`, `event_time`, `region_key`, `detection_probability`, `temporal_uncertainty_hours`, `false_positive_review_status`. |
| Norway SAR masks | JSON/JSONL/CSV scene manifests | `scene_id`, `region_key`, `stack_ref`, `truth_mask_ref`. |
| AvalCD | JSON scene manifests or zip archives | `scene_id`, `region_key`, `stack_ref`, `truth_mask_ref`, optional polygon/GeoPackage refs. |
| French EPA | CSV, JSON, JSONL, shapefile/GeoJSON | `event_id`, `date`, `site_id` or `path_id`, optional geometry. |
| French CLPA | Shapefile/GeoJSON/JSON | path-prior geometry and `path_id`; no dated occurrence label required. |
| SLF weather/snowpack | CSV, JSON, JSONL | `station_id`, `date` or `event_time`, weather/snowpack variables, optional `predicted_danger_level`. |
| SLF/EAWS bulletins | JSON, JSONL, CSV | `id`, `activeAt`, `region_key`, `danger_level`, danger problem/context fields. |
| SLF accidents | CSV, JSON, JSONL | `event_id`, `date`, `caught_count`, `dead_count` or `fatality_count`, `date_accuracy`, `location_accuracy_m`. |

## Promotion Rule

European data can support shadow validation, benchmark reconstruction, SAR candidate training, and calibration diagnostics. It must not change public production scoring until all of these are true:

| Gate | Required Evidence |
|---|---|
| License and attribution | Every included source has a recorded license review and required attribution. |
| RF comparator | Any recalibrated RF model has strictly better time-split Peirce Skill Score and no worse Brier score than the current RF baseline. |
| Local non-regression | Non-European/local validation slices do not materially degrade. |
| SAR qualification | SAR candidates pass held-out SAR gates and current release-gate policies. |
| Product truth | Public UI and artifacts continue to show candidate/fallback state until promotion is explicit. |
