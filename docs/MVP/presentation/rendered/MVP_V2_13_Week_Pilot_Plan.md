# MVP V2 — 13-Week Scientist-In-The-Loop Pilot Plan

Status: 2026-05-24 final-stage handout for SASE/DGRE scientist review
Owner roles: Product Lead (PL), Scientist Lead (SL), Partner Liaison (PR), ML/Data Engineer (ML), Geospatial/SAR Reviewer (GS), Holdout Auditor (HA), Operator (OP)
Pilot anchor: this 13-week pilot is the operational expansion of **Phase 1 (0–3 months) — Platform Hardening** described in Deck 3 slide D3-14. Phase 2 (3–9 months) and Phase 3 (9–18 months) sit downstream of this plan.

---

## Pilot Contract

- **Production scoring:** `production_scoring_allowed = false` throughout the pilot.
- **Himalayan accuracy claim:** `himalayan_accuracy_claim_allowed = false` until the local holdout protocol, leakage audit, metric report, and release-gate attestation all pass and a scientist co-signs.
- **Synthetic data:** synthetic rows are validator-fixture only (`SYNTHETIC_VALIDATION_ONLY_NOT_PARTNER_EVIDENCE`); they cannot be sent as evidence or be cited as accuracy.
- **Scientist authority:** at every weekly gate the Scientist Lead can `extend`, `narrow`, `block`, or `terminate` the pilot. The product team commits to honoring that decision in writing within the same calendar week.
- **Claim discipline:** every weekly status update maps each statement to one of `Hosted production`, `Repo/admin verified`, `Artifact/doc proof only`, `Candidate/gated`, or `Research-only`.

---

## Cross-Reference Map

| Deck reference | Plan section |
|---|---|
| D3-5 — Himalayan v3 partner handoff packet | Weeks 1, 2, 3 |
| D3-6 — Validation protocol v0 + V3 triage loop | Weeks 3, 4, 5, 7, 9 |
| D3-7 — Critical-layer / weak-layer program | Weeks 4, 6, 8, 10 |
| D3-9 — SAR qualification path | Week 6 (read-only) and Week 11 (review-only) |
| D3-10 — Pilot design (existing 4 timeline blocks) | This entire document |
| D3-14 — 3-phase timeline (Phase 1 = 0–3 months) | This entire document |
| D3-15 — Concrete ask / decision options | Week 13 |
| Schema doc | `docs/EnviDat_to_Partner_Schema_Mapping.md` |
| Co-working SLA | `docs/Scientist_Coworking_SLA.md` |
| Completion tracker | `docs/Scientist_Coworking_Completion_Tracker.md` |
| Open peer review | `docs/Open_Peer_Review.md` |

---

## Standing Cadence (every week of the pilot)

- **Mon 10:00 IST** — 30 min product/scientist sync: review Friday's progress note and rebalance the week.
- **Wed 16:00 IST** — 45 min technical working session: PR review of plans/artifacts touched that week.
- **Fri 17:00 IST** — Weekly progress note filed using `MVP_V2_Weekly_Progress_Template.md`. Locked into `docs/Scientist_Coworking_Completion_Tracker.md`.
- **Async on demand** — `evidence_request` actions opened in the scientist queue with ≤2 working-day acknowledgment SLA.

---

## Week 1 — Pilot Activation And Partner Handoff Session

- **Objective:** make the partner packet usable and lock the agreed-upon scope.
- **Inputs:** signed SASE/DGRE handoff acknowledgement; v3 evidence contract (`himalayan_accuracy_readiness_contract_v3`); current partner package index.
- **Deliverables:**
  - Partner handoff session held (≤90 min); minutes filed in `docs/Cust_comm.md`.
  - `partner_handoff_readme.md`, `partner_field_dictionary.md`, `partner_source_package_checksum_guide.md` walked through with the SASE/DGRE technical liaison.
  - One signed-back-by-partner copy of `partner_intake_checklist.md` showing acknowledgement of license/freshness rules.
  - Scientist Lead nominates **3 priority regions** and **1 priority avalanche-problem class** for the pilot.
