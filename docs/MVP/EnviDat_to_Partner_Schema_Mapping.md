# EnviDat To Himalayan Partner Schema Mapping

Status: updated from real RF1/RF2 download and Stage-1/3 reproduction checkpoint

## Purpose

The Swiss EnviDat / RAvaFcast workflow relies on station-day rows combining
weather observations, simulated SNOWPACK profile variables, and danger-level
labels. This document translates that expectation into a Himalayan partner data
request without implying that Swiss-trained models are valid for Himalayan
operations.

## Mapping Table

| Swiss / EnviDat Concept | Expected Partner Equivalent | Required For | Current Repo Support | Gap |
|---|---|---|---|---|
| AWS station id | `station_id` or `site_id` | Stage-1 RF and station evaluation | Partner adapter requires stable station id | Need real partner feed |
| Station date | `observed_at` or forecast valid date | Winter grouped split and daily forecasts | Partner adapter requires timestamp | Need timezone convention |
| Latitude / longitude | WGS84 `latitude`, `longitude` | Stage-2 interpolation | Partner adapter supports coordinates | Need QA and CRS confirmation |
| Elevation | `elevation_m` | Stage-2 GPxyz and elevation bands | Partner adapter supports elevation | Need station metadata |
| 24h weather summaries | temperature, precipitation, snowfall, wind, snow depth | RF features | Open-Meteo proxy exists | Need partner station observations |
| SNOWPACK profile features | layer depth, grain type, hardness, stability index, density | RF features and weak-layer validation | Adapter exists; current code uses only proxy scalars | Need SNOWPACK/HIM-STRAT output or field profiles |
| `D_forecast` | official/human danger level before quality control | RF1 comparison | Daily verification can store scientist/model danger | Need bulletin archive |
| `D_tidy` | quality-controlled danger level with nowcast/observer/reanalysis basis | RF2 primary target | Scientist review workflow exists and schema now requires label provenance | Need reviewed local nowcast/event corroboration |
| Warning regions | forecast-zone polygons | Stage-3 aggregation | Current regions are app regions, not official Himalayan warning regions | Need partner-defined regions |
| Elevation thresholds and refined class boundaries | critical elevation bands plus training/OOB-derived refined discretization thresholds | Stage-3 aggregation | Swiss research helper exists; production rounding unchanged | Need Himalayan band policy and leakage-safe threshold training evidence |

## Real EnviDat Column Findings

The downloaded Swiss RF1/RF2 CSVs expose the following practical column names:

| Need | Real EnviDat Column | Current Use |
|---|---|---|
| Station id | `station_code` | Stage-1 split/evaluation and future station metadata join |
| Date | `datum` | Winter-season grouping and daily aggregation |
| Warning region id | `warnreg` | Stage-3 station-row aggregation baseline |
| Station elevation | `elevation_station` | Stage-1 feature and elevation-band grouping |
| Station coordinate worksheet | `station_metadata_template.csv` generated from RF2 station ids | Partner/reviewer must fill `latitude` and `longitude` before GPxyz |
| Danger target | `dangerLevel` | Primary 4-class target in the downloaded RF1/RF2 files |
| Weak-layer / snow profile features | `pwl_100`, `sn38_pwl`, `sk38_pwl_100`, `Pen_depth`, `min_ccl_pen`, and related columns | Stage-1 RF4 features |

The RF1/RF2 files do **not** include station latitude or longitude. Full
RAvaFcast `GPxyz` reproduction therefore requires a station metadata table
before the 1 km interpolation grid can be generated.

## Gemini / PDF Delta: Label Quality, GPxyz, And Refined Discretization

The NHESS RF danger-level work separates raw forecast labels (`D_forecast`) from
quality-controlled labels (`D_tidy`). For the Himalayan partner contract, a
single danger-label column is therefore insufficient. The v3 templates require
`label_source`, `tidy_label_review_basis`, `nowcast_evidence_ref`,
`observer_evidence_ref`, `avalanche_regime`, `forecast_cycle`,
`forecast_issue_time`, `valid_at`, `window_center_local_time`,
`aggregation_window_hours`, `critical_elevation_m`, and `aspect_policy` on
danger labels and independent holdout rows. Public DGRE/DRDO-style bulletins
are useful inputs, but they are not `D_tidy`-grade training truth unless a
partner links them to reviewed nowcasts, observer reports, field/event records,
or an explicit scientific reanalysis basis.

The GMD RAvaFcast pipeline found that the simple `GPxyz` interpolation using
latitude, longitude, and elevation was strongest in that Swiss setting. The
Himalayan contract keeps `station_id`, `latitude`, `longitude`, and
`elevation_m` mandatory for station metadata, and now records station-count,
region-count, elevation-span, and sparse-coverage warnings. This is a GPxyz
readiness gate only; it does not assert that complex terrain features always
hurt, or that Himalayan terrain should ignore ATES/runout evidence.

