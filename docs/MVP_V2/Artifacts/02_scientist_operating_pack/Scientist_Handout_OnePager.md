# Avalanche Insight Hub — Scientist One-Pager (MVP V2)

Status: 2026-05-24 · For SASE/DGRE scientist review · Print-ready

---

## What you are reviewing

A **governed decision-support platform** for avalanche forecasting, partner evidence intake, scientist review, and gated promotion. **Not** a statutory warning-service authority. **Not** a Himalayan accuracy claim. **Not** an autonomous truth-generation engine.

---

## What is **live** today

- Public route and `/admin` route hosted; same-day `20×20` / `72h` full-grid technical publication for Colorado Rockies (proof: 2026-05-08).
- Colorado Rockies is live technical proof, not the target validation geography. It proves route hosting, publication mechanics, grid rendering, admin observability, and claim-boundary discipline.
- Himalayan live expansion is blocked until the partner evidence checklist, local holdout, scientist release gates, and app region wiring pass.
- Random-Forest baseline (`surrogate_rf_v1`) anchors public scoring; current full-grid artifact uses heuristic-fallback explanation; TreeSHAP path implemented and pending active-run refresh.
- Batch-first delivery, masked terrain (APT), reduced-confidence cues, share/export/report workflow, scientist verification queue.

## What is **research-only**

- Swiss RAvaFcast reproduction lane (read-only): Stage-1 RF4 calibrated accuracy `0.8937`, macro-F1 `0.7508`, class-4 F1 `0.3636` on Swiss `data_rf2_tidy.csv` (initial reproduction signal; paper parity audit ongoing). Stage-2 GPxyz `blocked_station_coordinates_required`. Stage-3 station-row baseline accuracy `0.8085`, macro-F1 `0.7848`. These numbers are **not** Himalayan claims.
- Himalayan v3 partner-evidence intake (`himalayan_accuracy_readiness_contract_v3`): 20+ governance artifacts (see partner packet inventory below).
- SAR / U-Net shadow path: candidate evidence; not promoted.
- MTS-LSTM dynamic head: candidate; not promoted.

## What is **blocked** by claim discipline

- `production_scoring_allowed = false`
- `himalayan_accuracy_claim_allowed = false`
- No SAR operational claim.
- No `D_tidy` substitution by raw public bulletins.
- No use of synthetic fixtures as evidence.

---

## Partner packet inventory (what your team receives)

| File | Purpose |
|---|---|
| `partner_handoff_readme.md` + `.json` | First-read guide and command sequence |
| `partner_field_dictionary.md` + `.json` | Field meanings, units, controlled values, danger-scale mapping caveat |
| `partner_source_package_checksum_guide.md` + `.json` | SHA-256 workflow, `source_ref` formats, manifest fields |
| `partner_source_manifest_template.{json,md}` + `partner_source_manifest_starter.{json,md}` | Owner, dataset, license, date range, reviewer, `evidence_package_ref` |
| 10 blank v3 evidence CSV templates | Stations, weather, snowpack, danger labels, polygons, events, remote sensing, terrain, scientist reviews, holdout |
| `partner_sample_row_pack.{json,md}` | One example row per CSV, marked `EXAMPLE_ONLY_REPLACE_WITH_REVIEWED` |
| `partner_intake_checklist.{json,md}` | Full submission contract; license/freshness rules |
| `partner_intake_preflight.{json,md}` | Lightweight presence/structure check before deep validation |
| `partner_source_manifest_validation.{json,md}` | Source-package governance verdict |
| `partner_evidence_validation.{json,md}` | Per-CSV schema, row-count, coverage, controlled-vocabulary checks |
| `partner_submission_quality_score.{json,md}` | 100-point package readiness rubric |
| `partner_submission_acceptance_checklist.{json,md}` | Score failures translated into partner-side acceptance criteria |
| `partner_submission_manifest_diff.{json,md}` | File presence/SHA-256/size/row-count diff against prior snapshots |
| `partner_submission_review_ledger.{json,md}` | One record per package attempt: blocker, readiness, next actions |
| `partner_submission_summary.{json,md}` | First-blocker handoff combining preflight + validations + readiness |
| `partner_submission_status_dashboard.{json,md}` | One-page operator/scientist status |
| `partner_package_index.{json,md}` | Navigation map of every artifact |
| `partner_intake_dry_run_runbook.{json,md}` | Operator procedure against the synthetic fixture only |
| `partner_incoming_triage_runbook.{json,md}` | First-response command sequence for real packages |
| `himalayan_local_holdout_protocol.{json,md}` | Pre-registered splits, leakage checks, metrics, acceptance floors |
| `himalayan_local_holdout_leakage_audit.{json,md}` | Cross-split / source-overlap audit |
| `himalayan_local_holdout_prediction_template.{json,md,csv}` | Header-only CSV for model output handoff |
| `himalayan_local_holdout_metric_report.{json,md}` | Refuses metrics until audit passes; gates release |
| `release_gate_attestation_template_pack.{json,md}` | Named approver, evidence digest, acceptance floors, measured results |
| `himalayan_top10_feature_gap_matrix.{json,md}` | Top-10 feature roadmap tied to evidence statuses |
| `partner_synthetic_validation_report.{json,md}` + fixture | Deterministic validator smoke material, **never** evidence |

Twenty-plus governance artifacts, hash-traceable, license-aware, freshness-bound (`reviewed_at ≤ 365 days`; attestations ≤ 180 days).

---

## What we ask of the scientist team

1. **Decide what `D_tidy`-grade truth means locally** — nominate the nowcast/observer/event/reanalysis sources you trust.
2. **Pick three priority regions and one priority avalanche-problem class** for the pilot.
3. **Co-sign the local holdout protocol in Week 9** before any metric is computed.
4. **Own the weak-layer slice definitions** that will be the case-by-case review pack in Weeks 8 and 10.
5. **Decide in Week 13** whether to continue, narrow, or terminate the pilot — you have explicit `extend / narrow / block / terminate` authority every week.

## What we are committing to

- Weekly cadence: Mon sync, Wed working session, Fri progress note (template provided).
- Tagged claim discipline: every statement maps to `Hosted production`, `Repo/admin verified`, `Artifact/doc proof only`, `Candidate/gated`, or `Research-only`.
- Written acknowledgement of your decisions inside the same calendar week.
- No silent failures at Week 12 — either a signed release-gate attestation or an explicit `claim_review_blocked` ledger entry.

---

## Reading order for the first 60 minutes

1. This page.
2. `docs/EnviDat_to_Partner_Schema_Mapping.md` (column-by-column + current reproduction numbers).
3. `MVP_V2_13_Week_Pilot_Plan.md` (this folder).
4. `avalanche-insight-hub-deck-3-scientist-validation.pdf` (this folder).
5. `docs/Scientist_Coworking_SLA.md`.
6. `MVP_V2_Action_List.md` + `MVP_V2_Weekly_Progress_Template.md` (operational artifacts).

---

## Decision options at Week 13 (D3-15 reference)

- **Option 1 — Handoff session only.** Low commitment; high clarity before any data formatting.
- **Option 2 — 90-day evidence pilot.** This 13-week plan continued; partner package submission, triage, scientist review, go/no-go gates.
- **Option 3 — Deeper co-development track.** Validation authority, publication intent, longer program arc; aligns with Deck 3 Phase 2 (3–9 months, INR 40–90 lakh).

---

## What this one-pager is **not**

- A statutory warning service brochure.
- A Himalayan accuracy claim.
- A SAR promotion.
- An autonomous-AI pitch.
- A request for endorsement without evidence.
