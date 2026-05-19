# European Shadow SAR Client Talk Track

This is a five-slide talk track for a shadow-only client briefing. It is not a production-launch deck.

## Slide 1: What Is Implemented

Message: the European shadow-data layer and SAR qualification workflow are implemented for validation and research discussion.

Evidence:
- `docs/European_Data_Shadow_Pipeline.md`
- `docs/European_Shadow_SAR_Client_Status_Brief.md`

Say:
- European source registry, staging, benchmark, SAR evaluation, and promotion guards exist.

Do not say:
- The European data is wired into public production scoring.

## Slide 2: AvalCD Passed The First SAR Gate

Message: v8 passes the AvalCD scene-blended first gate.

Evidence:
- `backend/artifacts/european-shadow-real-benchmarks/european-shadow-real-avalcd-scene-blended-v8-2026-05-19/european_shadow_benchmark_report.json`

Say:
- AvalCD v8 precision `0.6093` and recall `0.5942` pass the internal first-gate floors.

Do not say:
- AvalCD pass means SnowSlide or production pass.

## Slide 3: SnowSlide Reveals Localized Failure Modes

Message: SnowSlide v8 fails aggregate research-grade acceptance, but the failure is not uniform.

Evidence:
- `backend/artifacts/european-shadow-qualification/snowslide-research-grade-v8-2026-05-19/diagnostics/sar_error_diagnostics.json`

Say:
- `tromso_20241220` passes alone.
- `pish_20230221` and `livigno_20250318` are severe failure cases.
- Manual review should focus on the scene-specific burden.

Do not say:
- The model is globally validated or globally failed.

## Slide 4: Governance Guardrails

Message: production remains blocked by design.

Evidence:
- `backend/common/sar_acceptance_policy.py`
- `backend/sar_release_promote.py`
- `backend/scripts/build_european_shadow_sar_closeout_pack.py`

Say:
- SAR promotion requires accepted SnowSlide research-grade evidence and, after SnowSlide-guided tuning, a fresh final holdout.

Do not say:
- `beats_baseline=true` is sufficient for promotion.

## Slide 5: Next Scientific Step

Message: the next step is manual scene/component review, not another blind GPU run.

Evidence:
- `backend/artifacts/european-shadow-qualification/snowslide-research-grade-v8-2026-05-19/diagnostics/manual_label_review_packet.md`
- `backend/artifacts/european-shadow-qualification/snowslide-research-grade-v8-2026-05-19/diagnostics/manual_label_review_decisions.csv`

Say:
- The 30-component worksheet must be assigned to a reviewer with SAR and avalanche-domain literacy.
- v9 design is justified only after review confirms a model-side gap or a formal waiver is recorded.

Do not say:
- v9 is already approved or guaranteed to pass.