RAvaFcast Stage 3 also uses refined discretization of expected danger instead
of simple rounding. The Swiss reproduction lane now includes a research-only
helper that computes monotonic thresholds from training or out-of-bag expected
danger distributions and true labels. Validation, test, holdout, or
client-final labels must not be used to learn those thresholds. The published
Swiss thresholds are retained as a reference fixture, not hard-coded Himalayan
operational truth.

For the Himalayan adaptation lane, partner data should be supplied through the
machine-readable evidence templates generated by
`build_himalayan_accuracy_readiness_contract --templates-output-root`. The
validator marks a requirement `available` only when its CSV is present,
schema-complete, reviewed, field-valid, and large enough to meet that evidence
group's minimum reviewed-row, distinct-coverage, and temporal/elevation span
floors. This prevents manual status overrides, duplicated rows, temporally
compressed samples, spatially narrow samples, or a single token case from being
mistaken for local Himalayan evidence.

The same validator also constrains operational label fields to controlled
vocabularies. Avalanche problems, terrain classes, review verdicts, quality
flags, observed outcomes, and remote-sensing preprocessing levels must be
mapped before they can support a Himalayan accuracy claim.

The `license_scope` field is controlled as well. Partner evidence may support
research validation only when the scope explicitly permits that use; scopes that
are pending, blocked, presentation-only, unknown, or only approved for external
imagery sharing do not unlock Himalayan accuracy evidence.

The current evidence contract is `himalayan_accuracy_readiness_contract_v3`.
Partner templates and validation outputs also use v3 schema names plus the
`himalayan_partner_evidence_policy_v3_tidy_label_gpxyz_density_refined_discretization`
policy marker. Any v1 or v2 generated artifact is deprecated and should be
regenerated before being used in a review packet.
The builder can also emit `himalayan_top10_feature_gap_matrix.json` and `.md`,
which keep the top-10 Himalayan prediction/detection feature roadmap tied to
the current evidence statuses. The matrix is strategic blocker tracking only;
it does not unlock production scoring or a Himalayan accuracy claim.

Each partner evidence row must carry an ISO-8601 `reviewed_at` timestamp. The
validation contract blocks rows older than 365 days at generation time and rows
dated more than one day in the future, so Himalayan partner evidence cannot be
treated as current unless it has a recent documented review.

Each `source_ref` must also be hash-qualified. Use `sha256:<64-hex>` for an
externally retained source package, or `file:<relative-path>#sha256=<64-hex>`
when the source package is stored beside the partner evidence root. Local file
references are resolved and hashed by the validator; missing files and digest
mismatches block the evidence group.

