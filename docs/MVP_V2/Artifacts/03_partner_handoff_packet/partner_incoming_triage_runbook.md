# Himalayan Incoming Partner Package Triage Runbook

Decision: `partner_incoming_triage_runbook_written_pending_partner_package`

Give the operator a deterministic first-response sequence for a real Himalayan partner evidence package without enabling production scoring or accuracy claims.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |
| Runbook is prediction evidence | `false` |
| Triage steps | 8 |

## Pre-Arrival Preparation

| Priority | Task | Rating | Reason |
|---:|---|---:|---|
| 1 | Confirm the partner package root path and keep the original package read-only. | 5 | Preserves provenance and prevents accidental edits to received evidence. |
| 2 | Regenerate the template bundle and package index in the local artifact area. | 5 | Ensures current schema, command order, and claim boundaries are visible before intake. |
| 3 | Prepare a previous manifest-diff snapshot if this is a resubmission. | 4 | Makes package changes auditable across partner attempts. |

## Triage Sequence

### 1. Preflight file presence

- Priority rating: `5/5`
- Stop unless decision is: `partner_intake_package_files_present`

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --partner-intake-root <partner-package-root> --partner-intake-preflight-output backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.json --partner-intake-preflight-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.md
```

### 2. Build source manifest starter if hashes are missing

- Priority rating: `4/5`
- Stop unless decision is: `not_applicable`

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --partner-evidence-root <partner-package-root> --partner-source-manifest-starter-output backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_starter.json --partner-source-manifest-starter-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_starter.md
```

### 3. Validate source manifest governance

- Priority rating: `5/5`
- Stop unless decision is: `partner_source_manifest_available`

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --partner-source-manifest <partner-package-root>/partner_source_manifest.json --partner-source-manifest-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.json --partner-source-manifest-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.md
```

### 4. Validate evidence CSV rows and source refs

- Priority rating: `5/5`
- Stop unless decision is: `all_partner_evidence_available`

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --partner-evidence-root <partner-package-root> --partner-source-manifest <partner-package-root>/partner_source_manifest.json --partner-evidence-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.json --partner-evidence-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.md
```

### 5. Run local holdout leakage audit

- Priority rating: `5/5`
- Stop unless decision is: `local_holdout_leakage_audit_passed_release_gate_attestation_required`

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --partner-evidence-root <partner-package-root> --partner-source-manifest <partner-package-root>/partner_source_manifest.json --local-holdout-leakage-audit-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_leakage_audit.json --local-holdout-leakage-audit-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_leakage_audit.md
```

### 6. Provide prediction-output template if model outputs are not ready

- Priority rating: `4/5`
- Stop unless decision is: `not_applicable`

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --local-holdout-prediction-template-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_prediction_template.json --local-holdout-prediction-template-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_prediction_template.md --local-holdout-prediction-template-csv backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_predictions.csv
```

### 7. Evaluate holdout metrics only after predictions exist

- Priority rating: `5/5`
- Stop unless decision is: `local_holdout_metrics_passed_release_gate_attestation_required`

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --partner-evidence-root <partner-package-root> --partner-source-manifest <partner-package-root>/partner_source_manifest.json --local-holdout-predictions <partner-package-root>/himalayan_local_holdout_predictions.csv --local-holdout-metric-report-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_metric_report.json --local-holdout-metric-report-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_metric_report.md
```

### 8. Write summary, score, checklist, ledger, and dashboard

- Priority rating: `5/5`
- Stop unless decision is: `not_applicable`

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --output-markdown backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.md --partner-intake-root <partner-package-root> --partner-evidence-root <partner-package-root> --partner-source-manifest <partner-package-root>/partner_source_manifest.json --partner-submission-summary-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.json --partner-submission-summary-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.md --partner-submission-quality-score-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.json --partner-submission-quality-score-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.md --partner-submission-acceptance-checklist-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.json --partner-submission-acceptance-checklist-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.md --partner-submission-review-ledger-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_review_ledger.json --partner-submission-review-ledger-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_review_ledger.md --partner-submission-status-dashboard-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_status_dashboard.json --partner-submission-status-dashboard-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_status_dashboard.md
```

## Routing Decisions

| Condition | Route | Rating |
|---|---|---:|
| missing required files, stale review, unsupported licenses, invalid source refs, or failed leakage audit | return_to_partner_for_resubmission | 5 |
| evidence and leakage pass, but holdout predictions are missing | request_frozen_candidate_predictions_using_template | 5 |
| holdout metrics pass all floors | prepare local_himalayan_holdout_passed attestation; keep production blocked | 5 |
| holdout metrics miss any floor | scientist/model-error review; do not weaken floors | 5 |

## Stop Conditions

- Stop on missing package files before row-level validation.
- Stop on invalid or stale partner_source_manifest.json before evidence validation.
- Stop on evidence validation failures before leakage audit or metrics.
- Stop on leakage audit failures before metric evaluation.
- Stop on metric floor failures before release-gate attestation.
- Stop before production scoring even if every research gate passes.

## Standards Anchors

| Anchor | Use | URL |
|---|---|---|
| NIST AI RMF Measure function | Document test sets, metrics, tools, and stop conditions before claims. | https://airc.nist.gov/airmf-resources/playbook/measure/ |
| FAIR provenance principle R1.2 | Keep source ownership, processing history, and reuse context explicit. | https://www.go-fair.org/fair-principles/r1-2-metadata-associated-detailed-provenance/ |
| RAvaFcast v1.0.0 | Preserve separate classification, interpolation, aggregation, and evaluation stages. | https://ui.adsabs.harvard.edu/abs/2024GMD....17.7569M/abstract |

## Claim Boundary

- Production scoring allowed: `false`
- Himalayan accuracy claim allowed: `false`
- Reason: The triage runbook is operator procedure only. It does not supply partner evidence, model predictions, metric proof, release-gate approval, or production authorization.