- **Owners:** PL (session lead), PR (logistics), SL (region nomination).
- **Acceptance gate:** partner liaison has the README plus the 10 blank CSV templates and the checksum guide; minutes attached.
- **Risk triggers:**
  - Partner cannot attend → reschedule within the same week, otherwise activate **Contingency A** (Swiss-only sandbox week).
  - Scientist Lead cannot nominate priority regions → fall back to Lahaul–Spiti, Drass, and Nubra as default until Week 2 review.
- **Tier classification:** Tier 1.

---

## Week 2 — Source-Manifest Bootstrapping And Checksum Discipline

- **Objective:** make every partner row hash-traceable before any row arrives.
- **Inputs:** Week-1 priority regions; `partner_source_manifest_template.json` + `.md`.
- **Deliverables:**
  - Generated `partner_source_manifest_starter.json` for any partner-supplied checksum stubs.
  - SHA-256 reference walkthrough recorded as a screen-share (≤15 min) and stored in `docs/superpowers/`.
  - Partner returns at least one filled `partner_source_manifest` entry (owner, dataset, license scope, date range, reviewer, `reviewed_at`).
  - Operator runbook rehearsal of `partner_intake_dry_run_runbook.md` against the synthetic fixture **only**.
- **Owners:** PR (partner), OP (runbook rehearsal), ML (manifest tooling), SL (review).
- **Acceptance gate:** ≥1 manifest entry passes source-manifest validation with `license_scope ∈ {training_eligible, benchmark_only, research_only}` and `reviewed_at ≤ 365 days`.
- **Risk triggers:**
  - Partner license scope is `pending`, `presentation_only`, or `external_imagery_only` → block all evidence use of that source; escalate to partner legal.
  - Source manifest entry stale (>365 days) → block; request re-review.
- **Tier classification:** Tier 2.

---

## Week 3 — Station Metadata + GPxyz Readiness Gate

- **Objective:** unblock the Stage-2 GPxyz interpolation lane that is currently `blocked_station_coordinates_required`.
- **Inputs:** `station_metadata_template.csv` generated from RF2 station ids; partner station inventory.
- **Deliverables:**
  - Filled `station_metadata.csv` for ≥80% of partner-supplied AWS stations across the 3 priority regions, including `station_id`, `latitude`, `longitude`, `elevation_m`, `active_from`, `active_to`.
  - `gpxyz_readiness_report.json` regenerated showing `station_count`, `region_count`, `elevation_span_m`, and `sparse_coverage_warnings`.
  - Station-density diagnostic plot (1 PNG per region) reviewed in Wed working session.
- **Owners:** PR (partner station data), GS (geospatial QA), ML (regeneration), SL (sign-off).
- **Acceptance gate:** `gpxyz_readiness_report.json` exits `blocked_station_coordinates_required` for **at least one** priority region. If zero regions exit, treat this as Week-3 block and activate **Contingency B** (synthetic-pseudo-stations sandbox).
- **Risk triggers:**
  - <40% station coverage in any priority region → mark that region `interpolation_sparse` and exclude from Stage-2 outputs.
  - Coordinate CRS mismatch detected → quarantine rows; do not flip to "available."
- **Tier classification:** Tier 2.

---

## Week 4 — `D_tidy` Label Provenance And Weak-Layer Slice Definitions

- **Objective:** put quality-controlled labels in the loop, not raw bulletins; agree the weak-layer cases the scientist team cares about.
- **Inputs:** partner bulletin archive; scientist-curated nowcasts; observer reports; field/event records.
- **Deliverables:**
  - ≥30 `D_tidy`-class label rows submitted with `label_source`, `tidy_label_review_basis`, `nowcast_evidence_ref`, `observer_evidence_ref`, `avalanche_regime`, `forecast_cycle`, `forecast_issue_time`, `valid_at`, `window_center_local_time`, `aggregation_window_hours`, `critical_elevation_m`, `aspect_policy`.
  - First version of `weak_layer_slice_definitions.md` (scientist-authored, product-supported): persistent weak-layer epochs, depth bands, grain-type focus, instability-index thresholds.
  - Scientist review verdict on each row's label provenance recorded in the scientist queue.
- **Owners:** SL (label provenance + weak-layer slices), PR (partner submission), ML (intake validator), HA (label-row freshness checks).
- **Acceptance gate:** ≥80% of submitted rows pass label-provenance validation; ≥1 weak-layer slice is signed-off by the scientist as the Week 6 evaluation target.
- **Risk triggers:**
  - Partner can only supply raw bulletins → mark `D_tidy`-grade evidence as `not_yet_available`; do not promote bulletins into training-truth.
  - Reviewer disagreement >25% across submitted rows → run inter-rater check before continuing.
