# Deck 4 Final: Top 15 Challenge Alignment

Updated: May 9, 2026

## Deck Design System

- Theme: Mountain Evidence Heatmap
- Backgrounds: alternate only between `Light Snow #F7FAFB` and `Deep Ridge #1F3340`
- Primary accent: `Risk Amber #C9862B`
- Secondary accents: `Glacier Blue #2A7FA3`, `Pine Ink #102F35`, `Mist Line #D9E8EE`
- Typography: Inter for body, IBM Plex Sans Condensed for slide titles
- Customer-facing tone: current-state alignment with visible future strategy.
- Asset use: use screenshots only from `assets/screenshots/` if a visual proof crop is required.

## Slide 1: Challenge Alignment Contract

**Background:** Deep Ridge
**Customer message:**
This deck maps the top systemic avalanche-forecasting challenges to the current MVP response, without converting partial progress into completed science.

**Current state and future strategy:**
- Ratings use the stricter evidence-gated source table
- Current state is separated from future strategy
- Hosted proof is same-day full-grid technical publication, not scientist validation closure
- Candidate methods stay gated until supporting evidence exists

**Evidence level:** `Artifact/doc proof only`
**Supporting sources:** [Top Challenges](../../source/Top_challanges.md), [Claim Ledger](../../source/Scientist_claim_ledger.md)

---

## Slide 2: Data Collection And Observation Scarcity

**Background:** Light Snow
**Customer message:**
The MVP reduces dependence on manual observations, but it does not replace field snowpack truth.

**Current state and future strategy:**
- Dangerous manual collection: revised rating `3/5`
- Sparse AWS networks: revised rating `3/5`
- Field reports and news ingest augment the evidence base
- Open-Meteo and snowpack proxies reduce dependence on dense local stations
- Future strategy: scientist-reviewed field and observatory data integration

**Evidence level:** `Artifact/doc proof only`
**Supporting sources:** [Top Challenges](../../source/Top_challanges.md), [Research Base](../../source/Reserches.md)

---

## Slide 3: Occurrence Records And Autonomous Evidence

**Background:** Light Snow
**Customer message:**
Governed evidence fusion is useful because avalanche occurrence records are incomplete, delayed, and noisy.

**Current state and future strategy:**
- Uncertainty in occurrence records: revised rating `3/5`
- Current evidence: deduplication, `label_confidence`, and `training_weight`
- News and field reports are staged before they influence training or review
- Future strategy: scientist-owned adjudication rules and regional gold cases

**Evidence level:** `Repo/admin verified` plus `Artifact/doc proof only`
**Supporting sources:** [Governed Autonomy Note](../../source/Governed_autonomy_evidence_fusion_note.md), [Top Challenges](../../source/Top_challanges.md)

---

## Slide 4: Rare Events And Feature Discipline

**Background:** Deep Ridge
**Customer message:**
The current pipeline addresses class imbalance and feature sprawl better than a generic accuracy-led model story.

**Current state and future strategy:**
- Severe class imbalance: revised rating `4/5`
- Feature redundancy and overfitting: revised rating `4/5`
- Current technical path references rare-event metrics, KMeansSMOTE, and Recursive Feature Elimination
- Public users do not directly see this mitigation, so it remains technical evidence
- Future strategy: benchmark slices that expose miss, false-alarm, and calibration behavior

**Evidence level:** `Repo/admin verified` plus `Artifact/doc proof only`
**Supporting sources:** [Current Architecture](../../source/Technical_Architecture_Current_Platform.md), [Benchmark Pack](../../source/Scientist_benchmark_pack_v0.md)

---

## Slide 5: Physical Processes And Weak Layers

**Background:** Light Snow
**Customer message:**
The MVP is physics-aware, but not a complete snowpack-physics forecasting stack.

**Current state and future strategy:**
- Complex physical processes: revised rating `3/5`
- Current state: snowpack proxies, terrain masks, runout seeding, and bulletin framing
- Current active runout proof is analytical Alpha-Beta fallback
- Future strategy: weak-layer plausibility review and validated WhiteboxTools runout path

