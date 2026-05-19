# European Shadow SAR Client Status Brief

This is the client-safe closeout status for the European shadow SAR lane. It separates implemented capability, shadow evidence, and production readiness.

## Executive Position

The European shadow-data pipeline and SAR qualification workflow are implemented and evidence-rich. The SAR lane is not production-ready: v8 passes the AvalCD scene-blended gate but fails SnowSlide research-grade held-out acceptance on precision and F1. Public production scoring remains unchanged.

The most important scientific update is that v8 does not fail uniformly. SnowSlide errors are localized by scene: one scene passes research-grade floors on its own, three scenes are near-pass, and two scenes are severe failure cases that pull the aggregate below acceptance.

## What Is Complete

| Area | Status | Client-safe wording |
|---|---|---|
| European source registry and production guard | Complete | European sources are catalogued for shadow validation, with production scoring explicitly blocked. |
| Reviewed local staging paths | Partially complete | SPOT6, SLF accidents, and AvalCD have real staged artifacts; remaining families are data-review pending. |
| AvalCD SAR qualification lane | Complete for current gate | v8 passes AvalCD scene-blended precision and recall floors. |
| SnowSlide held-out evaluation | Complete for v8 | v8 was evaluated on all seven SnowSlide scenes with dry-run/no-persistence guardrails. |
| Promotion guard | Complete | SAR cannot promote from `beats_baseline=true` alone; accepted SnowSlide research-grade evidence is required. |

## Current V8 Gate Results

| Gate | v8 result | Required floor | Status |
|---|---:|---:|---|
| AvalCD precision | `0.6093` | `>=0.60` | Pass |
| AvalCD recall | `0.5942` | `>=0.50` | Pass |
| SnowSlide precision | `0.6137` | `>=0.70` | Fail |
| SnowSlide recall | `0.5584` | `>=0.50` | Pass |
| SnowSlide F1 | `0.5847` | `>=0.60` | Fail |
| SnowSlide false-positive rate | `0.00184` | `<=0.002` | Pass |

The v8 non-GPU threshold/component sweep found `passing_candidate_count=0`. The current blocker is not an untested threshold setting; it is a SnowSlide precision/F1 qualification gap that requires manual component review before any v9 design.

## Per-Scene SnowSlide V8 Results

Research-grade scene-level reference: precision `>=0.70`, recall `>=0.50`, F1 `>=0.60`, false-positive rate `<=0.002`.

| Scene | Region | Precision | Recall | F1 | FPR | Verdict |
|---|---|---:|---:|---:|---:|---|
| `tromso_20241220` | Norway | `0.848` | `0.686` | `0.758` | `0.00172` | Passes alone |
| `nuuk_20210411` | Greenland Nuuk | `0.630` | `0.609` | `0.619` | `0.00210` | Near-pass; FPR slightly above ceiling |
| `livigno_20250129` | Italian Alps | `0.631` | `0.549` | `0.587` | `0.00095` | Near-pass; F1 below floor |
| `livigno_20240403` | Italian Alps | `0.653` | `0.509` | `0.572` | `0.00173` | Near-pass; precision/F1 below floors |
| `nuuk_20160413` | Greenland Nuuk | `0.614` | `0.465` | `0.529` | `0.00173` | Below; recall gap |
| `pish_20230221` | Pamir | `0.393` | `0.569` | `0.465` | `0.00557` | Severe false-positive burden |
| `livigno_20250318` | Italian Alps | `0.405` | `0.436` | `0.420` | `0.00055` | Severe precision/F1 gap |

Interpretation: v8 carries real SnowSlide signal, but the aggregate failure is dominated by scene-specific problems. The next review should focus first on `pish_20230221` and `livigno_20250318`, while preserving the strong Tromso result as evidence that the model can work under some held-out conditions.

## Evaluation Coverage By Region

| Region key | Scene count | Metric status |
|---|---:|---|
| `greenland_nuuk` | 2 | `region_metrics_pending` |
| `italian_alps` | 3 | `region_metrics_pending` |
| `scandinavia_norway` | 1 | `region_metrics_pending` |
| `tajikistan_pamir` | 1 | `region_metrics_pending` |

The current AvalCD benchmark exposes coverage counts by region, not clean per-region precision/recall/F1. Do not present region-level metrics until the evaluator emits them directly.

## Manual Review Plan

Current status: `manual_scene_label_review_required`.

| Item | Status |
|---|---|
| Component count | 30 |
| Review owner | Unassigned |
| Target completion date | Unassigned |
| Presentation impact | External client presentation should not be scheduled until an owner and target date are named, or the absence is explicitly disclosed as a blocker. |
| Competency required | SAR domain literacy plus glaciology/avalanche field literacy |
| Throughput estimate | 5 components/hour; 30 components ~= 6 reviewer-hours plus reconciliation |
| Decision SLA | Each scene resolves to `label_remediation_required`, `labels_valid_model_gap`, `terrain_context_required`, or `review_incomplete`. |
| Blocking condition | Missing terrain/source context should be recorded as `terrain_context_required`, not forced into model failure. |