- **Tier classification:** Tier 2.

---

## Week 5 — Evidence Validation, Leakage Audit, And First Triage Run

- **Objective:** prove the partner pipeline produces a clean, leakage-free evidence ledger end-to-end.
- **Inputs:** filled CSVs (stations, weather, snowpack, labels, polygons, events) from Weeks 1–4; source manifest from Week 2.
- **Deliverables:**
  - `partner_intake_preflight.json` — green.
  - `partner_source_manifest_validation.json` — pass on the manifest entries delivered so far.
  - `partner_evidence_validation.json` for each evidence group.
  - `partner_submission_quality_score.json` (100-point rubric) ≥ **50/100** for at least one region.
  - `partner_submission_acceptance_checklist.json` translated into a numbered to-do list for the partner.
  - `himalayan_local_holdout_leakage_audit.json` — green on at least one region's holdout split.
  - Triage runbook executed by Operator using `partner_incoming_triage_runbook.md` against real partner data (not the synthetic fixture).
- **Owners:** OP (triage execution), ML (validators), HA (leakage audit), SL (review of audit).
- **Acceptance gate:** at least one priority region exits all three of: preflight green, source-manifest validation pass, evidence validation pass with score ≥50/100.
- **Risk triggers:**
  - Any leakage detected → automatic Week-5 block; do not move forward until source-overlap is resolved.
  - Score <50 across all regions → activate **Contingency C** (re-submission cycle; revisit Weeks 1–4 partner intake).
- **Tier classification:** Tier 2.

---

## Week 6 — Stage-1 RF4 Local Adaptation Spike And SAR Read-Only Review

- **Objective:** see whether a Stage-1 RF4 retraining on partner features is even feasible; review (not promote) SAR evidence.
- **Inputs:** validated partner rows from Week 5; existing `rf4_result.json` (Swiss reproduction; accuracy 0.8937 calibrated, macro-F1 0.7508, class-4 F1 0.3636 on Swiss data — **not** a Himalayan accuracy claim).
- **Deliverables:**
  - Feasibility note: `himalayan_rf4_feasibility.md` (1 page) — feature availability matrix, row-count sufficiency, class balance, blockers.
  - One pseudo-LOO experiment if and only if row count > 200; output written to `backend/artifacts/reproduction/himalayan_rf4_spike/` and tagged `usage_boundary = research_only`.
  - SAR read-only review session: scientist inspects current shadow artifacts; no promotion discussion.
- **Owners:** ML (spike), SL (feasibility verdict), GS (SAR read-only).
- **Acceptance gate:** feasibility note signed by SL; SAR review minutes filed; **no SAR or Himalayan accuracy claim produced**.
- **Risk triggers:**
  - Row count <200 → mark Stage-1 spike `deferred_to_week_10`; do not force a low-data spike.
  - SAR scientist concerns require labels we lack → log to research agenda, do not promote.
- **Tier classification:** Tier 2 (Tier 1 if no spike runs).

---

## Week 7 — Stage-3 Aggregation Parity And Refined Discretization Audit

- **Objective:** ensure that elevation-band aggregation and refined discretization thresholds were learned only from training/OOB distributions, not validation/test/holdout labels.
- **Inputs:** Swiss `elev_simple_aggregation_result.json` baseline (station-row accuracy 0.8085, macro-F1 0.7848); refined-discretization helper.
- **Deliverables:**
  - `refined_discretization_audit.md` — confirms thresholds were learned from training-only or OOB-only data; lists any cross-split contamination found.
  - If partner data permits, a station-row-baseline `himalayan_elev_simple_aggregation_pilot.json` (research-only; not Himalayan accuracy).
  - Reviewer sign-off on band choice ({1200, 1600, 2000, 2400} vs partner-specified alternatives).
- **Owners:** ML (audit), SL (band choice), HA (leakage check).
- **Acceptance gate:** audit passes for the Swiss reproduction; band policy for any Himalayan pilot output is explicitly noted as `partner-specified` or `swiss-default` with reasoning.
- **Risk triggers:**
  - Cross-split leakage in refined discretization → freeze the discretization helper to training/OOB-only and re-run the spike.
