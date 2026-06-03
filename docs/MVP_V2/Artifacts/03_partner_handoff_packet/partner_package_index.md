# Himalayan Partner Evidence Package Index

Decision: `partner_package_index_written_pending_partner_submission`

This index is the one-file handoff for the Himalayan partner evidence package. It links the checklist, preflight, source-manifest starter, validations, submission summary, and readiness contract.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |
| Required partner files | 11 |
| Artifact sequence steps | 24 |

## Artifact Sequence

| Step | Artifact | Purpose | Command flags |
|---:|---|---|---|
| 1 | `partner_handoff_readme.md` | Compact first-read handoff that points to the package index, scorecard, acceptance checklist, examples, and resubmission commands. | `--partner-handoff-readme-output`, `--partner-handoff-readme-markdown` |
| 2 | `partner_field_dictionary.md` | Defines field meanings, units, formats, controlled values, and non-lossy danger-scale guidance. | `--partner-field-dictionary-output`, `--partner-field-dictionary-markdown` |
| 3 | `partner_sample_row_pack.md` | Shows example-only rows for each evidence CSV without creating submit-ready evidence files. | `--partner-sample-row-pack-output`, `--partner-sample-row-pack-markdown` |
| 4 | `partner_synthetic_validation_report.md` | Optional synthetic-only smoke package proving the validation chain can pass structurally without creating real Himalayan evidence. | `--partner-synthetic-validation-package-root`, `--partner-synthetic-validation-report-output`, `--partner-synthetic-validation-report-markdown` |
| 5 | `partner_intake_checklist.md` | Defines the required source manifest, evidence CSVs, package rules, and validation outputs. | `--partner-intake-checklist-output`, `--partner-intake-checklist-markdown` |
| 6 | `partner_intake_dry_run_runbook.md` | Operator runbook for dry-running a real submitted partner package while keeping claims blocked. | `--partner-intake-dry-run-runbook-output`, `--partner-intake-dry-run-runbook-markdown` |
| 7 | `partner_incoming_triage_runbook.md` | First-response operator sequence for a real incoming partner package, including stop conditions and routing decisions. | `--partner-incoming-triage-runbook-output`, `--partner-incoming-triage-runbook-markdown` |
| 8 | `partner_intake_preflight.md` | Checks whether the source manifest and ten evidence CSV files are present before row-level validation. | `--partner-intake-preflight-output`, `--partner-intake-preflight-markdown` |
| 9 | `partner_source_manifest_starter.md` | Derives a fillable source manifest skeleton from source_ref hashes found in submitted evidence CSVs. | `--partner-source-manifest-starter-output`, `--partner-source-manifest-starter-markdown` |
| 10 | `partner_source_manifest_validation.md` | Validates source ownership, dataset names, licenses, dates, reviewer identity, freshness, and SHA-256 references. | `--partner-source-manifest-validation-output`, `--partner-source-manifest-validation-markdown` |
| 11 | `partner_evidence_validation.md` | Validates every partner evidence CSV for row count, coverage, values, freshness, licenses, and source references. | `--partner-evidence-validation-output`, `--partner-evidence-validation-markdown` |
| 12 | `partner_submission_quality_score.md` | Scores package completeness, source governance, evidence coverage, review controls, and release-gate readiness. | `--partner-submission-quality-score-output`, `--partner-submission-quality-score-markdown` |
| 13 | `partner_submission_acceptance_checklist.md` | Translates scorecard failures into partner-side fixes before scientist review or claim review. | `--partner-submission-acceptance-checklist-output`, `--partner-submission-acceptance-checklist-markdown` |
| 14 | `partner_submission_manifest_diff.md` | Compares package file presence, hashes, sizes, row counts, and schema versions against a previous submission snapshot. | `--partner-submission-manifest-diff-output`, `--partner-submission-manifest-diff-markdown` |
| 15 | `partner_submission_review_ledger.md` | Records each package attempt, fingerprint, score, blocker, review routing state, and resubmission action over time. | `--partner-submission-review-ledger-output`, `--partner-submission-review-ledger-markdown` |
| 16 | `partner_submission_status_dashboard.md` | One-page operator/scientist status export summarizing blocker, score, top-10 readiness, routing state, and claim gates. | `--partner-submission-status-dashboard-output`, `--partner-submission-status-dashboard-markdown` |
| 17 | `himalayan_local_holdout_protocol.md` | Pre-registers independent Himalayan holdout split rules, leakage checks, metrics, floors, and report outputs before evaluation. | `--local-holdout-protocol-output`, `--local-holdout-protocol-markdown` |
| 18 | `himalayan_local_holdout_leakage_audit.md` | Checks independent holdout rows, source-ref manifest coverage, and source-ref overlap before metric evaluation. | `--local-holdout-leakage-audit-output`, `--local-holdout-leakage-audit-markdown` |
| 19 | `himalayan_local_holdout_prediction_template.md` | Defines the header-only predictions CSV that the local holdout metric report consumes after leakage audit pass. | `--local-holdout-prediction-template-output`, `--local-holdout-prediction-template-markdown`, `--local-holdout-prediction-template-csv` |
| 20 | `himalayan_local_holdout_metric_report.md` | Blocks metric evaluation until the leakage audit passes, then reports local holdout classification, calibration, and region floors. | `--local-holdout-metric-report-output`, `--local-holdout-metric-report-markdown`, `--local-holdout-predictions` |
| 21 | `partner_submission_summary.md` | Combines preflight, source-manifest validation, evidence validation, and readiness status into one first-blocker report. | `--partner-submission-summary-output`, `--partner-submission-summary-markdown` |
| 22 | `partner_source_package_checksum_guide.md` | Explains SHA-256 source-package checksums, source_ref syntax, and partner_source_manifest.json handoff rules. | `--partner-source-package-checksum-guide-output`, `--partner-source-package-checksum-guide-markdown` |
| 23 | `release_gate_attestation_template_pack.md` | Fillable template pack for holdout, scientist-review, license, and promotion attestations after evidence passes. | `--release-gate-attestation-template-pack-output`, `--release-gate-attestation-template-pack-markdown` |
| 24 | `readiness_contract.md` | Shows the release-gated Himalayan accuracy-readiness contract after validated evidence and attestations are applied. | `--output`, `--output-markdown` |