**Evidence level:** `Artifact/doc proof only`
**Supporting sources:** [Top Challenges](../../source/Top_challanges.md), [Validation Protocol](../../source/Scientist_validation_protocol_v0.md)

---

## Slide 6: Spatial And Temporal Hazard Fusion

**Background:** Light Snow
**Customer message:**
The hosted workspace meaningfully fuses where and when risk changes, while still requiring scientific review of the forecast content.

**Current state and future strategy:**
- Spatial-temporal disconnect: revised rating `4/5`
- Current state: published grid, timeline, daypart bulletin, and optional 3D inspection
- Hosted proof: same-day `20x20` / `72h` full-grid technical publication
- Future strategy: region-specific validation cases and scientist review of daypart shifts

**Evidence level:** `Hosted production` plus `Artifact/doc proof only`
**Screenshot:** ![Hosted public full-grid proof](assets/screenshots/2026-05-08_hosted-public_cell-full-grid-after-refresh.png)
**Supporting sources:** [Proof Manifest](../06_Proof_Status_And_Screenshot_Manifest.md), [Top Challenges](../../source/Top_challanges.md)

---

## Slide 7: Weighting, Calibration, And Multiple Optima

**Background:** Deep Ridge
**Customer message:**
The platform reduces ad hoc promotion decisions with gates, but it does not eliminate calibration ambiguity.

**Current state and future strategy:**
- Subjective parameter weighting: revised rating `3/5`
- Multiple optima in calibration: revised rating `3/5`
- Current state: benchmark summaries, PSS/Brier gates, and stability summaries
- Current stability evidence is conservative and should not be framed as closure
- Future strategy: scientist-owned threshold and calibration review

**Evidence level:** `Repo/admin verified` plus `Artifact/doc proof only`
**Supporting sources:** [Benchmark Pack](../../source/Scientist_benchmark_pack_v0.md), [Scientist Discussion Framework](../../source/Scientist_discussion_framework.md)

---

## Slide 8: Compute Bottlenecks And Batch Delivery

**Background:** Light Snow
**Customer message:**
The strongest engineering response is batch-first artifact delivery, which keeps the live website responsive while heavy computation remains upstream.

**Current state and future strategy:**
- Severe computational bottlenecks: revised rating `4/5`
- Current state: manifests, hourly payloads, lazy loading, and Supabase-backed publication metadata
- Modal.com remains off-path candidate compute, not the active public scorer proof
- Future strategy: GitHub Actions or lightweight VPS for repeatable offline publication

**Evidence level:** `Hosted production` plus `Repo/admin verified`
**Supporting sources:** [Current Architecture](../../source/Technical_Architecture_Current_Platform.md), [PRD Addendum](../../../prd_add3.md)

---

## Slide 9: Disparate Data Integration And Terrain Semantics

**Background:** Light Snow
**Customer message:**
The MVP is strongest when it integrates forecast grids, bulletin semantics, terrain masking, and workflow controls into one current-state product.

**Current state and future strategy:**
- Disparate data integration: revised rating `4/5`
- APT masking prevents out-of-scope terrain from looking like ordinary low risk
- Shared artifacts connect map, bulletin, timeline, and review workflows
- Future strategy: PostGIS and richer geospatial contracts after validation needs are fixed

**Evidence level:** `Hosted production` plus `Artifact/doc proof only`
**Supporting sources:** [Top 20 Features](../../source/Top20_features.md), [Technical Glossary](../../source/Technical_Glossary_And_Acronyms.md)

---

## Slide 10: SAR And Remote Sensing Limits

**Background:** Deep Ridge
**Customer message:**
SAR is an important future evidence stream, but it remains candidate-gated in the current MVP.

**Current state and future strategy:**
- Topographic radar shadowing: revised rating `2/5`
- Current state: SAR coverage flags and candidate worker paths
- Do not describe SAR as operational or promoted
- Future strategy: labels, revisit-aware handling, shadow/layover review, and held-out qualification

