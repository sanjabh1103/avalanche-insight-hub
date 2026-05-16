# Avalanche Insight Hub — Challenge Alignment Transcript

## D2-1 — Challenge Alignment Contract

_Challenge alignment_

This deck maps the top systemic avalanche-forecasting challenges to the current MVP response, without converting partial progress into completed science.

Evidence lanes: Research agenda

Current state and future strategy

- Ratings use the stricter evidence-gated source table

- Current state is separated from future strategy

- Hosted proof is same-day full-grid technical publication, not scientist validation closure

- Candidate methods stay gated until supporting evidence exists

Evidence level:
`Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D2-2 — Data Collection And Observation Scarcity

_Challenge alignment_

The MVP reduces dependence on manual observations, but it does not replace field snowpack truth.

Evidence lanes: Research agenda

Current state and future strategy

- Dangerous manual collection: revised rating `3/5`

- Sparse AWS networks: revised rating `3/5`

- Field reports and news ingest augment the evidence base

- Open-Meteo and snowpack proxies reduce dependence on dense local stations

- Future strategy: scientist-reviewed field and observatory data integration

Evidence level:
`Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D2-3 — Occurrence Records And Autonomous Evidence

_Challenge alignment_

Governed evidence fusion is useful because avalanche occurrence records are incomplete, delayed, and noisy.

Evidence lanes: Technical evidence; Research agenda

Current state and future strategy

- Uncertainty in occurrence records: revised rating `3/5`

- Current evidence: deduplication, `label_confidence`, and `training_weight`

- News and field reports are staged before they influence training or review

- Future strategy: scientist-owned adjudication rules and regional gold cases

Evidence level:
`Repo/admin verified` plus `Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D2-4 — Rare Events And Feature Discipline

_Challenge alignment_

The current pipeline addresses class imbalance and feature sprawl better than a generic accuracy-led model story.

Evidence lanes: Technical evidence; Research agenda

Current state and future strategy

- Severe class imbalance: revised rating `4/5`

- Feature redundancy and overfitting: revised rating `4/5`

- Current technical path references rare-event metrics, KMeansSMOTE, and Recursive Feature Elimination

- Public users do not directly see this mitigation, so it remains technical evidence

- Future strategy: benchmark slices that expose miss, false-alarm, and calibration behavior

Evidence level:
`Repo/admin verified` plus `Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D2-5 — Physical Processes And Weak Layers

_Challenge alignment_

The MVP is physics-aware, but not a complete snowpack-physics forecasting stack.

Evidence lanes: Research agenda

Current state and future strategy

- Complex physical processes: revised rating `3/5`

- Current state: snowpack proxies, terrain masks, runout seeding, and bulletin framing

- Current active runout proof is analytical Alpha-Beta fallback

- Future strategy: weak-layer plausibility review and validated WhiteboxTools runout path

Evidence level:
`Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D2-6 — Spatial And Temporal Hazard Fusion

_Challenge alignment_

The hosted workspace meaningfully fuses where and when risk changes, while still requiring scientific review of the forecast content.

Evidence lanes: Live platform; Research agenda

Current state and future strategy

- Spatial-temporal disconnect: revised rating `4/5`

- Current state: published grid, timeline, daypart bulletin, and optional 3D inspection

- Hosted proof: same-day `20x20` / `72h` full-grid technical publication

- Future strategy: region-specific validation cases and scientist review of daypart shifts

Evidence level:
`Hosted production` plus `Artifact/doc proof only`

Hosted route proof

---

## D2-7 — Weighting, Calibration, And Multiple Optima

_Challenge alignment_

The platform reduces ad hoc promotion decisions with gates, but it does not eliminate calibration ambiguity.

Evidence lanes: Technical evidence; Research agenda

Current state and future strategy

- Subjective parameter weighting: revised rating `3/5`

- Multiple optima in calibration: revised rating `3/5`

- Current state: benchmark summaries, PSS/Brier gates, and stability summaries

- Current stability evidence is conservative and should not be framed as closure

- Future strategy: scientist-owned threshold and calibration review

Evidence level:
`Repo/admin verified` plus `Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D2-8 — Compute Bottlenecks And Batch Delivery

_Challenge alignment_

