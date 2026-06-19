# Himalayan Partner Evidence Handoff README

Decision: `partner_handoff_readme_written_pending_partner_submission`

This is the first file to read before submitting or resubmitting Himalayan partner evidence. It points to the artifact map, scorecard, acceptance checklist, field dictionary, and sample rows.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |
| Quality score | 0.0 / 100.0 |
| Readiness band | `not_run` |
| Scientist review ready | `false` |
| Claim review ready | `false` |

## Open First

| Step | Artifact | Reason |
|---:|---|---|
| 1 | `partner_handoff_readme.md` | Start here for the short package navigation and resubmission sequence. |
| 2 | `partner_package_index.md` | Use this as the full artifact map and command-order reference. |
| 3 | `partner_submission_status_dashboard.md` | Use this for the one-page current blocker, score, top-10 readiness, and claim-gate status. |
| 4 | `partner_source_package_checksum_guide.md` | Use this before filling source_ref values or partner_source_manifest.json. |
| 5 | `partner_synthetic_validation_report.md` | Optional: smoke-test the validator with synthetic-only rows that must never be submitted as evidence. |
| 6 | `partner_intake_dry_run_runbook.md` | Use this to dry-run a real submitted package and interpret expected blocked/pass decisions. |
| 7 | `partner_incoming_triage_runbook.md` | Use this when a real partner package arrives to run the first-response sequence and route blockers. |
| 8 | `release_gate_attestation_template_pack.md` | Use this after evidence validation passes to document holdout, scientist-review, license, and promotion gates. |
| 9 | `himalayan_local_holdout_protocol.md` | Use this before any local model evaluation to lock split rules, leakage checks, metrics, and floors. |
| 10 | `himalayan_local_holdout_leakage_audit.md` | Run this when partner evidence arrives to block contaminated or source-unreviewed holdout rows. |
| 11 | `himalayan_local_holdout_prediction_template.md` | Use this to produce the exact predictions CSV consumed by the holdout metric report. |
| 12 | `himalayan_local_holdout_metric_report.md` | Run this after the leakage audit passes to evaluate locked local holdout classification and calibration floors. |
| 13 | `partner_submission_acceptance_checklist.md` | Fix every partner-side blocker before scientist review. |
| 14 | `partner_submission_quality_score.md` | Track package quality dimensions and score changes after resubmission. |
| 15 | `partner_submission_manifest_diff.md` | Confirm which files changed since the prior submitted package. |
| 16 | `partner_submission_review_ledger.md` | Track each package attempt, score, blocker, routing state, and resubmission action over time. |
| 17 | `partner_field_dictionary.md` | Confirm field meanings, units, formats, controlled values, and danger-scale mapping. |
| 18 | `partner_sample_row_pack.md` | Use example-only rows as a guide, not as evidence. |

## Resubmission Sequence

### 1. Fill partner package

Complete partner_source_manifest.json and all ten evidence CSVs using real reviewed Himalayan evidence.

### 2. Run full validation and blocker reports

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --output-markdown backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.md --partner-intake-root <partner-package-root> --partner-evidence-root <partner-package-root> --partner-source-manifest <partner-package-root>/partner_source_manifest.json --partner-intake-preflight-output backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.json --partner-intake-preflight-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.md --partner-source-manifest-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.json --partner-source-manifest-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.md --partner-evidence-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.json --partner-evidence-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.md --partner-submission-quality-score-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.json --partner-submission-quality-score-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.md --partner-submission-acceptance-checklist-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.json --partner-submission-acceptance-checklist-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.md --partner-submission-manifest-diff-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_manifest_diff.json --partner-submission-manifest-diff-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_manifest_diff.md --partner-submission-summary-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.json --partner-submission-summary-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.md
```

### 3. Route next review

Proceed to scientist review only when scientist_review_ready=true; proceed to claim review only when claim_review_ready=true.

## Do Not Claim

- Do not claim Himalayan accuracy readiness from blank templates, sample rows, or package navigation artifacts.
- Do not treat the submission quality score as prediction accuracy.
- Do not start production scoring, public claims, or promotion without validated evidence and release-gate attestations.
- Do not collapse five-level danger labels into four classes without reviewed mapping notes.

## Best-Practice Anchors

| Anchor | Use | URL |
|---|---|---|
| FAIR data principles | Keep partner evidence findable, reusable, and source-governed before scientific claims. | https://www.go-fair.org/fair-principles/ |
| WMO WIGOS data quality monitoring | Treat observation readiness as a quality-controlled data pipeline, not a one-off upload. | https://community.wmo.int/en/activity-areas/wigos/wigos-data-quality-monitoring-system-wdqms |
| ISO 19157-style geospatial quality dimensions | Track completeness, consistency, coverage, and lineage for geospatial evidence. | https://www.iso.org/standard/78900.html |

## Claim Boundary

- Production scoring allowed: `false`
- Himalayan accuracy claim allowed: `false`
- Reason: The handoff README is navigation only; it does not supply evidence, validate a model, or authorize production scoring.