Hash-only references must be backed by the partner source manifest. Each source
manifest entry maps a SHA-256 digest to the source owner, dataset name, license
scope, date range, review status, reviewer, `reviewed_at`, and
`evidence_package_ref`. Unreviewed, stale, duplicate, unlicensed, or undocumented
source packages remain blocked.
The readiness-template command writes both `partner_source_manifest_template.json`
and `partner_source_manifest_template.md`; partners should complete that manifest
before their evidence CSVs are used for validation.
It also writes `partner_handoff_readme.json` and `.md`, the compact first-read
guide that tells partners which artifacts to open, what not to claim, and the
exact command sequence to run after resubmission.
It also writes `partner_field_dictionary.json` and `.md`, which define field
meanings, units, expected formats, controlled values, and the danger-scale
mapping caveat before partners start filling CSV rows.
It also writes `partner_sample_row_pack.json` and `.md`, which show one
example-only row per evidence CSV. Those examples are intentionally not
submit-ready: they keep placeholder SHA-256 references and
`EXAMPLE_ONLY_REPLACE_WITH_REVIEWED` status so they cannot be mistaken for
reviewed Himalayan evidence.
It also writes `partner_submission_quality_score.json` and `.md`, a 100-point
package-readiness rubric for file completeness, source governance, row
sufficiency, spatial/temporal/numeric coverage, review/license/source controls,
and release-gate readiness. This score is not a prediction metric and does not
unlock a Himalayan accuracy claim.
It also writes `partner_submission_acceptance_checklist.json` and `.md`, which
turn scorecard failures into partner-side acceptance criteria. The checklist
separates scientist-review readiness from claim-review readiness so a partial
package can be routed correctly without overclaiming.
It also writes `partner_submission_manifest_diff.json` and `.md`, which compare
required package files by presence, SHA-256, size, row count, schema version,
and prior-snapshot changes. The diff is provenance/change tracking only; it is
not row-level evidence validation.
It also writes `partner_intake_checklist.json` and `.md`, which define the full
submission package: source manifest, ten evidence CSVs, required validation
outputs, license scopes, review freshness rules, and the production-blocked
claim boundary.
It also writes `partner_intake_dry_run_runbook.json` and `.md`, the operator
procedure for running preflight, source-manifest validation, evidence
validation, score/checklist/summary, and manifest diff on a real submitted
package. The runbook is procedure only; it does not supply evidence or unlock
claims.
It also writes `partner_incoming_triage_runbook.json` and `.md`, which provide
the first-response command sequence for a real incoming partner package:
preflight, source-manifest validation, evidence validation, leakage audit,
prediction-template handoff, metric report, ledger, and dashboard. The triage
runbook is procedure only; it does not supply evidence or unlock claims.
It also writes `release_gate_attestation_template_pack.json` and `.md`, which
define the structured approval fields required after evidence acceptance:
named approver, evidence digest, acceptance floors, measured results,
reviewed timestamp, schema version, and validation policy version. The template
pack is not a completed release gate.
It also writes `partner_package_index.json` and `.md`, a one-file handoff map
for partners that links the handoff README, field dictionary, sample row pack,
checklist, intake preflight, source-manifest starter, source-manifest
validation, evidence validation, submission quality score, acceptance checklist,
manifest diff, submission review ledger, submission summary, and readiness
contract in the intended command order. The index is navigation only; it does
not supply evidence or unlock a Himalayan accuracy claim.
It also writes `partner_submission_review_ledger.json` and `.md`, which append
one record per package attempt or resubmission: package fingerprint, score,
first blocker, scientist-review readiness, claim-review readiness, and next
actions. The ledger is governance traceability only; it does not supply
evidence or unlock prediction claims.
It also writes `partner_submission_status_dashboard.json` and `.md`, a one-page
operator/scientist status export that combines the package index, review ledger,
quality score, acceptance checklist, top-10 feature matrix, release gates, and
next actions. The dashboard is not a public UI and does not supply evidence or
unlock prediction claims.
It also writes `himalayan_local_holdout_protocol.json` and `.md`, which
pre-register independent holdout split rules, leakage checks, metrics,
acceptance floors, and required report outputs before any Himalayan model
evaluation. The protocol is not a completed holdout result and does not unlock
prediction claims.
It also writes `himalayan_local_holdout_leakage_audit.json` and `.md`, which
check holdout rows, source-ref digest validity, partner source-manifest
coverage, and source-ref overlap with non-holdout evidence before any metric
evaluation. The audit is leakage governance only; it is not model-performance
evidence and does not unlock prediction claims.
It also writes `himalayan_local_holdout_prediction_template.json`, `.md`, and a
header-only `himalayan_local_holdout_predictions.csv`, which define the exact
model-output handoff required by the metric report. The template is not model
output and is not accuracy evidence.
It also writes `himalayan_local_holdout_metric_report.json` and `.md`, which
refuse to evaluate metrics until the leakage audit passes, then require a
`himalayan_local_holdout_predictions.csv` file with reviewed truth labels,
predicted four-class danger levels, and class probabilities. The metric report
can support a release-gate attestation only after all locked floors pass; it
still does not unlock production scoring.
It also writes `partner_source_package_checksum_guide.json` and `.md`, which
define the SHA-256 checksum workflow, stable `source_ref` formats, raw source
package layout, and required `partner_source_manifest.json` fields. The guide
is provenance instruction only; it does not make a source reviewed or unlock
prediction claims.
It can also write `partner_synthetic_validation_report.json` and `.md` plus a
`partner_synthetic_validation_package/` fixture. That fixture is deterministic
validator smoke-test material only, marked `SYNTHETIC_VALIDATION_ONLY_NOT_PARTNER_EVIDENCE`,
and must not be submitted as partner data or used for accuracy claims.
Danger labels now preserve both `danger_level_1_to_5` and
`danger_level_1_to_4`; the former keeps the reviewed partner/operational scale,
while the latter is only the current RF4-compatible research label.
The readiness builder can emit `partner_intake_preflight.json` / `.md` before
deep validation; that preflight only checks whether the source manifest and ten
CSV files are present, so partners can fix incomplete uploads before row-level
schema and evidence checks run.
It can also emit `partner_submission_summary.json` / `.md`, which combines
preflight, source-manifest validation, partner evidence validation, and the
release-gated readiness contract into one first-blocker handoff report.
The readiness builder can also emit a standalone
`partner_source_manifest_validation.json` / `.md` report so source package
ownership, license scope, freshness, reviewer, and evidence-package references
can be checked before all ten evidence CSVs are complete.
When CSVs already contain `source_ref` values but the source manifest is missing,
the builder can generate `partner_source_manifest_starter.json` / `.md` from the
observed SHA-256 digests. The starter is deliberately pending and invalid until
a reviewer fills owner, dataset, license, date-range, review, and evidence
package fields.