The strongest engineering response is batch-first artifact delivery, which keeps the live website responsive while heavy computation remains upstream.

Evidence lanes: Live platform; Technical evidence

Current state and future strategy

- Severe computational bottlenecks: revised rating `4/5`

- Current state: manifests, hourly payloads, lazy loading, and Supabase-backed publication metadata

- Modal.com remains off-path candidate compute, not the active public scorer proof

- Future strategy: GitHub Actions or lightweight VPS for repeatable offline publication

Evidence level:
`Hosted production` plus `Repo/admin verified`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D2-9 — Disparate Data Integration And Terrain Semantics

_Challenge alignment_

The MVP is strongest when it integrates forecast grids, bulletin semantics, terrain masking, and workflow controls into one current-state product.

Evidence lanes: Live platform; Research agenda

Current state and future strategy

- Disparate data integration: revised rating `4/5`

- APT masking prevents out-of-scope terrain from looking like ordinary low risk

- Shared artifacts connect map, bulletin, timeline, and review workflows

- Future strategy: PostGIS and richer geospatial contracts after validation needs are fixed

Evidence level:
`Hosted production` plus `Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D2-10 — SAR And Remote Sensing Limits

_Challenge alignment_

SAR is an important future evidence stream, but it remains candidate-gated in the current MVP.

Evidence lanes: Technical evidence; Research agenda

Current state and future strategy

- Topographic radar shadowing: revised rating `2/5`

- Current state: SAR coverage flags and candidate worker paths

- Do not describe SAR as operational or promoted

- Future strategy: labels, revisit-aware handling, shadow/layover review, and held-out qualification

Evidence level:
`Repo/admin verified` plus `Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D2-11 — Climate Drift And Micro-Climate Variability

_Challenge alignment_

Freshness surfaces help, but the MVP does not yet prove full adaptive climate-drift or micro-climate remediation.

Evidence lanes: Research agenda

Current state and future strategy

- Climate change concept drift: revised rating `3/5`

- Micro-climate variability: revised rating `2/5`

- Current state: freshness metadata, regional grids, terrain modifiers, and uncertainty cues

- Future strategy: local validation slices and continuous benchmark refresh

Evidence level:
`Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D2-12 — Trust, Explainability, And Reviewability

_Challenge alignment_

The platform reduces the black-box trust gap through provenance and explanation surfaces, but the current active artifact still uses heuristic explanation fallback.

Evidence lanes: Technical evidence; Research agenda

Current state and future strategy

- Black-box trust deficit: revised rating `4/5`

- Current state: cell inspection, admin provenance, uncertainty messaging, and implemented TreeSHAP path

- Active full-grid run: `heuristic_fallback`

- Future strategy: refresh active-run TreeSHAP evidence before stronger explanation claims

Evidence level:
`Repo/admin verified` plus `Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D2-13 — Customer Alignment Summary

_Challenge alignment_

The strongest customer proposition is not that every hard problem is solved; it is that the MVP makes the hard problems visible, governable, and ready for focused validation.

Evidence lanes: Live platform; Research agenda

Current state and future strategy

- Current state: public route, admin route, full-grid publication proof, workflow controls

- Current state: masked terrain, uncertainty, and current-state bulletin semantics

- Technical evidence: rare-event training discipline and benchmark gates

- Future strategy: scientist-led validation, SAR qualification, and candidate-model promotion rules

Evidence level:
`Hosted production` plus `Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D2-14 — Immediate Improvement Areas

_Challenge alignment_

The next work should concentrate on the gaps that most affect scientific credibility and customer confidence.

Evidence lanes: Research agenda

Current state and future strategy

- Full-grid scientist validation over selected regional cases

- TreeSHAP refresh for active full-grid artifacts

- WhiteboxTools runout qualification beyond smoke proof

- SAR held-out evidence and promotion gates

- Field-report and occurrence-record adjudication pack

Evidence level:
`Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D2-15 — Discussion Close

_Challenge alignment_

The decision is whether to use the current MVP as the shared workbench for the validation program.

Evidence lanes: Research agenda

Current state and future strategy

- Approve the current-state MVP as the validation workbench

- Select priority regions and challenge categories

- Agree benchmark and release-gate ownership

- Keep customer-facing claims tied to proof buckets

Evidence level:
`Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.