- **Tier classification:** Tier 2.

---

## Week 8 — Weak-Layer And Critical-Layer Review Round 1

- **Objective:** turn the Week 4 slice definitions into a reviewable evidence pack.
- **Inputs:** weak-layer slice definitions; partner SNOWPACK/profile rows (Pen_depth, ccl, Sn38, Sk38, SSI, PWL/PWL_100).
- **Deliverables:**
  - `weak_layer_evidence_pack_round1.md` — case-by-case review (≥10 cases), each with profile rows, partner-supplied verdict, and scientist verdict.
  - At least one weak-layer slice marked `scientist_signed_off`, `needs_more_data`, or `dropped` with reasoning.
- **Owners:** SL (case review lead), PR (partner submission of profile rows), ML (tooling support).
- **Acceptance gate:** ≥10 cases reviewed; ≥3 marked with a final verdict; minutes filed.
- **Risk triggers:**
  - Profile-feature columns missing or partial → mark cases `feature_incomplete`; do not synthesize replacements.
- **Tier classification:** Tier 2.

---

## Week 9 — Local Holdout Protocol And Pre-Registration

- **Objective:** lock the local holdout protocol **before** any metric is computed, to prevent post-hoc tuning.
- **Inputs:** validated partner rows; weak-layer slice verdicts; bulletin archive.
- **Deliverables:**
  - `himalayan_local_holdout_protocol.json` and `.md` — pre-registered: split rules, leakage checks, metrics (macro-F1, high-danger recall, Brier, ECE, day/region accuracy), acceptance floors, required report outputs.
  - Scientist co-signature on the protocol.
  - `himalayan_local_holdout_prediction_template.json/.md` plus header-only `himalayan_local_holdout_predictions.csv` ready for population.
- **Owners:** HA (protocol authoring), SL (co-signature), ML (template generation).
- **Acceptance gate:** protocol file SHA-256 captured; scientist signature stored alongside; protocol marked **immutable** for the rest of the pilot.
- **Risk triggers:**
  - Insufficient partner rows to support the protocol → keep the protocol but mark holdout `not_yet_runnable`; do not weaken floors to fit row count.
- **Tier classification:** Tier 2.

---

## Week 10 — Weak-Layer Review Round 2 And Spike Iteration

- **Objective:** close the loop on weak-layer cases and re-run the Week-6 spike if more rows arrived.
- **Inputs:** Round-1 verdicts; any new partner data since Week 6.
- **Deliverables:**
  - `weak_layer_evidence_pack_round2.md` — net-new cases plus revisions to Round 1.
  - If Stage-1 spike re-runs, output written under `backend/artifacts/reproduction/himalayan_rf4_spike/round2/`.
  - Updated `partner_submission_quality_score` — target ≥**70/100** for at least one priority region.
- **Owners:** SL (case review), ML (spike), HA (score check).
- **Acceptance gate:** weak-layer evidence pack reviewed; quality score ≥70 in at least one region.
- **Risk triggers:**
  - Quality score plateau <70 across all regions → escalate to a partner submission improvement cycle; consider narrowing the pilot to one region.
- **Tier classification:** Tier 2.

---

## Week 11 — Failure-Mode Review, SAR Re-Check, And Pre-Decision Memo

- **Objective:** produce a one-page memo that frames the Week 13 decision; surface failure modes openly.
- **Inputs:** all week-by-week artifacts; weekly progress notes; quality scores; leakage audits.
- **Deliverables:**
  - `pilot_failure_mode_review.md` — false alarms, missed high-danger days, weak-layer misses, calibration drift, station-density blind spots.
  - SAR re-check session: scientist verdict on whether SAR qualification can begin in Phase 2 (still no promotion).
  - `pilot_pre_decision_memo.md` (≤1 page) — current evidence posture per region, blocked claims, scientist-recommended decision options for Week 13.
- **Owners:** SL (memo lead), ML (failure-mode tooling), GS (SAR review).
- **Acceptance gate:** memo signed by SL and PL; decision options enumerated.
- **Risk triggers:**
  - Failure-mode review surfaces a systematic over-/under-forecast pattern → flag it explicitly in the memo; do not paper over.
- **Tier classification:** Tier 1.

---

## Week 12 — Release-Gate Attestation Or Block Decision