Release-gate attestations must also cite the current v3 partner-evidence
validation schema, the current validation policy marker, and an explicit
acceptance-floors reference plus structured floors. For the local Himalayan
holdout gate, those floors must include macro-F1, high-danger recall, Brier,
ECE, day/region accuracy, and leakage/independent-holdout requirements. A human
approval note by itself is not enough to turn Himalayan evidence into a
claim-review candidate. The attestation must also include measured results that
meet those floors, and the attestation `reviewed_at` timestamp must be no more
than 180 days old. Its `evidence_ref` and `acceptance_floors_ref` values must
also include SHA-256 digests. `not_applicable` waivers use the same
SHA-256-qualified `evidence_ref` requirement and must be no more than 365 days
old.

## Updated Partner Data Request

| Partner Dataset | Minimum Fields | Why It Is Needed | Current Status |
|---|---|---|---|
| Station metadata | `station_id`, `region_key`, `latitude`, `longitude`, `elevation_m`, active dates | Enables GPxyz, station density checks, elevation-span diagnostics, and station QA | Required next |
| Daily station weather summaries | 24h temperature, precipitation, snowfall, wind, snow depth, humidity/radiation where available | RF4 feature parity | Required for local adaptation |
| Snowpack / profile model output | weak-layer, penetration, stability, stratigraphy features, `profile_model`, `snowpack_model_version`, `profile_extracted_at_local_time`, `stability_metric_name` | Paper-parity feature contract and timing alignment | Required for meaningful model transfer |
| Quality-controlled danger labels | reviewed 1-4 and 1-5 danger levels plus `label_source`, `tidy_label_review_basis`, nowcast/observer refs, regime, issue/validity times, critical elevation, aspect policy | RF2-equivalent target and `D_tidy`-grade truth | Required before any local accuracy claim |
| Warning-region polygons | region id, polygon geometry, elevation policy | Stage-3 aggregation and UI display | Required for region forecast parity |
| Bulletin archive | forecast date, issued danger levels, elevation thresholds, avalanche problems, forecast cycle | Expert-vs-model comparison; not sufficient alone as `D_tidy` truth | Required for operational validation |

## Implementation Boundary

The Swiss reproduction lane should answer: "Can we reproduce the supplied
Swiss scientific workflow?" The Himalayan partner lane should answer: "Do we
have enough local station, snowpack, terrain, and danger-label evidence to make
that workflow meaningful operationally?"

Those are separate questions. Passing the Swiss reproduction gate does not
authorize Himalayan production scoring.

## Current Reproduction Evidence

| Stage | Evidence | Interpretation |
|---|---|---|
| Stage 1 RF4 | `rf4_result.json`: calibrated accuracy `0.8937`, macro-F1 `0.7508`, class-4 F1 `0.3636`; uncalibrated accuracy `0.9033` | Initial reproduction signal only; feature/parity audit shows sensitivity to feature-set assumptions. |
| Stage 1 feature audit | `rf4_feature_parity_audit.json`: auto/leakage-guarded accuracy `0.8924`; paper-candidate whitelist accuracy `0.8145` | Audit complete, but full paper parity still requires GP grid and official aggregation inputs. |
| Stage 2 GPxyz | `gpxyz_readiness_report.json`: `blocked_station_coordinates_required` | The module exists; the downloaded CSVs alone cannot support GP interpolation. |
| Stage 3 aggregation | `elev_simple_aggregation_result.json`: station-row baseline accuracy `0.8085`, macro-F1 `0.7848` | Useful baseline only; full RAvaFcast parity still needs GP grid and official polygons. |

## Additional Reproduction Evidence Required

| Evidence | Why It Is Required | Current Gate |
|---|---|---|
| RF4 feature/parity audit | Completed across auto numeric, paper-candidate whitelist, and leakage-guarded feature sets. | `initial_reproduction_signal_pending_parity_audit` remains because paper parity needs GP/aggregation parity too |
| Calibration report | GPxyz should consume calibrated expected-danger probabilities, not raw class probabilities without review. | calibration metrics required before GP handoff |
| Station metadata join | GPxyz needs reviewed `station_code`, `latitude`, `longitude`, and `elevation_m`. | `blocked_station_coordinates_required` until joined |
| Full aggregation inputs | RAvaFcast parity needs a 1 km GP grid and official warning-region polygons. | `blocked_full_aggregation_inputs_required` until supplied |
