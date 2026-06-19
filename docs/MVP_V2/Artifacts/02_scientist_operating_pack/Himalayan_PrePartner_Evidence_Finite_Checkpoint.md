# Himalayan Pre-Partner Evidence Finite Checkpoint

Updated: May 23, 2026

## Claim Boundary

Real Himalayan partner evidence is expected next week. Until it arrives, the
right work is to harden intake, validation, governance, and reproducibility.
No local Himalayan accuracy claim, production scoring, deployment, Supabase
mutation, GPU job, or public UI claim is authorized by this checkpoint.

Scientific anchors:

- NHESS 2022 distinguishes raw forecast labels from quality-controlled
  `D_tidy` labels, so raw public bulletins are not enough as training truth:
  <https://nhess.copernicus.org/articles/22/2031/2022/>
- GMD 2024 RAvaFcast uses a three-stage workflow: station danger classification,
  GPxyz interpolation, and elevation/warning-region aggregation:
  <https://gmd.copernicus.org/articles/17/7569/2024/>
- WMO WIGOS data-quality practice supports treating station observations as a
  monitored quality pipeline rather than a one-time file upload:
  <https://community.wmo.int/en/activity-areas/wigos/wigos-data-quality-monitoring-system-wdqms>
- FAIR data principles support explicit provenance, reusability, and source
  traceability for scientific evidence packages:
  <https://www.go-fair.org/fair-principles/>

## Table 1: Work Possible Before Real Partner Evidence Arrives

Rating: 5 = high value and feasible without real evidence; 1 = low value or
blocked until evidence arrives.

| Priority | Pre-Evidence Task | Why It Matters | Current Status | Implemented Now? | Rating /5 |
|---:|---|---|---|---|---:|
| 1 | One-command partner package triage wrapper | The first real package should produce preflight, source-manifest, evidence, holdout, quality, ledger, and dashboard artifacts in one reproducible run. | Individual builders existed, but no single operator entry point. | Yes: `backend/scripts/run_himalayan_partner_package_triage.py` | 5 |
| 2 | `D_tidy`-equivalent label provenance schema | Prevents training on unverified public bulletin labels and forecaster noise. | v3 contract requires label source, review basis, nowcast/observer refs, regime, timing, elevation, and aspect policy. | Already implemented in v3; documented here | 5 |
| 3 | GPxyz station-density diagnostics | Station lat/lon/elevation is necessary but insufficient; sparse station coverage must be surfaced before interpolation claims. | v3 contract reports station count, region count, elevation span, and sparse warnings. | Already implemented in v3; included in wrapper outputs | 5 |
| 4 | Refined discretization guardrails | RAvaFcast-style class thresholds can improve rare-class prediction, but thresholds must not leak validation/test labels. | Swiss reproduction helper computes monotonic thresholds from training/OOB distributions only. | Already implemented and tested | 4 |
| 5 | Partner source-manifest starter | Incoming packages may include `source_ref` digests but no completed manifest. Starter lets the operator return a precise source-governance fix list. | Existing builder; now included in one-command wrapper output. | Yes, wrapper emits it | 4 |
| 6 | Local holdout protocol and prediction template | The partner can prepare model-output handoff shape before any model run. | Existing protocol/template; wrapper writes them beside triage output. | Yes, wrapper emits JSON/MD/CSV template | 4 |
| 7 | Submission quality score and acceptance checklist | Converts a confusing package into objective partner fixes before scientist review. | Existing builders; now included in one-command wrapper output. | Yes, wrapper emits both | 5 |
| 8 | Review ledger and status dashboard | Enables repeatable resubmission tracking and a one-page current-state view. | Existing builders; now included in one-command wrapper output. | Yes, wrapper emits both | 4 |
| 9 | Triage artifact manifest | FAIR-style reuse needs a file inventory with paths, sizes, hashes, and purposes. | Wrapper now emits `triage_artifact_manifest.json` and `.md`. | Yes | 4 |
| 10 | Source-ref traceability report | Manifest source hashes must plumb through to evidence CSV `source_ref` values before any partner package can be trusted. | Wrapper now emits `triage_source_traceability.json` and `.md`. | Yes | 5 |
| 11 | Partner-facing finite checkpoint documentation | Keeps stakeholders aligned while evidence is not yet available. | This document records what is possible now and what remains blocked. | Yes | 4 |
| 12 | UI implementation for accuracy-readiness | Useful later, but premature before real package shapes and blocker states are exercised. | Design-only; do not implement public UI from synthetic data. | Deferred intentionally | 2 |

## Gemini Advice Cross-Verification

