# SAR FCN Baseline Evaluation Plan

## Purpose

Create a controlled baseline lane for SAR FCN comparison without promoting SAR outputs to production.

## Inputs

- European shadow SAR staging manifests.
- AvalCD assembled validation scenes where license review permits local evaluation.
- Existing SAR acceptance gates and SnowSlide manual-review packets.

## SnowSlide v8 Manual Review Status

The SnowSlide v8 component-review owner and target date already exist in `docs/superpowers/plans/Euro_plans/European_Shadow_SAR_Manual_Review_Handoff.md`: Dr. AK___ owns the 30-component review with target date `2026-05-27`.

The current blocker is completion and resolution, not assignment. SAR remains blocked until all 30 decision rows are completed and `backend.scripts.resolve_snowslide_manual_label_review` is run against the completed worksheet.

## Required Metrics

| Metric | Purpose |
|---|---|
| Precision / recall / F1 | Mask quality baseline. |
| Component count after postprocess | Avoid tiny-noise promotion. |
| Scene-level coverage | Prevent single-scene overclaim. |
| False-positive review count | Scientist/operator review burden. |
| Held-out split performance | Guard against training leakage. |

## Promotion Boundary

SAR FCN baseline results are shadow evidence only until held-out gates, manual review, and release manifests pass. No public SAR claim or production score change is allowed from this plan alone.
