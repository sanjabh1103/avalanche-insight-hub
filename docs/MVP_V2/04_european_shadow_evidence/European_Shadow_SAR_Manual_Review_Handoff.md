# European Shadow SAR Manual Review Handoff

This handoff is for Dr. AK___ to complete the SnowSlide v8 component review by `2026-05-27`. It is a domain adjudication task, not a model-training authorization.

## Scope

Review the 30 highest-burden SnowSlide v8 components already selected from the diagnostics packet. The goal is to decide whether the remaining blocker is label/source quality, valid model error, terrain/SAR ambiguity, or unresolved source context.

Do not change production scoring, launch GPU training, or promote SAR from this review.

## Inputs

| Artifact | Purpose |
|---|---|
| `backend/artifacts/european-shadow-qualification/snowslide-research-grade-v8-2026-05-19/diagnostics/manual_label_review_packet.md` | Human-readable review packet with scene/component context. |
| `backend/artifacts/european-shadow-qualification/snowslide-research-grade-v8-2026-05-19/diagnostics/manual_label_review_decisions.csv` | Worksheet to complete. |
| `backend/artifacts/european-shadow-qualification/snowslide-research-grade-v8-2026-05-19/diagnostics/component_review_table.csv` | Component bbox, centroid, geo bbox, type, and rank. |
| `backend/artifacts/european-shadow-qualification/snowslide-research-grade-v8-2026-05-19/diagnostics/sar_error_diagnostics.md` | Per-scene TP/FP/FN/TN and error-burden context. |

## Required Worksheet Fields

For each row in `manual_label_review_decisions.csv`, set:

| Field | Required value |
|---|---|
| `review_status` | `reviewed` |
| `component_decision` | One allowed component decision from the worksheet. |
| `requires_label_edit` | `true` or `false` |
| `scene_decision` | One allowed scene decision from the worksheet. |
| `reviewer_notes` | Non-empty reason for the decision. |

Leave geometry, bbox, centroid, component rank, and action IDs unchanged.

## Allowed Component Decisions

| Decision | Meaning |
|---|---|
| `truth_missing_or_underlabeled` | Prediction appears plausible and truth/reference may be incomplete. |
| `valid_model_miss` | Truth appears valid and the model missed it. |
| `prediction_false_alarm` | Prediction appears invalid under the reviewed reference. |
| `terrain_or_sar_ambiguity` | Component needs terrain/SAR context before model-vs-label attribution. |
| `registration_or_projection_issue` | Spatial alignment or projection may explain the mismatch. |
| `exclude_pending_source_review` | Component should be excluded until source/reference review is complete. |

## Allowed Scene Decisions

| Decision | When to use |
|---|---|
| `label_remediation_required` | Any reviewed component requires label/source edit or source exclusion. |
| `labels_valid_model_gap` | Labels are accepted and remaining error is model-side. |
| `terrain_context_required` | Terrain/SAR ambiguity prevents a clean label-vs-model decision. |
| `review_incomplete` | Use only while rows are still pending. |

## Resolver Command

After all 30 rows are reviewed, run:

```bash
python3 -m backend.scripts.resolve_snowslide_manual_label_review \
  --manual-label-review-decisions backend/artifacts/european-shadow-qualification/snowslide-research-grade-v8-2026-05-19/diagnostics/manual_label_review_decisions.csv \
  --manual-label-review-packet backend/artifacts/european-shadow-qualification/snowslide-research-grade-v8-2026-05-19/diagnostics/manual_label_review_packet.json \
  --output-root backend/artifacts/european-shadow-qualification/snowslide-research-grade-v8-2026-05-19/diagnostics
```

If any row is still pending, the resolver returns `review_incomplete` and exits with code `2`. That is expected until the review is complete.

## Outcome Rules

| Outcome | Next step |
|---|---|
| `label_remediation_required` | Prepare label/source remediation. Do not train v9 yet. |
| `labels_valid_model_gap` | Prepare a separate no-launch v9 candidate-design review. GPU still requires explicit one-run authorization. |
| `terrain_context_required` | Add terrain/SAR context review before retraining decisions. |
| `review_incomplete` | Keep SAR lane blocked and finish worksheet review. |

Every outcome keeps `production_scoring_allowed=false`, `promotion_allowed=false`, and `next_gpu_run_authorized=false`.
