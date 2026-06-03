# Swiss RAvaFcast Reproduction Lane

Status: Stage-1 initial reproduction signal implemented with feature/parity
audit; Stage-3 station-row baseline implemented; Stage-2 GPxyz blocked pending
station coordinates

## Purpose

This lane reproduces the Swiss RAvaFcast / EnviDat danger-level workflow as
research-only evidence. It exists to understand the client-supplied Swiss
reference pipeline before any Himalayan operational adaptation is attempted.

## Scope

| Area | Decision |
|---|---|
| Data | EnviDat weather, snowpack, and danger-rating CSVs for Swiss reproduction. |
| Model | Separate `rf4_danger_v0` reproduction model, not the production `surrogate_rf_v1`. |
| Pipeline | Stage 1 RF danger classifier, Stage 2 GP interpolation, Stage 3 elevation-band aggregation. |
| Outputs | Local JSON/Markdown artifacts under `backend/artifacts/reproduction/swiss_ravafcast/`. |
| Usage boundary | `research_only`. |

## Non-Goals

- No production scoring.
- No `model_status` mutation.
- No changes to `backend/daily_inference.py`.
- No changes to `backend/train_model.py`.
- No Supabase migration.
- No public route change.
- No Himalayan operational claim from Swiss-trained artifacts.

## Current Implementation Checkpoint

The current checkpoint adds:

- isolated package: `backend/reproduction/swiss_ravafcast/`
- checksum-aware data manifest utilities
- EnviDat RF1/RF2 downloader with sha256 recording
- CSV schema validator for the real EnviDat column names
  (`dangerLevel`, `datum`, `station_code`, `elevation_station`, weak-layer
  profile features)
- Stage-1 `rf4_danger_v0` training scaffold with winter-season grouped split
  and paper-aligned accuracy / macro-F1 / per-class-F1 metrics
- RF4 feature-set parity audit scaffolding with leakage-column refusal
- RF4 probability calibration reporting from the held-out calibration season
- Stage-2 GPxyz readiness audit and synthetic-coordinate interpolation module
- station metadata readiness gate for reviewed lat/lon joins
- station metadata worksheet generator for the 129 RF2 station ids
- Stage-3 `elev-simple` warning-region/elevation-band station-row aggregation
  baseline
- full aggregation readiness guard that refuses RAvaFcast parity claims until
  GP grid and official warning-region polygons exist
- gitignore protection for local Swiss data caches

## Real Data Checkpoint

| Artifact | Current Result | Boundary |
|---|---|---|
| `data_validation_report.json` | RF1: `292837` rows; RF2: `29296` rows; both Stage-1 valid | Research-only, no production scoring |
| `rf4_result.json` | Calibrated accuracy `0.8937`; macro-F1 `0.7508`; class-4 F1 `0.3636`; uncalibrated accuracy `0.9033` | `initial_reproduction_signal_pending_parity_audit`; not paper-parity evidence yet |
| `rf4_feature_parity_audit.json` | `auto_numeric_current` accuracy `0.8924`; `paper_candidate_whitelist` accuracy `0.8145`; `leakage_guarded` accuracy `0.8924` | Feature/parity audit complete; still not RAvaFcast paper-parity or Himalayan evidence |
| `gpxyz_readiness_report.json` | `blocked_station_coordinates_required`; station count `129`; missing `latitude` and `longitude` | Stage-2 cannot honestly run on the downloaded CSVs alone |
| `elev_simple_aggregation_result.json` | Station-row baseline accuracy `0.8085`; macro-F1 `0.7848` | Station-row baseline only; not a full GP-grid / warning-polygon RAvaFcast reproduction |
| `reproduction_summary.json` | Consolidates phases, headline metrics, blockers, and claim gates | `production_scoring_allowed=false`; no operational detection claim |

## Reproduction Gate

A Swiss reproduction artifact is acceptable for client discussion only if it:

1. carries `usage_boundary=research_only`;
2. has `production_scoring_allowed=false`;
3. records EnviDat source URLs and checksums;
4. validates both RF1 and RF2 data resources;
5. reports paper-comparable metrics separately from production metrics.

## Next Implementation Phases

| Phase | Target | Output |
|---:|---|---|
| 1 | Data acquisition | Complete: reviewed RF1/RF2 CSV manifest with sha256 checksums. |
| 2 | Stage-1 RF4 | Initial signal, feature/parity audit, and calibration report complete; paper-parity language still blocked pending station/GP/aggregation parity review. |
| 3 | Stage-2 GPxyz | Module complete with exact-GP cap and metadata gate; real-data run blocked until station lat/lon metadata is supplied. |
| 4 | Stage-3 aggregation | Station-row baseline complete; full RAvaFcast parity still needs GP grid and official warning-region polygons. |
| 5 | Client mapping | Updated mapping must request station coordinates, region polygons, and local snowpack/label equivalents. |
| 6 | Customer wishlist delta | Remote-sensing detection maps and landslide scope are documented as future shadow-gated product work. |
| 7 | Claim gate | Full operational avalanche/landslide detection remains blocked pending separate validation datasets and release gates. |

## Immediate Data Gap For Full RAvaFcast Parity

The downloaded EnviDat RF1/RF2 CSVs contain station ids, warning-region ids, and
station elevation, but they do not contain station latitude/longitude. GPxyz
interpolation therefore cannot be run honestly from these two CSVs alone. The
next data request is a station metadata table with:

| Field | Required For |
|---|---|
| `station_code` | Join to RF1/RF2 rows |
| `latitude` | GPxyz spatial coordinate |
| `longitude` | GPxyz spatial coordinate |
| `elevation_m` | GPxyz vertical coordinate and elevation-band aggregation |
| warning-region polygon id | Warning-region aggregation and map display |

Generate the station-coordinate worksheet for partner review with:

```bash
python3 -m backend.reproduction.swiss_ravafcast.cli write-station-metadata-template \
  --manifest backend/data/swiss_envidat/swiss_ravafcast_data_manifest.json \
  --output backend/artifacts/reproduction/swiss_ravafcast/station_metadata_template.csv
```

The generated worksheet deliberately leaves `latitude` and `longitude` blank.
Running `audit-station-metadata` against that blank worksheet must stay blocked
until a reviewer fills coordinates for all station ids.

## Regenerate The Consolidated Summary

```bash
python3 -m backend.reproduction.swiss_ravafcast.cli summarize-reproduction \
  --validation-report backend/artifacts/reproduction/swiss_ravafcast/data_validation_report.json \
  --rf4-result backend/artifacts/reproduction/swiss_ravafcast/rf4_result.json \
  --gpxyz-report backend/artifacts/reproduction/swiss_ravafcast/gpxyz_readiness_report.json \
  --aggregation-result backend/artifacts/reproduction/swiss_ravafcast/elev_simple_aggregation_result.json \
  --output backend/artifacts/reproduction/swiss_ravafcast/reproduction_summary.json \
  --output-markdown backend/artifacts/reproduction/swiss_ravafcast/reproduction_summary.md
```

The summary is generated evidence and should not be committed. It must continue
to report `production_scoring_allowed=false` and
`full_operational_detection_claim_allowed=false`.

## Run The RF4 Feature/Parity Audit

```bash
python3 -m backend.reproduction.swiss_ravafcast.cli audit-rf4-features \
  --manifest backend/data/swiss_envidat/swiss_ravafcast_data_manifest.json \
  --output backend/artifacts/reproduction/swiss_ravafcast/rf4_feature_parity_audit.json \
  --output-markdown backend/artifacts/reproduction/swiss_ravafcast/rf4_feature_parity_audit.md
```

The audit compares `auto_numeric_current`, `paper_candidate_whitelist`, and
`leakage_guarded` feature sets. It must be interpreted as a parity-risk audit,
not as production validation.