## Required Partner Files

| Path | Type | Requirement |
|---|---|---|
| `partner_source_manifest.json` | `source_manifest` | source_manifest |
| `station_metadata.csv` | `evidence_csv` | station_metadata |
| `weather_station_observations.csv` | `evidence_csv` | weather_station_observations |
| `snowpack_profile_features.csv` | `evidence_csv` | snowpack_profile_features |
| `danger_labels_and_bulletins.csv` | `evidence_csv` | danger_labels_and_bulletins |
| `warning_region_polygons.csv` | `evidence_csv` | warning_region_polygons |
| `historical_avalanche_events.csv` | `evidence_csv` | historical_avalanche_events |
| `remote_sensing_validation_scenes.csv` | `evidence_csv` | remote_sensing_validation_scenes |
| `terrain_ates_runout_validation.csv` | `evidence_csv` | terrain_ates_runout_validation |
| `scientist_reviews.csv` | `evidence_csv` | scientist_reviews |
| `independent_himalayan_holdout.csv` | `evidence_csv` | independent_himalayan_holdout |

## Command Order

### 1. Generate templates and package index

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --templates-output-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates --partner-handoff-readme-output backend/artifacts/reproduction/himalayan_accuracy/partner_handoff_readme.json --partner-handoff-readme-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_handoff_readme.md --partner-field-dictionary-output backend/artifacts/reproduction/himalayan_accuracy/partner_field_dictionary.json --partner-field-dictionary-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_field_dictionary.md --partner-sample-row-pack-output backend/artifacts/reproduction/himalayan_accuracy/partner_sample_row_pack.json --partner-sample-row-pack-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_sample_row_pack.md --partner-source-package-checksum-guide-output backend/artifacts/reproduction/himalayan_accuracy/partner_source_package_checksum_guide.json --partner-source-package-checksum-guide-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_source_package_checksum_guide.md --partner-synthetic-validation-package-root backend/artifacts/reproduction/himalayan_accuracy/partner_synthetic_validation_package --partner-synthetic-validation-report-output backend/artifacts/reproduction/himalayan_accuracy/partner_synthetic_validation_report.json --partner-synthetic-validation-report-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_synthetic_validation_report.md --partner-intake-dry-run-runbook-output backend/artifacts/reproduction/himalayan_accuracy/partner_intake_dry_run_runbook.json --partner-intake-dry-run-runbook-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_intake_dry_run_runbook.md --partner-incoming-triage-runbook-output backend/artifacts/reproduction/himalayan_accuracy/partner_incoming_triage_runbook.json --partner-incoming-triage-runbook-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_incoming_triage_runbook.md --release-gate-attestation-template-pack-output backend/artifacts/reproduction/himalayan_accuracy/release_gate_attestation_template_pack.json --release-gate-attestation-template-pack-markdown backend/artifacts/reproduction/himalayan_accuracy/release_gate_attestation_template_pack.md --partner-package-index-output backend/artifacts/reproduction/himalayan_accuracy/partner_package_index.json --partner-package-index-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_package_index.md
```

### 2. Preflight submitted package files

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --partner-intake-root <partner-package-root> --partner-intake-preflight-output backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.json --partner-intake-preflight-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.md
```

