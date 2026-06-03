# MVP V2 — Action List (Flat, Machine-Checkable)

Status: 2026-05-24 final-stage handout. Companion to `MVP_V2_13_Week_Pilot_Plan.md`.
Roles: PL = Product Lead, SL = Scientist Lead, PR = Partner Liaison, ML = ML/Data Engineer, GS = Geospatial/SAR Reviewer, HA = Holdout Auditor, OP = Operator.
Status legend: `pending`, `in_progress`, `blocked`, `done`, `dropped`.

---

## A. Pre-Pilot Actions (Before Week 1)

| ID | Action | Owner | Depends on | Acceptance criterion | Status |
|---|---|---|---|---|---|
| A1 | Send `Scientist_Handout_OnePager.md` + cover note to SASE/DGRE | PL | None | Email logged in `docs/Cust_comm.md` | pending |
| A2 | Confirm scientist availability for Mon 10:00 IST / Wed 16:00 IST / Fri 17:00 IST cadence | PR | A1 | Calendar holds accepted by SL | pending |
| A3 | Confirm scientist signature authority on protocols and attestations | PL | A1 | Authority statement filed | pending |
| A4 | Re-confirm `production_scoring_allowed=false` and `himalayan_accuracy_claim_allowed=false` in the pilot contract | PL | None | One-sentence acknowledgement from partner | pending |
| A5 | Archive Codex's verified MVP V2 deck refresh (15 slides × 5 decks, 2026-05-24 QA pass) | PL | None | `QA_SUMMARY.md` referenced in cover note | done |

## B. Week 1 — Partner Handoff Session

| ID | Action | Owner | Depends on | Acceptance criterion | Status |
|---|---|---|---|---|---|
| B1 | Walk through `partner_handoff_readme.md` and `partner_field_dictionary.md` with SASE/DGRE | PL | A1, A2 | Minutes filed | pending |
| B2 | Walk through `partner_source_package_checksum_guide.md` | OP | B1 | Partner confirms checksum workflow understood | pending |
| B3 | Hand over 10 blank v3 evidence CSV templates + `partner_source_manifest_template.{json,md}` | PR | B1 | Partner has the files | pending |
| B4 | Scientist Lead nominates 3 priority regions + 1 priority avalanche-problem class | SL | A2 | Nomination recorded | pending |
| B5 | Capture partner liaison signature on `partner_intake_checklist.md` acknowledgement | PR | B1 | Signed copy stored | pending |

## C. Week 2 — Source-Manifest Bootstrapping

| ID | Action | Owner | Depends on | Acceptance criterion | Status |
|---|---|---|---|---|---|
| C1 | Record screen-share walkthrough of SHA-256 + `sha256:<64-hex>` + `file:<path>#sha256=<digest>` formats | OP | B2 | ≤15 min recording stored | pending |
| C2 | Partner submits ≥1 filled `partner_source_manifest` entry | PR | B3 | Source-manifest validation pass | pending |
| C3 | Rehearse `partner_intake_dry_run_runbook.md` against the synthetic fixture only | OP | C1 | Runbook completes; output marked `SYNTHETIC_VALIDATION_ONLY_NOT_PARTNER_EVIDENCE` | pending |
| C4 | Block any submission with `license_scope ∈ {pending, presentation_only, external_imagery_only, unknown}` | ML | C2 | License-blocker entries logged | pending |
| C5 | Verify every submitted source entry has `reviewed_at ≤ 365 days` | HA | C2 | Freshness check pass | pending |

## D. Week 3 — Station Metadata + GPxyz Readiness

| ID | Action | Owner | Depends on | Acceptance criterion | Status |
|---|---|---|---|---|---|
| D1 | Partner fills `station_metadata.csv` for ≥80% of AWS stations in 3 priority regions | PR | B4, C2 | Row count + coverage report | pending |
| D2 | Regenerate `gpxyz_readiness_report.json` | ML | D1 | Report emitted | pending |
| D3 | Confirm `station_count`, `region_count`, `elevation_span_m` figures with SL | SL | D2 | SL sign-off note | pending |
| D4 | Produce one station-density PNG per priority region | GS | D2 | 3 PNGs stored | pending |
| D5 | If <40% coverage in any region, mark that region `interpolation_sparse` | GS | D3 | Flag recorded | pending |

## E. Week 4 — `D_tidy` Labels And Weak-Layer Slices

