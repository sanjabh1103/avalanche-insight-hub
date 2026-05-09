# Scientist Benchmark Pack v0

Updated: May 8, 2026

This is a scientist discussion starter built from current repo truth. It packages the evidence we can already prove without implying fresh field validation or promotion readiness.

## Benchmark Purpose

The purpose of this pack is to make the current MVP discussable with a scientist in a disciplined way:

- prove what the product and operator lane already surface;
- package current artifact-backed governance evidence;
- expose the main failure slices and open science questions;
- define what should count as the next benchmark and validation work, rather than pretending it is already complete.

## What This Pack Can And Cannot Prove

### It can prove

- the public route and admin route are real, reachable proof surfaces;
- the current pipeline emits source health, decision provenance, candidate-model gating, autonomous evidence summaries, runtime benchmark traces, and bounded stability summaries;
- the evaluation and labeling contracts are implemented and regression-tested;
- current release language is disciplined enough to keep promoted-model and authority claims blocked.

### It cannot prove

- fresh field validation;
- critical-layer or weak-layer closure;
- promoted MTS-LSTM superiority in production;
- authoritative SAR qualification;
- authority-grade warning-service standing;
- broad regional transfer robustness beyond the currently packaged artifact evidence.

## Case Inventory

| Evidence case | Current source | What it contributes | Current limitation |
|---|---|---|---|
| Public forecast shell | Hosted `/` and `run-forecast` smoke on `2026-05-08` | Proves the batch-first forecast workspace and same-day full-grid publication metadata now exist on the hosted route. Current public artifact proof is technical publication proof: `72h`, `20x20`, `400` ready cells, `0` stale cells, structured bulletin present, and no synthetic inputs. | Product proof is not field-validation proof, and full-grid publication is not scientist validation closure. |
| Admin observability | Hosted signed-in `/admin` smoke on `2026-05-08` | Proves source health, decision provenance, model status, stability, benchmark surfaces, and forecast publication state exist in the operator lane for the active May 8 run. | Operator proof is richer than public proof and still requires correct row freshness before each customer send. |
| Inference manifest | `backend/artifacts/20260504T070406Z/inference_manifest.json` | Proves current active model type, candidate gates, evidence mix, and runtime benchmark trace. | This artifact is a local packaged run, not live field validation. |
| Stability summary | `backend/artifacts/20260504T070406Z/stability_summary.json` | Proves bounded seed-stability evidence and surfaces `classification = unstable`, `seed_count = 3`. | Small-seed stability is governance evidence, not exhaustive robustness validation. |
| Training stage metrics | `backend/artifacts/20260504T070406Z/training_stage_metrics.json` | Proves training runtime phase breakdown is reproducible and benchmarkable. | Runtime trace does not imply scientist-grade model quality. |
| Evaluation contracts | Deno tests for `label-forecast-outcomes`, `run-evaluation`, and shared metadata | Proves slice-materialization and evaluation metadata contracts exist. | Live evaluation tables remain sparse in current smoke. |
| Governance contracts | `backend/common/label_governance.py`; backend tests | Proves explicit weighting, decay, and weak/audit-only handling. | Governance rigor does not eliminate label noise or sparse-data blind spots. |

## Region Slices

The current artifact-backed autonomous evidence summary spans these region keys:

| Region slice | Current evidence anchor | Interpretation |
|---|---|---|
| `cascades_wa` | `autonomous_evidence_summary.region_keys` | Present in the current governed evidence mix. |
| `colorado_rockies` | `autonomous_evidence_summary.region_keys`; hosted public route uses Colorado in current smoke | Useful for public-surface semantics, not yet a scientist-approved benchmark slice. |
| `french_alps` | `autonomous_evidence_summary.region_keys` | Present in the current artifact mix. |
| `himalayas_nepal` | `autonomous_evidence_summary.region_keys`; current inference artifact region | Best current anchor for the intended sparse-data story. |
| `japanese_alps` | `autonomous_evidence_summary.region_keys` | Present in governed evidence mix. |
| `swiss_alps` | `autonomous_evidence_summary.region_keys`; hosted admin shows current Swiss publication row | Strong admin proof for freshest publication metadata, still not field validation. |

## Failure Slices

| Failure slice | Current signal | Why it matters |
|---|---|---|
| Reduced confidence | Public route exposes reduced-confidence bulletin states. | Keeps scientist trust by surfacing support limits instead of hiding them. |
| Source support gaps | `source_health` tracks completeness, weather freshness, SAR mode, and missing inputs. | Makes sparse-support conditions explicit in publication metadata. |
| Candidate gate failure | `dynamic_model_candidate.blocked_gate = shadow_quality_gate` in current artifact path. | Prevents false promotion narratives. |
| Stability drift | `stability_summary.classification = unstable`; threshold drift `0.157726`. | Shows current model family still needs bounded interpretation. |
| Narrow evidence mix | Current local artifact has `1000` autonomous positives and `0` manual positives. | This is exactly why the autonomy story must stay governed and caveated. |
| Evaluation sparsity | Current admin smoke shows empty / sparse evaluation tables. | The artifact/test path is stronger than the live dashboard counts today. |

## Critical-Layer Questions

These questions remain open and should be put directly to the scientist:

1. What evidence would count as minimally credible critical-layer review for this MVP?
2. Which weak-layer failure modes must be benchmarked before any candidate model promotion discussion?
3. Which regions should be treated as “do not generalize from current artifact evidence” until scientist review is complete?
4. What slice definitions matter most: elevation band, dry/wet domain, problem slug, recent-loading regime, or another scientist-defined taxonomy?
5. What would qualify as a meaningful benchmark delta from the current surrogate path?

## Acceptance Criteria

For this `v0` pack to be discussion-ready before the meeting, all of the following should be true:

- the public and admin routes are reachable and smoke-verified;
- claim-state and evidence-surface ledgers are complete and internally consistent;
- the benchmark harness runs cleanly against the current artifact pack;
- backend, frontend, and Deno regression commands pass;
- blocked claims remain blocked in both docs and UI language;
- every cited benchmark claim has a route, artifact, or test anchor.

## Known Blind Spots

- no scientist-approved critical-layer validation loop;
- no promoted dynamic model;
- no authoritative SAR release artifact;
- no authority-grade dissemination workflow;
- no broad live evaluation inventory on the admin surface;
- current evidence mix is governance-aware but still narrow and autonomy-heavy.