### 3. Generate source manifest starter if needed

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --partner-evidence-root <partner-package-root> --partner-source-manifest-starter-output backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_starter.json --partner-source-manifest-starter-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_starter.md
```

### 4. Validate source manifest

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --partner-source-manifest <partner-package-root>/partner_source_manifest.json --partner-source-manifest-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.json --partner-source-manifest-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.md
```

### 5. Validate partner evidence and summarize blockers

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --output-markdown backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.md --partner-intake-root <partner-package-root> --partner-evidence-root <partner-package-root> --partner-source-manifest <partner-package-root>/partner_source_manifest.json --partner-evidence-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.json --partner-evidence-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.md --partner-submission-quality-score-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.json --partner-submission-quality-score-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.md --partner-submission-acceptance-checklist-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.json --partner-submission-acceptance-checklist-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.md --partner-submission-manifest-diff-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_manifest_diff.json --partner-submission-manifest-diff-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_manifest_diff.md --partner-submission-review-ledger-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_review_ledger.json --partner-submission-review-ledger-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_review_ledger.md --partner-submission-status-dashboard-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_status_dashboard.json --partner-submission-status-dashboard-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_status_dashboard.md --local-holdout-protocol-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_protocol.json --local-holdout-protocol-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_protocol.md --local-holdout-leakage-audit-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_leakage_audit.json --local-holdout-leakage-audit-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_leakage_audit.md --local-holdout-prediction-template-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_prediction_template.json --local-holdout-prediction-template-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_prediction_template.md --local-holdout-prediction-template-csv backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_predictions.csv --local-holdout-metric-report-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_metric_report.json --local-holdout-metric-report-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_metric_report.md --partner-submission-summary-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.json --partner-submission-summary-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.md --local-holdout-leakage-audit-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_leakage_audit.json --local-holdout-leakage-audit-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_leakage_audit.md --local-holdout-prediction-template-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_prediction_template.json --local-holdout-prediction-template-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_prediction_template.md --local-holdout-prediction-template-csv backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_predictions.csv --local-holdout-metric-report-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_metric_report.json --local-holdout-metric-report-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_metric_report.md
```

## Claim Boundary

- Production scoring allowed: `false`
- Himalayan accuracy claim allowed: `false`
- Reason: This index is a partner handoff map. Local Himalayan evidence, source governance, release attestations, and promotion approval are still required.