Decision branches:

| Manual review outcome | Next action |
|---|---|
| `label_remediation_required` | Plan label/source remediation; no v9 training until data issue is addressed. |
| `labels_valid_model_gap` | Prepare a no-launch v9 candidate-design review; GPU still requires separate one-run authorization. |
| `terrain_context_required` | Add terrain/SAR context review before any retraining decision. |
| `review_incomplete` | Keep SAR lane blocked. |

## Data Licenses And Use Boundaries

This matrix is conservative. It separates using a source in a presentation from deploying it commercially or sharing source imagery externally.

| Source family | Presentation OK? | Commercial deployment OK? | External imagery/share OK? | Notes |
|---|---|---|---|---|
| AvalCD | Yes with attribution for shadow-method discussion | No under current CC-BY-NC-style review posture | Needs license-specific review | Current SAR evidence is shadow qualification, not deployable commercial scoring. |
| Swiss SPOT6 outlines | Summary-level discussion OK with citation | Pending license review | Needs EnviDat/source-term review | Do not distribute imagery or derived outlines externally without terms review. |
| SLF accidents | Summary-level discussion OK with citation | Pending product-specific review | Needs source-term review | Accident data is bias/audit context, not occurrence-frequency truth. |
| Norway SAR detections | Summary-level discussion OK | Pending source package/license review | Needs source-term review | Counts and package terms must be verified before relying on row totals. |
| French EPA/CLPA | Summary-level discussion OK | Pending avalanches.fr terms review | Needs source-term review | EPA/CLPA should remain occurrence/path-prior evidence until terms and schema are reviewed. |
| Swiss weather/snowpack | Summary-level discussion OK with attribution | Pending product-specific CC BY 4.0 review | Needs product-specific review | Context/calibration surface, not direct avalanche occurrence truth. |
| EAWS/SLF bulletins | Summary-level discussion OK | No production-warning equivalence | Needs source-specific review | Treat as context and semantics only; do not imply official warning replacement. |

## Statistical Limitations

SnowSlide v8 uses seven held-out scenes. This is useful qualification evidence, but it is not a high-power statistical estimate. The aggregate F1 of `0.5847` is close to the `0.60` floor, and inter-scene variance is high. Confidence intervals are not computed in the current artifact. A fresh final holdout remains mandatory before any production discussion after SnowSlide-guided tuning.

## Presenter Constraints

Do not say:

- SAR is production-ready.
- SnowSlide research-grade acceptance has passed.
- v9 will pass.
- Current SAR evidence changes public scoring.
- Scene-level imagery can be shared externally without license review.
- A precision/recall number without naming the evaluation set, threshold, and post-processing rule.
- AvalCD pass means SnowSlide or production pass.

## Independent Reviews And Follow-Through

An independent Claude 4.7 audit identified the previous uint8 probability-mask quantization issue that made high thresholds unreachable in stored SnowSlide masks. That finding led to the float32 probability-mask fix in commit `2931830`. The current v8 status is based on corrected float32 evidence, not the old quantized-mask artifact.

## Safe Client Presentation Claims

| Claim | Safe? | Exact framing |
|---|---|---|
| European shadow pipeline exists | Yes | Implemented for source staging, benchmark reconstruction, SAR qualification, and production-blocked validation. |
| AvalCD SAR evidence is real | Yes | v8 passes the AvalCD scene-blended first gate. |
| SnowSlide research-grade passes | No | v8 fails aggregate precision and F1 floors. |
| SAR production scoring is ready | No | Production scoring is explicitly blocked pending SnowSlide and fresh-final holdout gates. |
| Next scientific action is known | Yes | Assign and complete the 30-component v8 manual review packet before any v9 candidate design. |

## Evidence Handles

| Evidence | Path |
|---|---|
| Operator doc | `docs/European_Data_Shadow_Pipeline.md` |
| v8 closeout pack | `backend/artifacts/european-shadow-qualification/sar-v8-client-closeout-2026-05-19/european_shadow_sar_closeout_pack.md` |
| v8 SnowSlide acceptance | `backend/artifacts/european-shadow-qualification/snowslide-research-grade-v8-2026-05-19/acceptance_report.json` |
| v8 per-scene diagnostics | `backend/artifacts/european-shadow-qualification/snowslide-research-grade-v8-2026-05-19/diagnostics/sar_error_diagnostics.json` |
| v8 manual review packet | `backend/artifacts/european-shadow-qualification/snowslide-research-grade-v8-2026-05-19/diagnostics/manual_label_review_packet.md` |
| v8 component worksheet | `backend/artifacts/european-shadow-qualification/snowslide-research-grade-v8-2026-05-19/diagnostics/manual_label_review_decisions.csv` |