**Evidence level:** `Repo/admin verified` plus `Artifact/doc proof only`
**Supporting sources:** [Research Appendix](../../source/Demo_research_appendix.md), [Modal/GPU Inventory](../../source/Modal_GPU_ML_Inventory.md)

---

## Slide 11: Climate Drift And Micro-Climate Variability

**Background:** Light Snow
**Customer message:**
Freshness surfaces help, but the MVP does not yet prove full adaptive climate-drift or micro-climate remediation.

**Current state and future strategy:**
- Climate change concept drift: revised rating `3/5`
- Micro-climate variability: revised rating `2/5`
- Current state: freshness metadata, regional grids, terrain modifiers, and uncertainty cues
- Future strategy: local validation slices and continuous benchmark refresh

**Evidence level:** `Artifact/doc proof only`
**Supporting sources:** [Top Challenges](../../source/Top_challanges.md), [Validation Protocol](../../source/Scientist_validation_protocol_v0.md)

---

## Slide 12: Trust, Explainability, And Reviewability

**Background:** Light Snow
**Customer message:**
The platform reduces the black-box trust gap through provenance and explanation surfaces, but the current active artifact still uses heuristic explanation fallback.

**Current state and future strategy:**
- Black-box trust deficit: revised rating `4/5`
- Current state: cell inspection, admin provenance, uncertainty messaging, and implemented TreeSHAP path
- Active full-grid run: `heuristic_fallback`
- Future strategy: refresh active-run TreeSHAP evidence before stronger explanation claims

**Evidence level:** `Repo/admin verified` plus `Artifact/doc proof only`
**Supporting sources:** [Modal/GPU Inventory](../../source/Modal_GPU_ML_Inventory.md), [Claim Ledger](../../source/Scientist_claim_ledger.md)

---

## Slide 13: Customer Alignment Summary

**Background:** Deep Ridge
**Customer message:**
The strongest customer proposition is not that every hard problem is solved; it is that the MVP makes the hard problems visible, governable, and ready for focused validation.

**Current state and future strategy:**
- Current state: public route, admin route, full-grid publication proof, workflow controls
- Current state: masked terrain, uncertainty, and current-state bulletin semantics
- Technical evidence: rare-event training discipline and benchmark gates
- Future strategy: scientist-led validation, SAR qualification, and candidate-model promotion rules

**Evidence level:** `Hosted production` plus `Artifact/doc proof only`
**Supporting sources:** [Demo Decision Brief](../../source/Demo_decision_brief.md), [Scientist Discussion Framework](../../source/Scientist_discussion_framework.md)

---

## Slide 14: Immediate Improvement Areas

**Background:** Light Snow
**Customer message:**
The next work should concentrate on the gaps that most affect scientific credibility and customer confidence.

**Current state and future strategy:**
- Full-grid scientist validation over selected regional cases
- TreeSHAP refresh for active full-grid artifacts
- WhiteboxTools runout qualification beyond smoke proof
- SAR held-out evidence and promotion gates
- Field-report and occurrence-record adjudication pack

**Evidence level:** `Artifact/doc proof only`
**Supporting sources:** [Validation Protocol](../../source/Scientist_validation_protocol_v0.md), [Scientist Meeting Checklist](../../source/Scientist_meeting_checklist.md)

---

## Slide 15: Discussion Close

**Background:** Deep Ridge
**Customer message:**
The decision is whether to use the current MVP as the shared workbench for the validation program.

**Current state and future strategy:**
- Approve the current-state MVP as the validation workbench
- Select priority regions and challenge categories
- Agree benchmark and release-gate ownership
- Keep customer-facing claims tied to proof buckets

**Evidence level:** `Artifact/doc proof only`
**Supporting sources:** [Scientist Discussion Framework](../../source/Scientist_discussion_framework.md), [Top Challenges](../../source/Top_challanges.md)