| ID | Action | Owner | Depends on | Acceptance criterion | Status |
|---|---|---|---|---|---|
| E1 | Partner submits ≥30 `D_tidy`-class label rows with all 12 required provenance fields | PR | B3, B4 | Row count + completeness report | pending |
| E2 | Validate label provenance: `label_source`, `tidy_label_review_basis`, `nowcast_evidence_ref`, `observer_evidence_ref`, `avalanche_regime`, `forecast_cycle`, `forecast_issue_time`, `valid_at`, `window_center_local_time`, `aggregation_window_hours`, `critical_elevation_m`, `aspect_policy` | ML | E1 | Validator pass for ≥80% rows | pending |
| E3 | Scientist authors `weak_layer_slice_definitions.md` (persistent weak-layer epochs, depth bands, grain-type focus, instability thresholds) | SL | A3 | Doc signed | pending |
| E4 | SL marks at least one weak-layer slice as the Week 6 evaluation target | SL | E3 | Target flagged | pending |
| E5 | Inter-rater check if reviewer disagreement >25% on labels | SL | E2 | Inter-rater report | pending |

## F. Week 5 — Evidence Validation + Leakage Audit

| ID | Action | Owner | Depends on | Acceptance criterion | Status |
|---|---|---|---|---|---|
| F1 | Run `partner_intake_preflight` against the real partner submission | OP | C2, D1, E1 | Green | pending |
| F2 | Run `partner_source_manifest_validation` | ML | F1 | Pass | pending |
| F3 | Run `partner_evidence_validation` per evidence group | ML | F2 | Pass per group reported | pending |
| F4 | Compute `partner_submission_quality_score.json` (100-point rubric) | ML | F3 | Score ≥50 for ≥1 region | pending |
| F5 | Convert score failures into `partner_submission_acceptance_checklist` | PR | F4 | Checklist sent back to partner | pending |
| F6 | Run `himalayan_local_holdout_leakage_audit` on the proposed holdout split | HA | F3 | Green on ≥1 region | pending |
| F7 | Execute `partner_incoming_triage_runbook` on real partner data | OP | F1–F6 | Triage outputs stored under `backend/artifacts/reproduction/` | pending |

## G. Week 6 — Stage-1 Spike + SAR Read-Only Review

| ID | Action | Owner | Depends on | Acceptance criterion | Status |
|---|---|---|---|---|---|
| G1 | Author `himalayan_rf4_feasibility.md` (feature matrix, row counts, blockers) | ML | F3 | Doc signed by SL | pending |
| G2 | Run a pseudo-LOO spike **only if** total row count >200 | ML | G1 | Spike output stored, tagged `usage_boundary=research_only` | pending |
| G3 | SAR read-only review session (no promotion discussion) | GS + SL | A3 | Minutes filed | pending |
| G4 | Hard rule: zero SAR or Himalayan accuracy claim produced this week | PL | G3 | Compliance check | pending |

## H. Week 7 — Aggregation Parity + Refined-Discretization Audit

| ID | Action | Owner | Depends on | Acceptance criterion | Status |
|---|---|---|---|---|---|
| H1 | Produce `refined_discretization_audit.md` confirming thresholds came from training/OOB only | ML | None | Doc filed | pending |
| H2 | If partner data permits, station-row-baseline Himalayan aggregation pilot | ML | F3, D1 | Output tagged research-only | pending |
| H3 | Document band choice ({1200, 1600, 2000, 2400} vs partner-specified) with reasoning | SL + ML | E3 | Decision recorded | pending |
| H4 | HA cross-checks for cross-split leakage in refined discretization | HA | H1 | Leakage check green | pending |

## I. Week 8 — Weak-Layer Review Round 1

| ID | Action | Owner | Depends on | Acceptance criterion | Status |
|---|---|---|---|---|---|
| I1 | Compile ≥10 weak-layer cases with profile rows | ML + PR | E1, E3 | Pack assembled | pending |
| I2 | SL reviews case-by-case, attaching verdicts | SL | I1 | Each case has a verdict | pending |
| I3 | Produce `weak_layer_evidence_pack_round1.md` | SL + ML | I2 | Doc signed | pending |

## J. Week 9 — Pre-Register The Local Holdout Protocol

| ID | Action | Owner | Depends on | Acceptance criterion | Status |
|---|---|---|---|---|---|
| J1 | Draft `himalayan_local_holdout_protocol.{json,md}` (splits, leakage checks, metrics, acceptance floors) | HA | F6 | Draft filed | pending |
| J2 | SL co-signs the protocol | SL | J1 | Signature stored | pending |
| J3 | Capture SHA-256 of the signed protocol; mark immutable | OP | J2 | Hash stored | pending |
| J4 | Generate `himalayan_local_holdout_prediction_template.{json,md,csv}` (header-only CSV) | ML | J2 | Files stored | pending |

