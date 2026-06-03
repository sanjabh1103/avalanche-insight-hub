# Avalanche Prediction Accuracy Top 10 Gap Plan

Updated: May 23, 2026

## Confidence Position

I am **not 100% confident** that the current strategy is enough to make the app
world class for accurate Himalayan avalanche prediction yet. The strategy is
directionally strong because it separates public scoring from research evidence,
uses scientist validation, and now includes Swiss RAvaFcast reproduction and
European SAR shadow gates. The loophole is that method evidence is still not the
same as Himalayan operational accuracy.

World-class status requires this stricter target:

> A Himalayan prediction claim is allowed only when local station/weather,
> snowpack, terrain, event, remote-sensing, and scientist-review evidence pass
> explicit benchmark and holdout gates.

## Scientific Anchors

| Anchor | What It Adds To The Strategy | Implementation Implication |
|---|---|---|
| RAvaFcast v1.0.0, 2024: three-stage classification -> GP interpolation -> elevation-band aggregation ([GMD](https://gmd.copernicus.org/articles/17/7569/2024/)) | The strongest operational pattern is not a standalone cell model; it is a pipeline from station danger prediction to spatial/regional forecast. | Build Stage 1-3 parity before claiming Swiss-style regional danger forecast capability. |
| NHESS 2022 RF danger-level study: `D_forecast` vs quality-controlled `D_tidy` ([NHESS](https://nhess.copernicus.org/articles/22/2031/2022/)) | Human forecasts can contain label noise; training directly on raw public bulletins can reproduce human error. | Make label provenance, nowcast/observer evidence, review basis, and dry/wet regime mandatory before any Himalayan accuracy claim. |
| GMD 2024 RAvaFcast GPxyz and refined discretization details ([GMD](https://gmd.copernicus.org/articles/17/7569/2024/)) | In the Swiss setting, latitude/longitude/elevation GP interpolation plus refined expected-danger thresholds performed strongly and exposed uncertainty. | Require X/Y/Z station metadata with density diagnostics; compute refined thresholds from training/OOB distributions only. |
| Perez-Guillen et al., 2025: live-tested RF with SHAP explainability around 70% agreement ([NHESS](https://nhess.copernicus.org/articles/25/1331/2025/nhess-25-1331-2025.html)) | Explainability and probability calibration matter operationally, especially for forecaster trust. | Preserve TreeSHAP/current-driver explanations and add calibrated RF4 expected danger. |
| Techel et al., 2025: model-vs-human discriminatory skill ([NHESS](https://nhess.copernicus.org/articles/25/3333/2025/nhess-25-3333-2025.html)) | Accuracy alone is incomplete; models must be compared with expert forecasts and outcomes. | Add model-vs-scientist daily verification and discrimination metrics before promotion. |
| Herla et al., 2025: distributed snowpack simulation adds operational value ([NHESS](https://nhess.copernicus.org/articles/25/625/2025/)) | Weak-layer and snowpack simulations can improve forecast consistency. | Himalayan partner data must include SNOWPACK/HIM-STRAT-like features, not just weather. |
| Indian Himalaya avalanche susceptibility review, 2025 ([ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0012825225001680)) | Indian Himalayan risk depends on weather, terrain, geology/topography, remote sensing, and spatiotemporal modelling. | Treat Himalayan deployment as a local evidence program, not European/Swiss model transfer. |

## Top 10 Accuracy Features And Gap Analysis

Rating: 5 = implementation and evidence near the needed standard; 1 = mostly
missing. These ratings are about **Himalayan accuracy readiness**, not UI polish.

| # | Accuracy Feature | Current Repo Evidence | What Is Needed For World-Class Himalayan Prediction | Gap / Loophole | Rating /5 |
|---:|---|---|---|---|---:|
| 1 | `D_tidy`-equivalent Himalayan label provenance | Partner adapter docs and Swiss EnviDat mapping exist; v3 contract now requires label source, review basis, nowcast/observer refs, regime, and timing fields. | Partner-reviewed danger truth with local nowcast, observer, field-event, or reanalysis evidence; public bulletins can be inputs but not trusted training truth alone. | Without quality-controlled label provenance, the model can learn forecaster noise and no Himalayan accuracy claim is defensible. | 2 |
| 2 | Calibrated 4-class danger-level model | Current public scorer is RF baseline; Swiss RF4 reproduction lane exists and is research-only. | Calibrated danger-level model trained/evaluated on local or reviewed transfer data, with per-class F1 and high-danger performance. | RF4 initial signal is not paper-parity or Himalayan proof yet. | 3 |
| 3 | RAvaFcast-style spatial interpolation | GPxyz readiness and exact-GP cap now exist; real run blocked by missing station coordinates. | Station coordinate join, LOOCV RMSE, 1 km grid, uncertainty, and reviewed interpolation behavior. | Missing station metadata blocks spatial forecast parity. | 2 |
| 4 | Elevation-band warning-region aggregation | Station-row `elev-simple` baseline exists. | Official Himalayan warning-region polygons, elevation policy, refined rounding, mean/median day accuracy. | Current aggregation is not full regional forecast parity. | 2 |
| 5 | Distributed snowpack / weak-layer evidence | Snowpack proxy exists; Swiss data has weak-layer columns for reproduction. | HIM-STRAT/SNOWPACK-like local profiles, persistent weak-layer indicators, failure-depth/stability features. | Proxy scalars are not enough for weak-layer prediction claims. | 2 |
| 6 | Terrain, ATES, runout and exposure features | DEM, runout, map, impact overlays, 3D view exist. | Validated slope/aspect/elevation/terrain traps, ATES-style classes, runout model validation, exposure-sensitive risk surfaces. | Terrain UI exists, but terrain model validation is incomplete. | 3 |
| 7 | Remote-sensing avalanche evidence | SAR U-Net/AvalCD/SnowSlide shadow lane exists; v8 still fails SnowSlide research-grade. | Accepted SAR/optical/InSAR validation, fresh final holdout, preprocessing contracts, modality-specific gates. | SAR/remote sensing must remain shadow-only until gates pass. | 3 |
| 8 | Field reports and event-outcome feedback loop | Field reports, event ingestion, scientist validation cases, daily verification exist. | Enough real Himalayan paired events, label-quality workflow, false-positive/false-negative closure, training eligibility rules. | Workflow exists; local evidence volume is still insufficient. | 4 |
| 9 | Explainability, calibration and model-vs-human diagnostics | SHAP path, RF methodology docs, scientist daily verification, RF4 calibration work exists. | Artifact-level active SHAP proof, calibrated probability quality, model-vs-scientist discrimination metrics, decision curves. | Explanation exists but must be tied to each active artifact before claims. | 3 |
| 10 | Release gates, uncertainty and claim governance | Strong shadow gates, production blocks, scientist workflows, SAR closeout docs. | One promotion framework across RF4, MTS-LSTM, SAR, remote sensing, fresh holdouts, and uncertainty display. | Governance is strong; missing local validation keeps production claims blocked. | 4 |

## Missing Feature Backlog

| Priority | Missing Feature | Implementation Target | Done Criteria |
|---:|---|---|---|
| 1 | Himalayan partner evidence contract | Expand partner data request using the EnviDat mapping, `D_tidy` provenance, and RAvaFcast requirements. | Every required model feature has `available`, `partner_required`, or `not_applicable` status in `himalayan_accuracy_readiness_contract_v3`. |
| 2 | RF4 feature/parity audit | Completed: audit now reports auto numeric, paper-candidate whitelist, and leakage-guarded feature sets. | Artifact reports three feature sets, calibration metrics, and claim boundary; paper parity still blocked on GP/aggregation inputs. |
| 3 | Station metadata join | Add reviewed station coordinate CSV support. | GPxyz readiness moves from `blocked_station_coordinates_required` to joined coverage report. |
| 4 | GPxyz LOOCV and grid | Run exact GP only after station metadata exists. | LOOCV report has ME/MAE/RMSE and grid output with uncertainty. |
| 5 | Warning-region aggregation | Add polygon/elevation-band input contract. | Full aggregation readiness no longer blocks on polygons/grid. |
| 6 | Snowpack weak-layer features | Add HIM-STRAT/SNOWPACK schema and validation gates. | Local profiles map to weak-layer/stability fields used by the model. |
| 7 | Remote-sensing preprocessing contract | Formalize SAR/optical/InSAR preprocessing and gates. | Each modality has correction, co-registration, mask, label, and holdout requirements. |
| 8 | Model-vs-scientist discrimination report | Extend daily verification analytics beyond agreement rate. | Report compares model/scientist discrimination against outcomes and confidence. |
| 9 | Accuracy dashboard | Add scientist/admin accuracy-readiness view after backend artifacts stabilize. | UI shows top-10 readiness, blockers, evidence age, and promotion state. |
| 10 | Himalayan final holdout plan | Define independent heldout scenes/days/regions. | Holdout is independent from model selection and required before production claim. |

## Implementation Sequence

| Phase | Target | Why This Comes First | Output |
|---:|---|---|---|
| 1 | Lock claim boundary | Prevents inflated client/product claims while building. | Docs say current strategy is strong but not 100% complete. |
| 2 | Maintain Swiss RF4 audit as evidence | Determines whether the reproduction lane is trustworthy. | `rf4_feature_parity_audit` artifact and docs are current; do not call it paper parity until GP/aggregation inputs exist. |
| 3 | Partner data contract | Converts “Himalayan accuracy” into concrete data requirements. | Updated schema mapping and partner ask. |
| 4 | Station metadata and GPxyz | Enables spatial forecast parity. | Station join + LOOCV + GP grid, or formal blocker. |
| 5 | Warning-region aggregation | Converts station/grid evidence into forecast-region evidence. | Elevation-band regional forecast parity artifact. |
| 6 | Snowpack and terrain hardening | Addresses weak-layer, terrain and runout accuracy. | Validated snowpack/terrain feature reports. |
| 7 | Remote-sensing shadow gates | Adds avalanche/landslide detection evidence without overclaiming. | SAR/optical/InSAR gated reports. |
| 8 | Scientist verification expansion | Turns model output into governed local learning. | Model-vs-scientist/outcome reports. |
| 9 | Accuracy-readiness UI | Makes world-class evidence inspectable. | Admin/scientist dashboard, no public production claim. |
| 10 | Promotion and holdout review | Only after local evidence passes. | Production-readiness packet, not automatic promotion. |

## Loopholes To Close Before Strong Accuracy Claims

| Loophole | Fix |
|---|---|
| Public bulletins are treated as quality-controlled truth. | Require `label_source`, `tidy_label_review_basis`, nowcast/observer/event refs, dry/wet regime, and timing fields before training or claims. |
| Swiss/European evidence gets mistaken for Himalayan validation. | Keep all Swiss/SAR artifacts `research_only` until local Himalayan holdouts pass. |
| RF accuracy is inflated by leakage or split mismatch. | Require feature-set audit and calibration report before paper-comparable wording. |
| Refined discretization learns from validation/test data. | Compute thresholds only from training or out-of-bag expected-danger distributions and true labels. |
| Snowpack proxy is treated as weak-layer truth. | Require HIM-STRAT/SNOWPACK-like local profile validation. |
| Remote-sensing detections are promoted from scene demos. | Require held-out precision/recall/F1/FPR gates and fresh final holdout. |
| Expert review is unstructured or too sparse. | Use daily verification, component reviews, action ledger, and minimum evidence counts. |
| UI appears authoritative before science catches up. | Display explicit badges: `research_only`, `shadow_gated`, `production_blocked`, or `validated`. |

## Decision

The strategy is good enough to continue, but not enough to call complete. The
next factual confidence loop should close the RF4 feature/parity audit and the
Himalayan data-contract gap before building more public-facing accuracy claims.

## Machine-Readable Readiness Contract

The first implementation step is now tracked as
`backend.reproduction.himalayan_accuracy_contract`. It defines ten required
Himalayan evidence groups:

1. `station_metadata`
2. `weather_station_observations`
3. `snowpack_profile_features`
4. `danger_labels_and_bulletins`
5. `warning_region_polygons`
6. `historical_avalanche_events`
7. `remote_sensing_validation_scenes`
8. `terrain_ates_runout_validation`
9. `scientist_reviews`
10. `independent_himalayan_holdout`

Generate the local readiness artifact with:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --output-markdown backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.md
```

By default this artifact must say:

- `production_scoring_allowed=false`
- `himalayan_accuracy_claim_allowed=false`
- `decision=blocked_pending_himalayan_evidence`

Generate partner-fillable CSV templates for the ten evidence groups with:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --output-markdown backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.md \
  --templates-output-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates
```

You can write the top-10 feature gap matrix directly when the strategy needs a
machine-readable current-vs-needed view tied to the evidence contract:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --top10-feature-gap-matrix-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_top10_feature_gap_matrix.json \
  --top10-feature-gap-matrix-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_top10_feature_gap_matrix.md
```

This matrix is a strategy and blocker artifact only. It keeps all feature
ratings tied to current evidence statuses and keeps
`himalayan_accuracy_claim_allowed=false`.

That command also writes `partner_field_dictionary.json`,
`partner_field_dictionary.md`, `partner_intake_checklist.json`,
`partner_intake_checklist.md`, `partner_sample_row_pack.json`,
`partner_sample_row_pack.md`, `partner_submission_quality_score.json`,
`partner_submission_quality_score.md`,
`partner_submission_acceptance_checklist.json`,
`partner_submission_acceptance_checklist.md`, `partner_handoff_readme.json`,
`partner_handoff_readme.md`, `partner_submission_manifest_diff.json`,
`partner_submission_manifest_diff.md`,
`himalayan_top10_feature_gap_matrix.json`,
`himalayan_top10_feature_gap_matrix.md`,
`partner_intake_dry_run_runbook.json`,
`partner_intake_dry_run_runbook.md`,
`partner_incoming_triage_runbook.json`,
`partner_incoming_triage_runbook.md`,
`himalayan_local_holdout_protocol.json`,
`himalayan_local_holdout_protocol.md`,
`himalayan_local_holdout_leakage_audit.json`,
`himalayan_local_holdout_leakage_audit.md`,
`himalayan_local_holdout_prediction_template.json`,
`himalayan_local_holdout_prediction_template.md`,
`himalayan_local_holdout_predictions.csv`,
`himalayan_local_holdout_metric_report.json`,
`himalayan_local_holdout_metric_report.md`,
`release_gate_attestation_template_pack.json`,
`release_gate_attestation_template_pack.md`,
`partner_source_package_checksum_guide.json`,
`partner_source_package_checksum_guide.md`,
`partner_synthetic_validation_report.json`,
`partner_synthetic_validation_report.md`, `partner_package_index.json`, and
`partner_package_index.md` beside the CSV templates. The handoff README is the
first file partners should open: it lists what to read first, what not to claim,
and the exact resubmission command. The field dictionary defines field meanings,
units, expected formats, controlled values, and the danger-scale mapping caveat.
The sample row pack gives partners example-only rows for every CSV without
writing submit-ready CSV files; the examples contain placeholders and
`EXAMPLE_ONLY_REPLACE_WITH_REVIEWED` status so they cannot be treated as
validated evidence. The checklist lists the required source manifest, the ten
evidence CSVs, validation outputs, review freshness rules, allowed license
scopes, and the claim boundary. The submission quality score grades package
completeness, source governance, row sufficiency, coverage, review and license
controls, and release-gate readiness; it is not model accuracy. The acceptance
checklist translates scorecard failures into partner-side fixes and separates
scientist-review readiness from claim-review readiness. The package index is
the full artifact map: it links the handoff README, field dictionary, sample row
pack, checklist, file preflight, source-manifest starter, source-manifest
validation, evidence validation, submission quality score, acceptance
checklist, manifest diff, submission review ledger, submission summary, and
readiness contract in the intended command order. The manifest diff records
file presence, SHA-256, sizes, row counts, schema versions, and changes versus
a previous snapshot; it is provenance/change tracking only. The submission
review ledger records each package attempt, fingerprint, score, blocker,
review-routing state, and resubmission action over time; it is governance
traceability only, not prediction evidence. The submission status dashboard
summarizes the latest blocker, score, top-10 readiness, release gates, source
artifacts, and next actions for operator/scientist review; it is a status export
only, not a UI or prediction claim. The local holdout protocol pre-registers
the independent Himalayan holdout split rules, leakage checks, metrics,
acceptance floors, and required report outputs before any model run or claim
review. It is a protocol only, not a completed holdout result. The local
holdout leakage audit checks `independent_himalayan_holdout.csv`, holdout
`source_refs`, source-manifest coverage, and source-ref overlap with
non-holdout evidence before metric evaluation. It is a leakage/governance check,
not a model-performance result. The intake dry-run runbook gives operators a
single command sequence, expected decisions, and stop/continue rules for a real
submitted package. The release-gate attestation template pack gives reviewers
the exact structured fields needed later for holdout, scientist-review, license,
and promotion gates. The checksum guide explains how partners
freeze raw source packages, compute SHA-256 digests, fill `source_ref`, and
mirror those references in `partner_source_manifest.json`. The synthetic
validation report is a deterministic smoke test for the validation chain only;
its package is generated under `partner_synthetic_validation_package/` and must
not be submitted or cited as evidence. These templates, dictionaries, samples,
scorecards, checklists, READMEs, diffs, guides, synthetic fixtures, and indexes
are input contracts only. They do not make any Himalayan accuracy claim true
until reviewed local data is supplied, validated, and all release gates pass.

You can also write the intake checklist directly:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-intake-checklist-output backend/artifacts/reproduction/himalayan_accuracy/partner_intake_checklist.json \
  --partner-intake-checklist-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_intake_checklist.md
```

You can write the field dictionary directly when partners need data-entry
guidance without regenerating the full template packet:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-field-dictionary-output backend/artifacts/reproduction/himalayan_accuracy/partner_field_dictionary.json \
  --partner-field-dictionary-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_field_dictionary.md
```

You can write the compact handoff README directly when partners need a
first-read guide:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-intake-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --partner-evidence-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --partner-handoff-readme-output backend/artifacts/reproduction/himalayan_accuracy/partner_handoff_readme.json \
  --partner-handoff-readme-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_handoff_readme.md
```

You can write the sample row pack directly when partners need examples without
generating submit-ready CSV rows:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-sample-row-pack-output backend/artifacts/reproduction/himalayan_accuracy/partner_sample_row_pack.json \
  --partner-sample-row-pack-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_sample_row_pack.md
```

You can write the submission quality score directly after preflight and
validation. The score is a data-package readiness rubric, not a prediction
metric:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-intake-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --partner-evidence-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --partner-source-manifest backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest.json \
  --partner-submission-quality-score-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.json \
  --partner-submission-quality-score-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.md
```

You can write the acceptance checklist directly after quality scoring. This
checklist tells partners exactly what to fix before scientist review or claim
review:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-intake-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --partner-evidence-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --partner-source-manifest backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest.json \
  --partner-submission-acceptance-checklist-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.json \
  --partner-submission-acceptance-checklist-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.md
```

You can write a manifest diff directly to compare a resubmitted package against
the previous snapshot. Omit `--partner-submission-manifest-diff-previous` to
create the first baseline:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-intake-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --partner-submission-manifest-diff-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_manifest_diff.json \
  --partner-submission-manifest-diff-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_manifest_diff.md \
  --partner-submission-manifest-diff-previous backend/artifacts/reproduction/himalayan_accuracy/previous_partner_submission_manifest_diff.json
```

You can write the submission review ledger directly to track each attempted
package or resubmission across time. Supply `--partner-submission-review-ledger-previous`
when appending to an existing ledger:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-intake-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --partner-evidence-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --partner-submission-review-ledger-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_review_ledger.json \
  --partner-submission-review-ledger-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_review_ledger.md
```

You can write the one-page status dashboard directly when operators or
scientists need the current blocker, score, top-10 readiness, release gates, and
next actions without opening every artifact:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-intake-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --partner-evidence-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --partner-submission-status-dashboard-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_status_dashboard.json \
  --partner-submission-status-dashboard-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_status_dashboard.md
```

You can write the partner package index directly when building a standalone
handoff packet:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-package-index-output backend/artifacts/reproduction/himalayan_accuracy/partner_package_index.json \
  --partner-package-index-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_package_index.md
```

You can write the incoming-package triage runbook before real partner evidence
arrives. This is the operator sequence to run when the package lands next week:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-incoming-triage-runbook-output backend/artifacts/reproduction/himalayan_accuracy/partner_incoming_triage_runbook.json \
  --partner-incoming-triage-runbook-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_incoming_triage_runbook.md
```

The triage runbook lists the exact preflight, source-manifest, evidence,
leakage-audit, prediction-template, metric-report, ledger, and dashboard
commands. It is procedure only and does not supply evidence or unlock claims.

You can write the pre-registered local holdout protocol directly before
running any Himalayan model evaluation:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --local-holdout-protocol-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_protocol.json \
  --local-holdout-protocol-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_protocol.md
```

This protocol fixes the independent-holdout requirement, leakage controls,
macro-F1, high-danger recall, Brier, ECE, day/region accuracy floors, and
required report outputs. It remains non-evidence until real partner holdout rows
are validated and evaluated.

You can write the local holdout leakage audit directly once a partner package
contains `independent_himalayan_holdout.csv`:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-evidence-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --local-holdout-leakage-audit-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_leakage_audit.json \
  --local-holdout-leakage-audit-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_leakage_audit.md
```

The audit must pass before any local holdout metric report can support a
release-gate attestation. Passing the audit still does not authorize production
scoring.

Write the local holdout prediction template before any model-output exchange.
It produces a header-only `himalayan_local_holdout_predictions.csv` plus
JSON/Markdown rules for reviewed truth labels, predicted four-class danger
levels, and class probabilities:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --local-holdout-prediction-template-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_prediction_template.json \
  --local-holdout-prediction-template-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_prediction_template.md \
  --local-holdout-prediction-template-csv backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_predictions.csv
```

The prediction template is not model output and is not accuracy evidence. It
exists so that a future filled predictions CSV can be checked deterministically
by the metric report.

You can also write the local holdout metric report gate. It refuses to compute
metrics unless the leakage audit passes first, then expects
`himalayan_local_holdout_predictions.csv` with reviewed truth labels, predicted
four-class danger levels, and class probabilities:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-evidence-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --local-holdout-metric-report-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_metric_report.json \
  --local-holdout-metric-report-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_metric_report.md
```

The metric report is the first executable bridge from partner evidence to
measured Himalayan holdout performance. It still keeps
`production_scoring_allowed=false` and `himalayan_accuracy_claim_allowed=false`
until leakage, all metric floors, release-gate attestation, and separate
promotion review pass.

You can write the checksum guide directly when partners need source-package
hashing instructions before filling `source_ref` values:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-source-package-checksum-guide-output backend/artifacts/reproduction/himalayan_accuracy/partner_source_package_checksum_guide.json \
  --partner-source-package-checksum-guide-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_source_package_checksum_guide.md
```

You can write a synthetic-only validation package to smoke-test the full
validator before real partner evidence arrives:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-synthetic-validation-package-root backend/artifacts/reproduction/himalayan_accuracy/partner_synthetic_validation_package \
  --partner-synthetic-validation-report-output backend/artifacts/reproduction/himalayan_accuracy/partner_synthetic_validation_report.json \
  --partner-synthetic-validation-report-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_synthetic_validation_report.md
```

That fixture is deliberately marked `SYNTHETIC_VALIDATION_ONLY_NOT_PARTNER_EVIDENCE`;
it can prove the validator plumbing but cannot unlock scientist review, release
gates, production scoring, or a Himalayan accuracy claim.

You can write the real-package intake dry-run runbook directly:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-intake-dry-run-runbook-output backend/artifacts/reproduction/himalayan_accuracy/partner_intake_dry_run_runbook.json \
  --partner-intake-dry-run-runbook-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_intake_dry_run_runbook.md
```

This runbook is the operator procedure for `preflight -> source manifest ->
evidence validation -> score/checklist/summary -> manifest diff`. It is not a
model result and keeps both claim gates false.

You can write the release-gate attestation template pack directly:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --release-gate-attestation-template-pack-output backend/artifacts/reproduction/himalayan_accuracy/release_gate_attestation_template_pack.json \
  --release-gate-attestation-template-pack-markdown backend/artifacts/reproduction/himalayan_accuracy/release_gate_attestation_template_pack.md
```

This pack is blank governance scaffolding only. It must not be treated as a
completed release gate until reviewers fill named approvers, evidence digests,
acceptance floors, measured results, and reviewed timestamps.

Before parsing row contents, run a file-presence preflight over a submitted
partner package:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-intake-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --partner-intake-preflight-output backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.json \
  --partner-intake-preflight-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.md
```

The preflight only checks for `partner_source_manifest.json` and the ten
evidence CSVs. It reports `blocked_missing_partner_intake_files` until every
required package file exists, and it still keeps
`himalayan_accuracy_claim_allowed=false` and `production_scoring_allowed=false`.

For a concise handoff, generate a combined submission summary after preflight,
source-manifest validation, and evidence validation:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-intake-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --partner-evidence-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --partner-source-manifest backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest.json \
  --partner-submission-summary-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.json \
  --partner-submission-summary-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.md
```

The summary does not replace the detailed reports; it records each stage
decision and the first blocker so partner follow-up can focus on the next
missing evidence item.

After partners/scientists fill the CSVs, validate the evidence root with:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --output-markdown backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.md \
  --partner-evidence-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --partner-evidence-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.json \
  --partner-evidence-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.md
```

Partners can also validate the governed source manifest before every evidence
CSV is complete:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-source-manifest backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest.json \
  --partner-source-manifest-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.json \
  --partner-source-manifest-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.md
```

If the source manifest is absent, the standalone report emits
`partner_source_manifest_not_supplied`, keeps
`himalayan_accuracy_claim_allowed=false`, and keeps
`production_scoring_allowed=false`.

If the evidence CSVs already contain `source_ref` hashes but the manifest has
not been filled, generate a starter manifest:

```bash
python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract \
  --output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json \
  --partner-evidence-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates \
  --partner-source-manifest-starter-output backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_starter.json \
  --partner-source-manifest-starter-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_starter.md
```

The starter extracts unique SHA-256 values from `source_ref` fields and writes a
fillable `partner_source_manifest.json` shape, but every source is deliberately
`review_status=pending` with `license_scope=pending_license_review`. It must fail
source-manifest validation until a reviewer completes owner, dataset, date
range, license, review timestamp, and evidence-package fields.

The automated tests also include a synthetic complete-package harness that runs
the real CLI over all ten CSV templates plus a matching source manifest. That
harness is structural proof only: it verifies the intake and validation plumbing
can reach `all_partner_evidence_available`, but it still leaves
`himalayan_accuracy_claim_allowed=false` unless real release-gate attestations
are supplied.

The validator derives `available` only from CSV files that exist, contain every
required column, meet the minimum reviewed-row floor for that evidence group,
meet basic distinct-coverage floors such as station/case/scene diversity, have
enough temporal or elevation/slope span where those fields exist, have
`review_status=reviewed`, and pass field-level sanity checks for coordinates,
elevation, slope, danger levels, confidence/stability values, ISO-8601
timestamps, aspect, and holdout split labels. Blank templates, pending rows,
undersized, duplicated, temporally compressed, spatially narrow, or implausible
evidence files stay `partner_required`.

Semantic fields such as `avalanche_problem`, `terrain_class`, `quality_flag`,
`label_quality`, `label_source`, `avalanche_regime`, `forecast_cycle`,
`model_error_type`, `verdict`, `observed_outcome`, and `preprocessing_level`
must use controlled values. Free-text labels stay blocked until they are mapped
to the reviewed vocabulary.
The danger-label template preserves both `danger_level_1_to_5` and
`danger_level_1_to_4`: the five-level field keeps the canonical partner or
operational danger scale, while the four-level field is only the current
RF4-compatible research label. If a partner supplies level 5, the row should not
be silently collapsed; the mapping needs reviewer notes and a later model/design
decision before any claim.

The v3 danger-label and independent-holdout templates require a
`D_tidy`-equivalent provenance bundle: `label_source`,
`tidy_label_review_basis`, `nowcast_evidence_ref`, `observer_evidence_ref`,
`avalanche_regime`, `forecast_cycle`, `forecast_issue_time`, `valid_at`,
`window_center_local_time`, `aggregation_window_hours`,
`critical_elevation_m`, and `aspect_policy`. Public DGRE/DRDO-style bulletins
remain useful source material, but they do not become quality-controlled
training truth without a partner-reviewed nowcast, observer/event, or
reanalysis basis.

`license_scope` is also controlled. Evidence can support the research-readiness
contract only when the scope explicitly supports research validation, such as
`internal_research_validation`, `research_validation_only`,
`partner_restricted_research`, `cc_by_nc_research_only`, or
`commercial_deployment_approved`. Presentation-only, pending, blocked, unknown,
or external-imagery-only scopes remain blocked for Himalayan accuracy evidence.

Current generated artifacts use `himalayan_accuracy_readiness_contract_v3`,
`himalayan_accuracy_partner_evidence_templates_v3`, and
`himalayan_accuracy_partner_evidence_validation_v3` with
`validation_policy_version=himalayan_partner_evidence_policy_v3_tidy_label_gpxyz_density_refined_discretization`.
Older v1 and v2 artifacts are deprecated and must not be used as current
readiness proof.

Every partner evidence row now requires an ISO-8601 `reviewed_at` timestamp.
Evidence older than 365 days at contract-generation time is blocked as stale,
and evidence dated more than one day in the future is blocked as invalid. This
prevents copied legacy CSV rows from becoming current Himalayan accuracy proof.
Every `source_ref` must also carry a SHA-256 digest. `sha256:<64-hex>` refs are
accepted as externally retained source-package fingerprints, and
`file:<relative-path>#sha256=<64-hex>` refs are verified against local files
inside the partner evidence root. Missing files, path traversal, or digest
mismatches keep the evidence group blocked.
Every source hash must also be present in a partner source manifest with
`source_owner`, `dataset_name`, `license_scope`, `date_range`, `review_status`,
`reviewer_id`, `reviewed_at`, and `evidence_package_ref`. The manifest blocks
unreviewed, stale, duplicate, unlicensed, or undocumented source packages before
they can support a Himalayan accuracy claim.
The template command now writes `partner_source_manifest_template.json` and
`partner_source_manifest_template.md` beside the evidence CSV templates so
partners can fill the governed source manifest before submitting data.

It may move to `ready_for_himalayan_accuracy_claim_review` only when every
required evidence group is available or explicitly not applicable **and** all
release gates pass. Even then, production scoring remains a separate explicit
promotion decision.

Any `not_applicable` override must be backed by a waiver JSON object supplied
with `--not-applicable-waivers`. Each waived requirement needs `approved_by`,
`reason`, `evidence_ref`, and ISO-8601 `reviewed_at`; otherwise the readiness
builder fails closed.
Waiver `reviewed_at` must be no more than 365 days old and cannot be future
dated beyond the one-day skew allowance. The `evidence_ref` must be
SHA-256-qualified.

Every completed release gate must also have a release-gate attestation supplied
with `--release-gate-attestations`. Each gate attestation needs `approved_by`,
`summary`, `evidence_ref`, ISO-8601 `reviewed_at`,
`evidence_schema_version=himalayan_accuracy_partner_evidence_validation_v3`,
`validation_policy_version=himalayan_partner_evidence_policy_v3_tidy_label_gpxyz_density_refined_discretization`,
`acceptance_floors_ref`, and a structured `acceptance_floors` object. This
prevents booleans such as `local_himalayan_holdout_passed=true` from becoming
claim evidence without a current validation artifact and explicit acceptance
floors.

Release-gate attestations have a stricter freshness window: `reviewed_at` must
be no more than 180 days old, with the same one-day future skew allowance.
Their `evidence_ref` values must also be SHA-256-qualified so a human approval
note cannot be substituted for a stable evidence artifact. The
`acceptance_floors_ref` must be SHA-256-qualified for the same reason.

For `local_himalayan_holdout_passed`, the structured floors must include
`macro_f1_min`, `high_danger_recall_min`, `brier_score_max`, `ece_max`,
`mean_day_accuracy_min`, `region_accuracy_min`, `leakage_check_required=true`,
and `independent_holdout_required=true`. Other release gates must carry
gate-specific review, license, rollback, monitoring, and human-override floors.
Every true gate must also include `measured_results` with the same metric keys:
minimum-style metrics must meet or exceed the floor, maximum-style metrics such
as Brier/ECE or unresolved issue counts must be at or below the floor, and
required governance checks must be `true`.
