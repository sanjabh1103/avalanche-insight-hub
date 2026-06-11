# European Shadow SAR Mission Review And Next Targets

This document summarizes how the European shadow/SAR qualification work progressed, what bottlenecks were crossed, what remains scientifically unresolved, and what should be targeted next. It is a presentation-prep and next-conversation handoff artifact. It is not a SAR production-readiness claim.

Evidence basis:

- Current tracked client docs and closeout code on `feature/european-data-shadow-pipeline`.
- v8 SAR closeout posture: AvalCD scene-blended gate passed; SnowSlide research-grade aggregate failed precision and F1; production scoring remains blocked.
- Manual review assignment: Sanjay B. authorized the shadow-only briefing framing; Dr. AK___ owns the 30-component SnowSlide v8 manual review with target date `2026-05-27`.
- External research anchors: [AvalCD arXiv](https://arxiv.org/abs/2603.22658), [Bianchi SAR FCN](https://arxiv.org/abs/1910.05411), [The Cryosphere 2024 SAR avalanche transferability](https://tc.copernicus.org/articles/18/2809/2024/), [Frontiers remote-sensing label noise](https://www.frontiersin.org/journals/remote-sensing/articles/10.3389/frsen.2022.1100012/full), and [ISPRS noisy-label segmentation](https://isprs-annals.copernicus.org/articles/V-2-2022/275/2022/).

## Table 1. Why We Started, Bottlenecks Crossed, Targets Achieved

| # | Area | Why we started / target | Bottleneck crossed | Target achieved | Uniqueness index highlight | Rating /5 |
|---:|---|---|---|---|---|---:|
| 1 | SnowSlide v5 blocker closure | Fix the remaining SAR research-grade blocker without weakening gates. | Threshold/postprocess-only recovery could not pass. | Blocker became evidence-based, not speculative. | Strict "fail honestly" gate discipline. | 5 |
| 2 | Acceptance policy hardening | Prevent production promotion from weak evidence. | `beats_baseline` and partial-scene wins were insufficient. | Locked floors: precision, recall, F1, false-positive rate, and all scenes. | Separates shadow evidence from production claim. | 5 |
| 3 | Error diagnostics | Understand where SAR failed. | Aggregate metrics hid scene/component burden. | Scene and component diagnostics generated. | Failure decomposition into FP/FN burden. | 5 |
| 4 | Component review summary | Turn diagnostics into manual-review actions. | Raw component rows were not decision-ready. | Review summaries/actions created. | Connected-component review instead of vague label debate. | 5 |
| 5 | Manual label-review workflow | Make label/data review auditable. | "Manual review pending" was too loose. | Packet, worksheet, resolver, and outcome states added. | Closed-choice adjudication schema. | 5 |
| 6 | v5 manual-review checkpoint | Decide whether retraining was justified. | GPU retries were not scientifically justified. | Next step narrowed to label/component review. | Prevented blind retraining. | 5 |
| 7 | Phase 0-7 program map | Reconcile two seven-phase plans. | Status drift across a long workstream. | Phase statuses mapped and guarded. | Phase-gated research program narrative. | 5 |
| 8 | Non-GPU feasibility audit | Prove whether existing masks could pass. | Targeted thresholds did not generalize across all scenes. | No all-seven-scene pass found. | Saves GPU by exhausting evaluation-only path. | 5 |
| 9 | Bounded GPU authorization | Allow exactly one justified candidate. | GPU use risked becoming open-ended. | One bounded candidate request pattern established. | Cost/time guarded Modal execution. | 5 |
| 10 | AvalCD first gate | Prevent SnowSlide overfitting first. | Needed source-benchmark gate before heldout. | v6/v7/v8 AvalCD scene-blended gates exercised. | Gate order: benchmark first, heldout second. | 5 |
| 11 | SnowSlide qualification | Test cross-domain research-grade acceptance. | AvalCD success did not transfer cleanly. | v8 improved but still failed precision/F1. | Shows domain-transfer gap, not code optimism. | 4 |
| 12 | Fresh final holdout guard | Avoid contaminated final claims. | SnowSlide influenced model selection. | Fresh final holdout blocked until SnowSlide passes. | Correct final-evidence hygiene. | 5 |
| 13 | Phase 7 readiness guard | Prevent promotion from partial evidence. | Phase 7 could be confused with client readiness. | `phase7_ready=false` preserved. | Product integration blocked by evidence. | 5 |
| 14 | SOTA checkpoint path | Check if public checkpoint could avoid training. | No reviewed compatible direct checkpoint found. | Recorded as unavailable unless evidence appears. | Avoided invented SOTA artifact. | 4 |
| 15 | Float32 mask bug closure | Explain v7 zero-positive SnowSlide result. | `uint8` probability masks capped below threshold. | Float32 path added and requalified. | Independent audit found real serialization issue. | 5 |
| 16 | v8 candidate execution | Try calibrated transfer candidate. | v8 improved recall/FPR but not precision/F1. | v8 result became corrected metric failure. | Stronger diagnosis after bug fix. | 4 |
| 17 | Per-scene v8 story | Avoid misleading aggregate-only story. | Aggregate "v8 failed" hid local success. | Per-scene table shows 1 pass, 3 near-pass, 2 severe failures. | Localized failure narrative. | 5 |
| 18 | Client closeout pack v2 | Separate presentation readiness from production readiness. | Readiness semantics were conflated. | `client_presentation_ready` split from `sar_production_ready`. | Governance-grade briefing gate. | 5 |
| 19 | Client docs pack | Prepare safe presentation narrative. | Evidence was spread across artifacts. | Status brief, FAQ, talk track, fresh-final design, and handoff exist. | Presentation-safe source of truth. | 5 |
| 20 | Reviewer assignment | Remove presentation blocker. | Manual review owner was unassigned. | Sanjay B. authorization and Dr. AK___ owner/date recorded. | Human governance now explicit. | 4 |

## Table 2. Co-Working Areas Needing Scientist Confirmation

| # | Co-working area | Confirmation needed from scientists | Checklist detail | Current status | Rating /5 |
|---:|---|---|---|---|---:|
| 1 | 30-component review | Are top FP/FN components label, model, terrain, or registration issues? | Fill every row in `manual_label_review_decisions.csv`. | Pending with Dr. AK___. | 2 |
| 2 | Pamir failure | Is `pish_20230221` terrain/domain shift or labeling mismatch? | Review FP clusters, terrain/shadow/layover, and source label quality. | Severe scene failure. | 2 |
| 3 | Livigno 20250318 failure | Why does this Livigno date collapse while other Livigno scenes near-pass? | Check snow state, wet-snow artifacts, registration, and acquisition differences. | Severe scene failure. | 2 |
| 4 | Tromso success | Is Tromso's strong pass representative or scene-specific? | Confirm labels and SAR conditions are comparable. | Strong pass. | 4 |
| 5 | Nuuk recall gap | Are missed Nuuk truth components valid avalanches? | Review FN components and underlabeling risk. | Mixed / below. | 3 |
| 6 | Italian Alps variability | Why do Livigno dates vary so widely? | Compare season, date, weather, and terrain context. | Needs domain review. | 3 |
| 7 | Greenland coverage | Are two Nuuk scenes enough for regional interpretation? | Confirm if region label should be broad or site-specific. | Limited evidence. | 3 |
| 8 | Pamir coverage | Is one Pamir scene enough to diagnose model gap? | Decide whether more Pamir-like reference data is required. | Too thin. | 2 |
| 9 | Precision floor | Is `>=0.70` operationally/scientifically justified? | Confirm false-alarm tolerance for research-grade SAR. | Locked but confirmable. | 4 |
| 10 | F1 floor | Is `>=0.60` suitable for client narrative? | Confirm balance between recall and precision. | Locked but confirmable. | 4 |
| 11 | FPR ceiling | Does `<=0.002` match expected map-scale burden? | Translate FPR to false-positive area/user load. | Needs interpretation. | 3 |
| 12 | Fresh final holdout | What scenes can be independent from SnowSlide-guided tuning? | Define source, dates, leakage checks, and labels. | Design-only. | 2 |
| 13 | Label-noise policy | When should label remediation supersede retraining? | Define threshold for underlabeling/source correction. | Pending manual review. | 2 |
| 14 | Terrain ambiguity | Which cases should be `terrain_context_required`? | Require slope/aspect/shadow/layover review criteria. | Pending. | 2 |
| 15 | Registration risk | Are bbox/geo refs sufficiently aligned for adjudication? | Spot-check component overlays. | Pending. | 3 |
| 16 | v9 design | If labels valid, what model-side changes are justified? | Hard negatives, calibration, and domain augmentation. | Not authorized yet. | 2 |
| 17 | UI scientific wording | How should shadow-only SAR be shown to users? | Avoid "production-ready" or "certified" language. | Guarded in docs. | 4 |
| 18 | License display | What imagery/metrics can be shown externally? | Confirm presentation/deployment/imagery-share rights. | Conservative matrix exists. | 3 |
| 19 | Client claims | Which claims are acceptable in the room? | Use do-not-say list and artifact-backed metrics only. | Strong doc guard. | 4 |
| 20 | Degree of success | How should mission success be graded scientifically? | Separate implementation complete from research-grade blocked. | Ready for scientist judgment. | 4 |

## Table 3. Top 10 Remaining Gaps And Practical Next Targets

| Priority | Gap | Why it matters | Next target | Action | Owner | Current rating /5 |
|---:|---|---|---|---|---|---:|
| 1 | Manual component decisions incomplete | Scientific closure cannot be inferred by Codex. | Complete 30-row worksheet. | Dr. AK___ reviews packet and fills closed-choice fields. | Dr. AK___ | 2 |
| 2 | Resolver outcome not produced post-review | Current state remains review-pending. | Generate official manual-review outcome. | Run `resolve_snowslide_manual_label_review` after worksheet completion. | Codex/operator | 2 |
| 3 | Severe Pamir/Livigno scene causes unresolved | These scenes drive aggregate failure. | Scene-specific diagnosis. | Create scene notes from review outcomes. | Scientist + Codex | 2 |
| 4 | v9 not yet justified | Another GPU run needs evidence. | No-launch v9 design only if labels are valid. | Build v9 design after resolver says model-side gap. | Codex | 2 |
| 5 | Fresh final holdout not available | Required before any Phase 7 readiness. | Design independent final set. | Keep design-only until SnowSlide passes. | Scientist + operator | 2 |
| 6 | License review IDs incomplete | External client imagery claims need clearance. | Source-specific clearance log. | Add review IDs for non-AvalCD sources before external sharing. | Legal/source owner | 3 |
| 7 | Regional metrics limited | Region claims are currently thin. | Region-aware evaluation artifact. | Add clean per-region metrics only when evaluator supports it. | Codex | 3 |
| 8 | UI lacks SAR qualification workspace | Client/scientist review is doc-heavy. | Evidence-review UI concept. | Add shadow-only review route after docs stabilize. | Product/dev | 2 |
| 9 | Branch ahead of origin | Collaboration may miss latest closeout docs. | Push current commit if collaboration requires it. | `git push origin feature/european-data-shadow-pipeline`. | Operator | 4 |
| 10 | Modal cost attestation is point-in-time | Governance may ask for cost proof. | 7-day attestation process. | Follow documented rubric; no cron needed now. | Operator | 3 |

### Top 5 Practical Next Targets

| Rank | Target | Why this is feasible now | Done criteria | Impact |
|---:|---|---|---|---|
| 1 | Complete Dr. AK___ manual review | Inputs and worksheet already exist. | All 30 rows reviewed; resolver emits final outcome. | Converts blocker from pending to classified. |
| 2 | Produce scene-specific closeout notes | Diagnostics already identify top scenes. | Pamir/Livigno/Nuuk notes linked to decisions. | Gives client a precise next-step story. |
| 3 | Prepare v9 design only if labels valid | v8 failure modes are known. | No-launch candidate design with one-run guard. | Avoids blind GPU work. |
| 4 | Strengthen review visualization | Component bbox/geo data exists. | Static or UI review overlays for components. | Speeds scientist adjudication. |
| 5 | Define fresh final holdout candidates | Design doc exists. | Candidate independent scenes listed, no materialization. | Prepares future Phase 6 without leakage. |

## Table 4. Top 10 UI Features Not Yet Added

| # | UI feature to add | Current gap | Why it helps | Suggested first version | Priority /5 |
|---:|---|---|---|---|---:|
| 1 | SAR qualification dashboard | SAR evidence is mostly in docs/artifacts. | Makes AvalCD/SnowSlide gate status visible. | Admin-only shadow SAR tab with gates and metrics. | 5 |
| 2 | Manual component review workspace | Review currently happens in CSV/Markdown. | Reduces reviewer friction and errors. | Component table with bbox, centroid, and decision fields. | 5 |
| 3 | Per-scene SnowSlide metric view | Localized failures are the headline but not UI-visible. | Shows Tromso pass vs Pamir/Livigno failures. | Bar/table by scene with precision, recall, F1, and FPR. | 5 |
| 4 | SAR mask overlay comparison | Scientists need visual FP/FN adjudication. | Connects metrics to spatial evidence. | Truth/prediction/probability overlay toggles. | 5 |
| 5 | Region evidence panel | Coverage varies by region. | Prevents overclaiming regional generalization. | Region counts plus region metrics pending/available. | 4 |
| 6 | Presentation-readiness badge | Client-ready and production-ready are separate. | Prevents accidental claim drift. | Two badges: client presentation vs SAR production. | 5 |
| 7 | Fresh-final holdout tracker | Final holdout is blocked but important. | Shows what remains before promotion. | Checklist with leakage/source/scene criteria. | 4 |
| 8 | License/provenance panel | Client sharing depends on rights. | Keeps evidence legally scoped. | Source, license, presentation/deployment/share status. | 4 |
| 9 | Statistical fragility panel | n=7 SnowSlide is thin. | Communicates uncertainty honestly. | Mean/std/CI note and per-scene variance. | 4 |
| 10 | Reviewer SLA/status widget | Review owner/date now exists. | Makes manual-review progress operational. | Owner, target date, pending/reviewed count, and blocker state. | 4 |

## Decision Summary

The mission has achieved a strong implementation and governance closeout for a shadow-only client briefing. The most important bottlenecks crossed were strict acceptance gates, non-GPU recovery proof, bounded GPU candidate discipline, the float32 probability-mask bug fix, v8 corrected evaluation, localized per-scene failure diagnosis, and the split between client-presentation readiness and SAR production readiness.

The mission is not scientifically complete as a production SAR capability. The remaining hard blocker is the manual/domain review of 30 v8 components, assigned to Dr. AK___ with target date `2026-05-27`. After that, the valid branch is label remediation, terrain-context escalation, or a no-launch v9 candidate-design review if labels are valid and the failure is model-side.

## Presentation-Safe One-Liner

The European shadow SAR lane is implemented, evidence-rich, and client-briefing ready as a shadow-only research program, but SAR production scoring remains blocked until SnowSlide research-grade and a later independent fresh final holdout pass.