## K. Week 10 — Weak-Layer Round 2 + Spike Iteration

| ID | Action | Owner | Depends on | Acceptance criterion | Status |
|---|---|---|---|---|---|
| K1 | Compile net-new weak-layer cases + revisions | SL + PR | I3 | Pack assembled | pending |
| K2 | Produce `weak_layer_evidence_pack_round2.md` | SL | K1 | Doc filed | pending |
| K3 | Re-run Stage-1 spike if more rows arrived | ML | G2 | Round-2 spike output stored | pending |
| K4 | Confirm `partner_submission_quality_score ≥ 70` for ≥1 region | ML | F4 | Score check | pending |

## L. Week 11 — Failure-Mode Review + Pre-Decision Memo

| ID | Action | Owner | Depends on | Acceptance criterion | Status |
|---|---|---|---|---|---|
| L1 | Produce `pilot_failure_mode_review.md` (false alarms, missed high-danger days, weak-layer misses, calibration drift, station blind spots) | SL + ML | K2, K3 | Doc filed | pending |
| L2 | SAR re-check session (verdict on whether SAR qualification can begin in Phase 2) | GS + SL | G3 | Verdict filed; still no promotion | pending |
| L3 | Produce `pilot_pre_decision_memo.md` (≤1 page, decision options for Week 13) | SL + PL | L1, L2 | Memo signed | pending |

## M. Week 12 — Attestation Or Block

| ID | Action | Owner | Depends on | Acceptance criterion | Status |
|---|---|---|---|---|---|
| M1 | If a metric report exists with passing floors, fill `release_gate_attestation.{json,md}` (named approver, evidence digest, acceptance floors, measured results, `reviewed_at` within 180 days, SHA-256-qualified `evidence_ref` and `acceptance_floors_ref`) | SL | L3 | Attestation file stored | pending |
| M2 | If any floor fails, file a `claim_review_blocked` entry in `partner_submission_review_ledger.json` with next-action list | PL | L3 | Ledger entry stored | pending |
| M3 | Update `partner_submission_status_dashboard.md` for customer-facing readout | PL | M1 or M2 | Dashboard refreshed | pending |
| M4 | Hard rule: refuse any pressure to soften Week-9 floors | SL + PL | J3 | Compliance check | pending |

## N. Week 13 — Decision Session

| ID | Action | Owner | Depends on | Acceptance criterion | Status |
|---|---|---|---|---|---|
| N1 | 60-minute decision session with SASE/DGRE | PL + SL | M3 | Minutes in `docs/Cust_comm.md` | pending |
| N2 | If continuing, produce `Phase_2_Scoping.md` (regions, slices, acceptance floors, cadence, budget alignment) | PL | N1 | Doc signed | pending |
| N3 | If narrowing, produce `Narrow_Pilot_Charter.md` | PL + SL | N1 | Doc signed | pending |
| N4 | If terminating, produce `Pilot_Termination_Memo.md` documenting what was learned | PL + SL | N1 | Doc signed | pending |
| N5 | Update `model_status` only if a release gate passed; otherwise leave untouched | OP | M1 | Compliance check | pending |

---

## Cross-Cutting Standing Actions

| ID | Action | Owner | Cadence | Acceptance criterion |
|---|---|---|---|---|
| X1 | File `MVP_V2_Weekly_Progress_Template.md` instance every Friday | PL | weekly | Note exists with all sections filled |
| X2 | Honor scientist `extend/narrow/block/terminate` decision in writing within the same week | PL | as triggered | Written acknowledgement |
| X3 | Map every weekly statement to one of `Hosted production`, `Repo/admin verified`, `Artifact/doc proof only`, `Candidate/gated`, `Research-only` | PL | weekly | Tags present in note |
| X4 | Refuse to send synthetic fixtures as evidence | PR + ML | continuous | Compliance |
| X5 | Refuse to claim Himalayan accuracy before Week-12 attestation passes | PL | continuous | Compliance |
| X6 | Refuse to weaken Week-9 protocol floors | HA + SL | continuous | Compliance |
| X7 | Open `evidence_request` actions in scientist queue with ≤2 working-day SLA | OP | as triggered | SLA met |

---

## Hard Constraints (Same In Every Week)

- No production-scoring authorization.
- No Himalayan accuracy claim.
- No SAR promotion.
- No `D_tidy` substitution by raw bulletins.
- No use of synthetic fixtures as evidence.
- No post-hoc weakening of acceptance floors.
- No silent failures — Week-12 is either attestation **or** explicit block with next-actions.