| Suggestion | Cross-Verification | Adversarial Finding | Decision / Action | Rating /5 |
|---|---|---|---|---:|
| Defer the accuracy-readiness UI dashboard | Valid. Real blocker/error shapes are not known until the first partner package is triaged. | A synthetic-data UI would make brittle assumptions and may imply readiness before evidence exists. | Keep UI deferred; build only after real triage outputs stabilize. | 5 |
| Prioritize partner handoff | Valid. The partner needs the handoff README, field dictionary, source-manifest guide, and blank v3 CSV templates before data delivery. | Handoff must not include synthetic rows as evidence. | Use `build_himalayan_accuracy_readiness_contract --templates-output-root` to generate the partner pack; send only templates/docs, not generated synthetic fixtures. | 5 |
| Run the synthetic validation checkpoint | Valid. The repo has a synthetic package generator that exercises the validation chain without real evidence. | Synthetic pass must never unlock claims or scientist review. | Keep synthetic data policy locked and run synthetic package through the triage wrapper before delivery day. | 5 |
| Compare synthetic source hashes to the artifact manifest | Partly valid but imprecise. The artifact manifest hashes emitted reports; source-manifest hashes are raw source-package digests. | Comparing source digests to report-file digests is a category error. | Added `triage_source_traceability.json/.md` to compare manifest hashes, validated manifest hashes, and evidence `source_ref` hashes directly; artifact manifest then hashes that report. | 5 |
| Confirm safety locks even on synthetic success | Valid and critical. A structurally perfect synthetic package is still not Himalayan evidence. | Any synthetic path that flips `himalayan_accuracy_claim_allowed` or `production_scoring_allowed` would be a governance failure. | Tests verify traceability passes while both safety flags stay false. | 5 |

## Table 2: Next Finite Checkpoint Gap Analysis

This is the exact completion checklist for the current Himalayan evidence task.

| # | Needed Item | Current Evidence | Gap | Done Criteria | Owner | Rating /5 |
|---:|---|---|---|---|---|---:|
| 1 | Real partner package root | Templates and triage wrapper are ready. | No real files yet. | Partner supplies package folder with required CSVs and source manifest. | Partner/operator | 5 |
| 2 | `partner_source_manifest.json` | Starter/validator are ready. | No reviewed source manifest yet. | Manifest validates as `partner_source_manifest_available`. | Partner/source reviewer | 5 |
| 3 | Ten evidence CSV files | v3 templates exist. | Real rows absent. | Preflight decision is `partner_intake_package_files_present`. | Partner/operator | 5 |
| 4 | Quality-controlled danger labels | v3 requires `D_tidy` provenance. | No local reviewed label rows yet. | `danger_labels_and_bulletins.csv` passes row count, controlled values, source refs, freshness, and manifest checks. | Partner/scientist | 5 |
| 5 | Station metadata for GPxyz | Required columns and density diagnostics exist. | Real lat/lon/elevation coverage absent. | `station_metadata.csv` passes station count, region count, elevation span, and source governance. | Partner/operator | 5 |
| 6 | Snowpack/profile provenance | v3 requires model/version/timing fields. | HIM-STRAT/SNOWPACK-like local profiles absent. | `snowpack_profile_features.csv` validates with reviewed source refs and profile-model metadata. | Partner/scientist | 4 |
| 7 | Historical event/observer evidence | Event schema now includes regime, field report, and atlas refs. | Real event corroboration absent. | `historical_avalanche_events.csv` validates and links to source manifest. | Partner/scientist | 4 |
| 8 | Independent Himalayan holdout | Protocol/template exist. | No real independent holdout rows or predictions. | Leakage audit passes, then metric report evaluates predictions against locked floors. | Scientist/operator | 5 |
| 9 | Release-gate attestations | Templates exist. | No completed holdout/scientist/license/promotion attestations. | Readiness contract reaches `ready_for_himalayan_accuracy_claim_review`; production remains separately gated. | Governance owners | 4 |
| 10 | Repeatable operator command | One-command wrapper now exists. | Needs first run on real package next week. | `python3 -m backend.scripts.run_himalayan_partner_package_triage --partner-package-root <package> --output-root <out>` completes and emits triage summary. | Codex/operator | 5 |

## Table 3: Current Gap Analysis For The Avalanche Prediction Strategy

