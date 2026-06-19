# Himalayan Partner Evidence Intake Checklist

Decision: `partner_intake_checklist_written_pending_partner_submission`

This checklist tells partners how to package local Himalayan evidence for validation. It does not authorize a Himalayan accuracy claim or production scoring.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |
| Required package files | 11 |

## Intake Steps

| Step | Name | Check |
|---:|---|---|
| 1 | Prepare source packages | Compute SHA-256 for each source package and add it to partner_source_manifest.json. |
| 2 | Complete source manifest | Every source has owner, dataset, license_scope, date_range, review_status=reviewed, reviewer_id, reviewed_at, and evidence_package_ref. |
| 3 | Fill evidence CSVs | Use reviewed rows only; every source_ref must point to a manifest SHA-256 or a local file hash reference. |
| 4 | Validate source manifest first | Run the standalone source-manifest validation before full evidence validation. |
| 5 | Validate all evidence | Run the partner evidence validation and keep blocked outputs if any group is incomplete, stale, undersized, unlicensed, or unreviewed. |

## Required Package Files

| Path | Type | Requirement | Minimum reviewed rows |
|---|---|---|---:|
| `partner_source_manifest.json` | `source_manifest` | source_manifest | n/a |
| `station_metadata.csv` | `evidence_csv` | station_metadata | 10 |
| `weather_station_observations.csv` | `evidence_csv` | weather_station_observations | 30 |
| `snowpack_profile_features.csv` | `evidence_csv` | snowpack_profile_features | 20 |
| `danger_labels_and_bulletins.csv` | `evidence_csv` | danger_labels_and_bulletins | 10 |
| `warning_region_polygons.csv` | `evidence_csv` | warning_region_polygons | 1 |
| `historical_avalanche_events.csv` | `evidence_csv` | historical_avalanche_events | 10 |
| `remote_sensing_validation_scenes.csv` | `evidence_csv` | remote_sensing_validation_scenes | 5 |
| `terrain_ates_runout_validation.csv` | `evidence_csv` | terrain_ates_runout_validation | 3 |
| `scientist_reviews.csv` | `evidence_csv` | scientist_reviews | 20 |
| `independent_himalayan_holdout.csv` | `evidence_csv` | independent_himalayan_holdout | 1 |

## Validation Outputs

- `partner_source_manifest_validation.json`
- `partner_source_manifest_validation.md`
- `partner_evidence_validation.json`
- `partner_evidence_validation.md`
- `readiness_contract.json`
- `readiness_contract.md`

## Package Rules

- Source manifest required: `true`
- Review status required: `reviewed`
- Evidence max review age: `365` days
- Source manifest max review age: `365` days
- Allowed license scopes: `cc_by_nc_research_only`, `commercial_deployment_approved`, `internal_research_validation`, `partner_restricted_research`, `research_validation_only`