- **Objective:** make every gate visible and decide; nothing is implicit.
- **Inputs:** pre-decision memo; protocol; leakage audit; metric report (if any); quality scores; weak-layer evidence packs.
- **Deliverables:**
  - If metric report exists and floors pass: `release_gate_attestation.json/.md` populated (named approver, evidence digest, acceptance floors, measured results, reviewed timestamp, schema version, validation policy version), `reviewed_at` within 180 days, SHA-256-qualified `evidence_ref` and `acceptance_floors_ref`.
  - If any floor fails: explicit `claim_review_blocked` entry in `partner_submission_review_ledger.json` with next-action list.
  - Updated `partner_submission_status_dashboard.md` for the customer-facing readout.
- **Owners:** SL + named scientific approver (attestation), HA (floor verification), PL (dashboard).
- **Acceptance gate:** attestation written and signed **OR** block-with-next-actions filed. Either is acceptable; silent failure is not.
- **Risk triggers:**
  - Pressure to soften acceptance floors → refuse; preserve immutability of the Week-9 protocol.
- **Tier classification:** Tier 2.

---

## Week 13 — Decision Session, Phase 2 Scoping, Or Narrow Pilot

- **Objective:** convert evidence into one of the three D3-15 options: handoff-only, 90-day evidence pilot continuation, or deeper co-development.
- **Inputs:** every Week 1–12 artifact; attestation or block memo; partner readiness.
- **Deliverables:**
  - 60-min decision session minutes filed in `docs/Cust_comm.md`.
  - Phase 2 scoping doc (`Phase_2_Scoping.md`) if the scientist team chooses to continue: regions, slices, acceptance floors, cadence, budget alignment with D3-14 Phase 2 (INR 40–90 lakh).
  - Narrow-pilot doc (`Narrow_Pilot_Charter.md`) if the choice is to constrain to one region or one weak-layer class.
  - Termination memo (`Pilot_Termination_Memo.md`) if no continuation is chosen, with what was learned.
- **Owners:** SL + PL (session leads), PR (partner alignment), product team (write-up).
- **Acceptance gate:** one of the three documents is produced and circulated; no ambiguity about the next step.
- **Risk triggers:** none — Week 13 is the decision point, not a deliverable point.
- **Tier classification:** Tier 2.

---

## Contingencies

- **Contingency A — Swiss-only sandbox week.** Triggered when partner availability fails for any one-week milestone. Replace that week's partner-side deliverables with: (a) deeper Swiss reproduction notebooks against `data_rf2_tidy.csv`, (b) refined-discretization audits, (c) station-density and elevation-band visualizations. Nothing produced under Contingency A is a Himalayan claim.
- **Contingency B — Synthetic-pseudo-stations sandbox.** Triggered when no priority region has enough station coordinates by Week 3. Sample a deterministic subset of the existing grid cells as pseudo-stations, run GPxyz on them, and treat the output as a methodology demo only. Tag every artifact `pseudo_stations_methodology_demo_only`.
- **Contingency C — Re-submission cycle.** Triggered when partner submission quality scores stay <50/100 in Week 5. Pause forward motion; restart at Week 2's source-manifest discipline.
- **Contingency D — Scientist-led narrow pilot.** Triggered any time the Scientist Lead chooses to narrow to one region or one weak-layer class. Re-scope downstream weeks to fit; do not silently keep the original wide scope.

---

## Reading Order For The Scientist (First 60 Minutes)

1. `Scientist_Handout_OnePager.md` (this folder).
2. `docs/EnviDat_to_Partner_Schema_Mapping.md` (column-by-column mapping + current reproduction numbers).
3. This file.
4. `docs/MVP/presentation/rendered/avalanche-insight-hub-deck-3-scientist-validation.pdf`.
5. `docs/Scientist_Coworking_SLA.md`.
6. `MVP_V2_Action_List.md` and `MVP_V2_Weekly_Progress_Template.md` (this folder) — operational artifacts.

---

## Things This Plan Will Not Do

- It will **not** unlock production scoring or a Himalayan accuracy claim, regardless of how well the pilot goes.
- It will **not** treat partner bulletin archives as `D_tidy`-grade truth.
- It will **not** send synthetic fixtures as evidence.
- It will **not** weaken the Week-9 protocol floors after the protocol is signed.
- It will **not** promote SAR off the shadow path in this pilot.
