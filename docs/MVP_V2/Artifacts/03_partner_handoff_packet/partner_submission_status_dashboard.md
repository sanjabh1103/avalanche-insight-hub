# Himalayan Partner Submission Status Dashboard

Decision: `partner_submission_status_dashboard_blocked_partner_action_required`

This dashboard is a one-page status export for operators and scientists. It summarizes the latest package blocker, quality score, top-10 feature readiness, and claim gates.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |
| Dashboard is prediction evidence | `false` |
| Latest blocker | `intake_preflight` |
| Latest quality score | 0.0 / 100.0 |
| Readiness band | `not_run` |
| Submissions tracked | 1 |
| Top-10 blocked features | 10 / 10 |
| Package artifacts | 24 |

## Source Artifacts

| Artifact | Schema | Decision |
|---|---|---|
| `partner_package_index.json` | `himalayan_accuracy_partner_package_index_v1` | `partner_package_index_written_pending_partner_submission` |
| `partner_submission_review_ledger.json` | `himalayan_accuracy_partner_submission_review_ledger_v1` | `partner_submission_review_ledger_updated_blocked` |
| `partner_submission_summary.json` | `himalayan_accuracy_partner_submission_status_v1` | `blocked_submission_checks_not_run` |
| `partner_submission_quality_score.json` | `himalayan_accuracy_partner_submission_quality_score_v1` | `blocked_quality_checks_not_run` |
| `partner_submission_acceptance_checklist.json` | `himalayan_accuracy_partner_submission_acceptance_checklist_v1` | `blocked_acceptance_checklist_partner_fixes_required` |
| `himalayan_top10_feature_gap_matrix.json` | `himalayan_accuracy_top10_feature_gap_matrix_v1` | `top10_feature_gap_matrix_written_pending_partner_evidence` |
| `readiness_contract.json` | `himalayan_accuracy_readiness_contract_v2` | `blocked_pending_himalayan_evidence` |

## Release Gates

| Gate | Passed |
|---|---:|
| `local_himalayan_holdout_passed` | `false` |
| `scientist_review_complete` | `false` |
| `license_clearance_complete` | `false` |
| `production_promotion_approved` | `false` |

## Missing Files

- `partner_source_manifest.json`

## Next Actions

- Supply partner_source_manifest.json and all ten evidence CSV files.
- Validate source owner, license, reviewer, freshness, and evidence package refs.
- Fix missing, stale, undersized, unreviewed, unlicensed, or invalid evidence rows.
- Supply release-gate attestations for holdout, scientist review, license clearance, and promotion approval.
- Map every source_ref SHA-256 to owner, dataset, license, date range, reviewer, and evidence package.
- Fill every evidence CSV with enough reviewed rows to meet the row floor.
- Broaden station, region, scene, case, time, elevation, or slope coverage where required.
- Ensure every row is reviewed, fresh, license-supported, and linked to the source manifest.
- Supply accepted holdout, scientist-review, license-clearance, and promotion attestations after evidence passes.
- Supply all missing required package files before scientist review.
- Obtain a complete partner source manifest and filled station/weather/snowpack/danger CSVs.
- Run calibrated model evaluation only after local partner labels and holdout are available.
- Validate station coordinate coverage, then run GPxyz LOOCV and grid generation.
- Acquire reviewed warning-region polygons and elevation-band policy.
- Add reviewed snowpack profile exports and map fields to controlled partner schema.

## Operator Guardrails

- Use this dashboard as a status export, not as prediction evidence.
- Do not open scientist review until scientist_review_ready=true.
- Do not open claim review until claim_review_ready=true.
- Do not claim Himalayan accuracy until all release gates pass with validated evidence.
- Do not enable production scoring from this research artifact.

## Standards Anchors

| Anchor | Use | URL |
|---|---|---|
| NIST AI Risk Management Framework | Keep AI risk decisions visible, governed, and traceable. | https://www.nist.gov/itl/ai-risk-management-framework |
| WMO WIS/WIGOS monitoring practice | Expose current status and historical performance/blockers through a monitor-style dashboard. | https://wmo-im.github.io/wis2-manual/manual/wis2-manual-APPROVED.html |
| ISO 19157 geospatial data quality | Report completeness, lineage, and quality status for geospatial evidence. | https://www.iso.org/standard/78900.html |
| FAIR data principles | Keep evidence artifacts findable, reusable, source-referenced, and auditable. | https://www.go-fair.org/fair-principles/ |

## Claim Boundary

- Production scoring allowed: `false`
- Himalayan accuracy claim allowed: `false`
- Reason: The dashboard summarizes package and review state. It is not local Himalayan validation, model performance evidence, release-gate approval, or production authorization.
