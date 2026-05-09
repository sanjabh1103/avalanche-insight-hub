# Scientist Meeting Checklist

Updated: May 8, 2026

Use this checklist immediately before any scientist or customer-facing discussion. It is derived from `docs/MVP/source/Scientist_claim_ledger.md`, `docs/MVP/source/Scientist_evidence_surface_ledger.md`, current route smoke, and the current artifact pack.

## Safe To Say Now

- We already have a usable batch-first avalanche forecast decision-support shell on the public route.
- The current hosted public proof is same-day published full-grid technical evidence for Colorado Rockies: `forecastDate=2026-05-08`, `sameDayPublished=true`, `stale=false`, `horizonHours=72`, `20x20`, `400` ready cells, `0` stale cells, structured bulletin present, and no synthetic inputs.
- The May 8 full-grid artifact is scientist-review-ready publication evidence, not final field validation or authority-grade warning-service proof.
- The public forecast surface implements `EAWS-style experimental` bulletin framing with explicit reduced-confidence and high-uncertainty cues.
- Masked terrain is intentionally distinguished from danger classes to avoid false confidence outside eligible terrain.
- Operators can inspect source health, decision provenance, runtime benchmark traces, and bounded model-stability evidence in the admin lane.
- Candidate-model governance is explicit: the current dynamic scorer remains blocked until release gates pass.
- Autonomous evidence is governed through explicit weighting, corroboration, decay, and audit-only exclusions before it is trusted.

## Say Only With Caveat

- Consequence-aware overlays and expert review exist, but their value still depends on region-specific data quality and coverage.
- Runtime benchmarks prove reproducible pipeline timing and publication traces, not field-validation quality.
- Stability summaries prove bounded governance evidence, not broad robustness across all mountain conditions.
- Evaluation plumbing and contracts are implemented, but the current live evaluation surface is still sparse compared with the artifact/test path.
- The autonomy story is strongest as governed evidence fusion under sparse-data constraints, not as solved autonomous avalanche truth generation.
- The current product is useful for scientist-in-the-loop co-development discussion, not as proof of completed science.

## Blocked / Do Not Say

- Do not say `mts_lstm_v1` is the active public model or that it is already promoted.
- Do not say SAR support is operationally validated or authoritative in the current MVP.
- Do not say whitebox runout is operationally qualified.
- Do not say critical-layer or weak-layer validation is already complete.
- Do not say the current MVP is an official avalanche warning service or equivalent to an authority-grade workflow.
- Do not borrow validation status from EAWS, WMO, Google, or any external precedent as if that proof transfers automatically to this product.

## Pre-Meeting Checks

1. Re-run the verification commands in `docs/MVP/source/Scientist_readiness_next_thread_prompt.md`.
2. Confirm hosted `/` still shows current publication state, reduced-confidence language where artifact support exists, and masked-terrain semantics without wording drift.
3. Confirm hosted signed-in `/admin` is showing the freshest publication/model rows, not stale `model_status` state.
4. If the hosted admin smoke depends on the demo-admin seam, confirm `DEMO_ADMIN_PASSWORD` is available locally before starting.
5. If any route, artifact, or test no longer proves the statement you want to use, downgrade to the safe phrasing from the claim ledger immediately.
