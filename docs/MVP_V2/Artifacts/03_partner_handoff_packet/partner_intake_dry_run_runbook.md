# Himalayan Partner Intake Dry-Run Runbook

Decision: `partner_intake_dry_run_runbook_written_pending_partner_package`

This runbook tells an operator how to dry-run a real Himalayan partner submission package. It is a procedure artifact only and does not authorize claims.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |
| Required partner files | 11 |

## Operator Inputs

| Name | Required | Description |
|---|---:|---|
| `<partner-package-root>` | `true` | Directory containing partner_source_manifest.json, raw_sources/, and ten filled evidence CSV files. |
| `<previous-manifest-diff-json>` | `false` | Optional previous partner_submission_manifest_diff.json for resubmission comparison. |

## Dry-Run Steps

### 1. Confirm package files

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --partner-intake-root <partner-package-root> --partner-intake-preflight-output backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.json --partner-intake-preflight-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.md
```

- Expected pass decision: `partner_intake_package_files_present`
- Expected blocked decision: `blocked_missing_partner_intake_files`
- Stop if blocked: `true`

### 2. Validate source manifest

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --partner-source-manifest <partner-package-root>/partner_source_manifest.json --partner-source-manifest-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.json --partner-source-manifest-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.md
```

- Expected pass decision: `partner_source_manifest_available`
- Expected blocked decision: `partner_source_manifest_not_supplied or blocked_invalid_partner_source_manifest`
- Stop if blocked: `true`

### 3. Validate evidence rows

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --partner-evidence-root <partner-package-root> --partner-source-manifest <partner-package-root>/partner_source_manifest.json --partner-evidence-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.json --partner-evidence-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.md
```

- Expected pass decision: `all_partner_evidence_available`
- Expected blocked decision: `blocked_pending_partner_evidence`
- Stop if blocked: `true`

### 4. Score and summarize submission

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --output-markdown backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.md --partner-intake-root <partner-package-root> --partner-evidence-root <partner-package-root> --partner-source-manifest <partner-package-root>/partner_source_manifest.json --partner-submission-quality-score-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.json --partner-submission-quality-score-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.md --partner-submission-acceptance-checklist-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.json --partner-submission-acceptance-checklist-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.md --partner-submission-summary-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.json --partner-submission-summary-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.md
```

- Expected pass decision: `partner_submission_evidence_available_release_gates_pending`
- Expected blocked decision: `blocked_submission_checks_not_run or blocked_<first_blocker>`
- Stop if blocked: `false`

### 5. Capture manifest diff

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json --partner-intake-root <partner-package-root> --partner-submission-manifest-diff-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_manifest_diff.json --partner-submission-manifest-diff-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_manifest_diff.md
```

- Expected pass decision: `partner_submission_manifest_diff_baseline_written or partner_submission_manifest_diff_changed`
- Expected blocked decision: `blocked_manifest_diff_current_package_incomplete`
- Stop if blocked: `false`

- Optional previous snapshot flag: `--partner-submission-manifest-diff-previous <previous-manifest-diff-json>`

## Interpretation Rules

- A dry-run pass means the package is structurally ready for scientist review, not production.
- Any blocked preflight, source-manifest, or evidence-validation decision should be returned to the partner before scientist review.
- A quality score is evidence-package readiness, not model accuracy.
- Release-gate readiness requires separate accepted holdout, scientist-review, license-clearance, and promotion attestations.
- Never copy synthetic fixture rows into a partner package.

## Expected Current Template Status

- Decision: `blocked_missing_partner_intake_files`
- Reason: The generated template folder intentionally lacks partner_source_manifest.json and real reviewed rows.

## Claim Boundary

- Production scoring allowed: `false`
- Himalayan accuracy claim allowed: `false`
- Reason: This runbook is an operator procedure. It does not provide partner evidence, scientific acceptance, or production authorization.
