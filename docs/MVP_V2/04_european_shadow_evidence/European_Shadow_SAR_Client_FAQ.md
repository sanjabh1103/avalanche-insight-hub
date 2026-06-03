# European Shadow SAR Client FAQ

## 1. Is the SAR model production-ready?

No. v8 is a shadow candidate. It passed AvalCD scene-blended precision and recall floors, but it failed SnowSlide research-grade aggregate precision and F1 floors. Public production scoring remains unchanged.

## 2. Why is SnowSlide stricter than AvalCD?

AvalCD is the first SAR model-development gate. SnowSlide is a held-out qualification gate, so its floors are stricter: precision `>=0.70`, recall `>=0.50`, F1 `>=0.60`, and false-positive rate `<=0.002`.

## 3. Why does v8 fail if it has useful signal?

The failure is scene-localized, not uniform. `tromso_20241220` passes research-grade floors alone, and several scenes are near-pass. `pish_20230221` and `livigno_20250318` are severe failures and pull aggregate precision/F1 below acceptance.

## 4. What does the 30-component manual review decide?

It adjudicates whether dominant false positives and false negatives are label/data issues, valid model misses, terrain/SAR ambiguity, registration issues, or exclusions pending source review. That outcome determines whether the next step is label remediation, terrain-context review, or a no-launch v9 candidate design.

Dr. AK___ owns this 30-component review, with target completion date `2026-05-27`. Until those rows are reviewed, scientific closure remains pending even though the shadow-only client briefing has been authorized by Sanjay B.

## 5. Can we run v9 now?

No. v9 requires completed manual review or an explicit waiver plus a separate bounded one-run authorization artifact. The current closeout does not authorize GPU work.

## 6. Why only seven SnowSlide scenes?

SnowSlide currently functions as a compact held-out qualification set, not a final statistical benchmark. The small scene count is why the brief discloses statistical fragility and requires a fresh final holdout before production discussion.

## 7. What is the fresh final holdout?

It is a future independent reference set that must not be the SnowSlide qualification set and must not have guided candidate or threshold selection. It is design-only for now and should not be materialized until SnowSlide research-grade first passes.

## 8. What changed after the independent adversarial audit?

The audit identified that uint8 probability-mask storage made high thresholds unreachable. The repo now supports float32 probability masks, and v8 evidence is based on corrected float32 SnowSlide masks.

## 9. Can we show scene imagery externally?

Not by default. The license matrix distinguishes presentation summary, commercial deployment, and external imagery sharing. Per-scene imagery sharing needs source-specific license review.

## 10. What can be said safely in a client meeting?

Safe framing: the European shadow/SAR lane is implemented, validated as a shadow workflow, and has localized failure modes under review. Unsafe framing: SAR is production-ready, research-grade accepted, or guaranteed to pass v9.

## 11. Does the Sanjay B. authorization make SAR client-ready or production-ready?

It makes the material eligible for a shadow-only briefing when presented with the documented constraints. It does not make SAR production-ready, does not close the SnowSlide research-grade gap, does not authorize v9 GPU work, and does not authorize a fresh-final evaluation.
