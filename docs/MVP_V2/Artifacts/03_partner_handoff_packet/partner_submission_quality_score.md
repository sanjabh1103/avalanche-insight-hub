# Himalayan Partner Submission Quality Score

Decision: `blocked_quality_checks_not_run`

This scorecard grades partner evidence-package readiness. It is not a model accuracy result and does not authorize production scoring.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |
| Score | 0.0 / 100.0 |
| Readiness band | `not_run` |
| Failed dimensions | 6 |

## Dimensions

| Dimension | Score | Status | Evidence | Next action |
|---|---:|---|---|---|
| Required package files | 0.0 / 15.0 | `not_run` | `decision`=not_run, `present_file_count`=0, `required_file_count`=0 | Supply partner_source_manifest.json and all ten evidence CSV files. |
| Source manifest governance | 0.0 / 20.0 | `not_run` | `decision`=not_run, `source_count`=0, `valid_source_count`=0, `invalid_source_count`=0 | Map every source_ref SHA-256 to owner, dataset, license, date range, reviewer, and evidence package. |
| Evidence row sufficiency | 0.0 / 20.0 | `not_run` | `decision`=not_run, `available_requirement_count`=0, `requirement_count`=0 | Fill every evidence CSV with enough reviewed rows to meet the row floor. |
| Spatial, temporal, numeric coverage | 0.0 / 20.0 | `not_run` | `requirement_count`=0, `coverage_ratio`=0.0 | Broaden station, region, scene, case, time, elevation, or slope coverage where required. |
| Review freshness, license, and source controls | 0.0 / 15.0 | `not_run` | `requirement_count`=0, `review_license_source_ratio`=0.0 | Ensure every row is reviewed, fresh, license-supported, and linked to the source manifest. |
| Release-gate attestations | 0.0 / 10.0 | `not_run` | `decision`=not_run, `himalayan_accuracy_claim_allowed`=False | Supply accepted holdout, scientist-review, license-clearance, and promotion attestations after evidence passes. |

## Failed Dimensions

- `package_file_completeness`
- `source_governance`
- `evidence_row_sufficiency`
- `coverage_quality`
- `review_license_source_controls`
- `release_gate_readiness`

## Quality Policy

- Score is not accuracy: `true`
- Score is not production authorization: `true`
