# Synthetic Himalayan Partner Validation Package

Decision: `synthetic_partner_validation_package_structurally_passed_claims_blocked`

This artifact reports a synthetic-only validator smoke test. It is not partner evidence, not a benchmark, and not a basis for a Himalayan accuracy or production claim.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |
| Synthetic package root | `backend/artifacts/reproduction/himalayan_accuracy/partner_synthetic_validation_package` |
| Evidence files | 10 |
| Raw sources | 10 |
| Available requirements | 10 |
| Blocked release gates | 4 |

## Synthetic Data Policy

- `is_real_himalayan_evidence`: `false`
- `may_be_submitted_as_partner_evidence`: `false`
- `may_unlock_scientist_review`: `false`
- `may_unlock_himalayan_accuracy_claim`: `false`
- `reason`: `Rows are deterministic synthetic fixtures for validator smoke testing only.`

## Validation Decisions

| Check | Decision |
|---|---|
| `intake_preflight` | `partner_intake_package_files_present` |
| `source_manifest_validation` | `partner_source_manifest_available` |
| `evidence_validation` | `all_partner_evidence_available` |
| `readiness_contract` | `blocked_pending_himalayan_evidence` |
| `quality_score` | `partner_submission_quality_evidence_ready_release_gates_pending` |
| `acceptance_checklist` | `partner_submission_acceptance_scientist_review_ready_release_gates_pending` |
| `submission_summary` | `partner_submission_evidence_available_release_gates_pending` |

## Evidence Files

| Requirement | File | Rows | Source ref |
|---|---|---:|---|
| `station_metadata` | `station_metadata.csv` | 10 | `file:raw_sources/station_metadata_synthetic_source.txt#sha256=84a4f13d1efa7d5767f30ec50baae79590944438cc935b9e5cdc825b0f0cbddf` |
| `weather_station_observations` | `weather_station_observations.csv` | 30 | `file:raw_sources/weather_station_observations_synthetic_source.txt#sha256=d6861633743d1d9ad7ac2d3cd4c52ab2549dcacdae0d4d61c00c774856ba452b` |
| `snowpack_profile_features` | `snowpack_profile_features.csv` | 20 | `file:raw_sources/snowpack_profile_features_synthetic_source.txt#sha256=3e9d85aa611c0c42944c8e57bea206101e32fe016fb1e66f889f5ca936e21edc` |
| `danger_labels_and_bulletins` | `danger_labels_and_bulletins.csv` | 10 | `file:raw_sources/danger_labels_and_bulletins_synthetic_source.txt#sha256=3c1de6c55c1799fd4cee12dd65104925f42ba6a52832d1a9ac979f49f873b820` |
| `warning_region_polygons` | `warning_region_polygons.csv` | 3 | `file:raw_sources/warning_region_polygons_synthetic_source.txt#sha256=3f431644e603daaf55f44fdfe7e1b89ae1b464f50bf5999e1a7cda7911ee182b` |
| `historical_avalanche_events` | `historical_avalanche_events.csv` | 10 | `file:raw_sources/historical_avalanche_events_synthetic_source.txt#sha256=1be7e50b6663c298dd36a5d49b067992e946f603a76fe5a5116eb0b3c800be84` |
| `remote_sensing_validation_scenes` | `remote_sensing_validation_scenes.csv` | 5 | `file:raw_sources/remote_sensing_validation_scenes_synthetic_source.txt#sha256=4104e09ec0413cc4999f4cd88c3598a9847bcb1bc227cb8591e9195b71ce047e` |
| `terrain_ates_runout_validation` | `terrain_ates_runout_validation.csv` | 3 | `file:raw_sources/terrain_ates_runout_validation_synthetic_source.txt#sha256=0dcccd670c041587b8ca8806ec22b929d0b4a0c88213e7e7613bf51dc26faf5a` |
| `scientist_reviews` | `scientist_reviews.csv` | 20 | `file:raw_sources/scientist_reviews_synthetic_source.txt#sha256=a928da8882daaeff7443374d607eef325e6f17d06229c11e1608c10ffb708ff3` |
| `independent_himalayan_holdout` | `independent_himalayan_holdout.csv` | 1 | `file:raw_sources/independent_himalayan_holdout_synthetic_source.txt#sha256=da11c0c00de58d3a5c14dc293f050fed310f6bc31a27df1214340fdf30ab8cb3` |

## Claim Boundary

- Production scoring allowed: `false`
- Himalayan accuracy claim allowed: `false`
- Reason: The synthetic package proves validator plumbing only. Real reviewed Himalayan evidence and release-gate attestations are still required.
