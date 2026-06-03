# Himalayan Partner Submission Acceptance Checklist

Decision: `blocked_acceptance_checklist_partner_fixes_required`

This checklist translates the package quality score into partner-side fixes before scientist review or claim review. It does not authorize production scoring.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |
| Scientist review ready | `false` |
| Claim review ready | `false` |
| Quality score | 0.0 / 100.0 |
| Blocking items | 6 |

## Acceptance Items

| Item | Status | Score | Acceptance criterion | Partner fix |
|---|---|---:|---|---|
| Required package files | `partner_action_required` | 0.0 / 15.0 | partner_source_manifest.json and all ten evidence CSV files are present. | Supply partner_source_manifest.json and all ten evidence CSV files. |
| Source manifest governance | `partner_action_required` | 0.0 / 20.0 | Every source hash has reviewed owner, dataset, license scope, date range, reviewer, and evidence package metadata. | Map every source_ref SHA-256 to owner, dataset, license, date range, reviewer, and evidence package. |
| Evidence row sufficiency | `partner_action_required` | 0.0 / 20.0 | Every evidence CSV meets its minimum reviewed-row floor. | Fill every evidence CSV with enough reviewed rows to meet the row floor. |
| Spatial, temporal, numeric coverage | `partner_action_required` | 0.0 / 20.0 | Required distinct, temporal, elevation, and slope coverage floors pass for every evidence group. | Broaden station, region, scene, case, time, elevation, or slope coverage where required. |
| Review freshness, license, and source controls | `partner_action_required` | 0.0 / 15.0 | Every row is fresh, reviewed, license-supported, SHA-256 referenced, and mapped to the source manifest. | Ensure every row is reviewed, fresh, license-supported, and linked to the source manifest. |
| Release-gate attestations | `partner_action_required` | 0.0 / 10.0 | Independent holdout, scientist review, license clearance, and promotion attestations pass after evidence acceptance. | Supply accepted holdout, scientist-review, license-clearance, and promotion attestations after evidence passes. |

## Scientist Review Blockers

- `package_file_completeness`
- `source_governance`
- `evidence_row_sufficiency`
- `coverage_quality`
- `review_license_source_controls`

## Partner Next Actions

- Supply partner_source_manifest.json and all ten evidence CSV files.
- Map every source_ref SHA-256 to owner, dataset, license, date range, reviewer, and evidence package.
- Fill every evidence CSV with enough reviewed rows to meet the row floor.
- Broaden station, region, scene, case, time, elevation, or slope coverage where required.
- Ensure every row is reviewed, fresh, license-supported, and linked to the source manifest.
- Supply accepted holdout, scientist-review, license-clearance, and promotion attestations after evidence passes.

## Claim Boundary

- Production scoring allowed: `false`
- Himalayan accuracy claim allowed: `false`
- Reason: The checklist gates partner evidence acceptance only. It does not authorize model claims or production scoring.