| Gap | Risk If Ignored | Current Mitigation | Next Action When Evidence Arrives | Rating /5 |
|---|---|---|---|---:|
| Raw bulletins mistaken for truth | Model learns human forecast noise. | v3 requires `D_tidy`-equivalent provenance. | Reject or quarantine rows without nowcast/observer/reanalysis basis. | 5 |
| Sparse station network hidden | GPxyz uncertainty gets undercommunicated. | Station-density diagnostics and GPxyz blocked state. | Review station count, region count, elevation span, and sparse warnings. | 5 |
| Swiss evidence overgeneralized to Himalaya | False confidence in local accuracy. | Research-only boundary and local holdout gates. | Require local evidence and release-gate attestations. | 5 |
| Refined thresholds leak holdout labels | Inflated class accuracy. | Training/OOB-only threshold helper and tests. | Compute any thresholds only from training/OOB data. | 4 |
| Source provenance weak | Package cannot be audited or reused. | SHA-256 `source_ref` and source-manifest validation. | Block rows missing manifest-backed source refs. | 5 |
| License scope ambiguous | Evidence cannot be safely used externally. | Controlled license scopes and score dimensions. | Require reviewed license scope before claim review. | 4 |
| Holdout contaminated by training/threshold selection | Invalid release evidence. | Leakage audit and final holdout protocol. | Stop if source refs overlap or leakage text is inadequate. | 5 |
| UI claims outrun science | Client/public trust risk. | No public claim/UI implementation in this checkpoint. | Build UI only after real triage outputs stabilize. | 4 |

## One-Command Triage Command

Run this when the real partner package arrives:

```bash
python3 -m backend.scripts.run_himalayan_partner_package_triage \
  --partner-package-root <partner-package-root> \
  --output-root backend/artifacts/reproduction/himalayan_accuracy/partner_triage_YYYYMMDD
```

Optional resubmission inputs:

```bash
python3 -m backend.scripts.run_himalayan_partner_package_triage \
  --partner-package-root <partner-package-root> \
  --output-root backend/artifacts/reproduction/himalayan_accuracy/partner_triage_YYYYMMDD \
  --previous-manifest-diff backend/artifacts/reproduction/himalayan_accuracy/partner_triage_previous/partner_submission_manifest_diff.json \
  --previous-review-ledger backend/artifacts/reproduction/himalayan_accuracy/partner_triage_previous/partner_submission_review_ledger.json
```

Expected current behavior before real evidence:

- `triage_summary.decision=triage_complete_partner_action_required`
- `production_scoring_allowed=false`
- `himalayan_accuracy_claim_allowed=false`
- first blockers point to missing source manifest, blank CSV rows, or partner fixes.

## Partner Handoff And Synthetic Checkpoint

Before the real package arrives, generate partner handoff templates with:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --output-markdown backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.md \
  --templates-output-root backend/artifacts/reproduction/himalayan_accuracy/partner_handoff_v3
```

Send the partner the generated `partner_handoff_readme.md`,
`partner_field_dictionary.md`, `partner_source_package_checksum_guide.md`,
`partner_source_manifest_template.md`, and the blank v3 CSV templates. Do not
send `partner_synthetic_validation_package/` as evidence.

Run the synthetic checkpoint with:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/synthetic_smoke/readiness_contract.json \
  --partner-synthetic-validation-package-root backend/artifacts/reproduction/himalayan_accuracy/synthetic_smoke/partner_synthetic_validation_package \
  --partner-synthetic-validation-report-output backend/artifacts/reproduction/himalayan_accuracy/synthetic_smoke/partner_synthetic_validation_report.json \
  --partner-synthetic-validation-report-markdown backend/artifacts/reproduction/himalayan_accuracy/synthetic_smoke/partner_synthetic_validation_report.md

python3 -m backend.scripts.run_himalayan_partner_package_triage \
  --partner-package-root backend/artifacts/reproduction/himalayan_accuracy/synthetic_smoke/partner_synthetic_validation_package \
  --output-root backend/artifacts/reproduction/himalayan_accuracy/synthetic_smoke/triage_output
```

Expected synthetic checkpoint:

- `partner_synthetic_validation_report.decision=synthetic_partner_validation_package_structurally_passed_claims_blocked`
- `triage_source_traceability.decision=source_traceability_passed_perfect_match_claims_blocked`
- `triage_artifact_manifest.decision=triage_artifact_manifest_complete`
- `production_scoring_allowed=false`
- `himalayan_accuracy_claim_allowed=false`

## Completion Criteria For This Task

This task can be considered complete when:

1. The real partner package is received.
2. The one-command triage wrapper completes without runtime errors.
3. `partner_intake_preflight.json` proves required files are present.
4. `partner_source_manifest_validation.json` either passes or gives exact source-governance fixes.
5. `partner_evidence_validation.json` either passes all ten evidence groups or gives exact row/schema/source/freshness/license fixes.
6. `himalayan_local_holdout_leakage_audit.json` refuses contaminated holdout evidence until independence is proven.
7. `partner_submission_quality_score.json`, `partner_submission_acceptance_checklist.json`, `partner_submission_review_ledger.json`, and `partner_submission_status_dashboard.json` exist and keep production blocked.
8. `triage_source_traceability.json` proves source-manifest hashes and evidence `source_ref` hashes match, or identifies exact mismatches.
9. `triage_artifact_manifest.json` inventories emitted files with SHA-256 digests for handoff and resubmission tracking.
10. Any future claim review uses release-gate attestations and never treats triage success as production authorization.
