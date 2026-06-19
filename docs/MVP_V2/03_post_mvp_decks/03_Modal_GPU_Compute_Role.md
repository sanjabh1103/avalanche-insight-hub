# Post-MVP Addendum 3: Modal.com GPU Compute Role

Status date: 2026-05-21

This is a post-MVP addendum source. It explains Modal.com as off-path compute for validation and candidate-model workflows.

## Purpose

Clarify how Modal.com and GPUs fit into the scientist co-working model without implying that GPU models drive the live public forecast.

## Current Role

| Worker path | Current use | Public prediction impact |
|---|---|---|
| `/sar-segment` | SAR segmentation and held-out prediction masks. | Indirect shadow evidence only. |
| `/train-sar-unet` | SAR U-Net candidate training. | No public scoring change. |
| `/train-mtslstm` | Candidate sequence-model training. | Candidate evidence only. |
| `/infer-mtslstm` | Modal-backed batch inference, currently CPU/memory-sized. | Not the active public scorer. |
| `/evaluate-release` | Held-out release evaluation, forced dry-run in worker path. | Gate evidence only. |
| Modal volumes | DEM, model, checkpoint, and artifact persistence. | Reproducibility support. |

## Current Frequency

Modal is not a continuous public-serving backend. It is invoked by operator workflows, GitHub Actions dispatch, shadow regression, model training, SAR qualification, and release evaluation.

## Scientist Co-Working Lifecycle

1. Scientist reviews cases and daily verification rows.
2. The action ledger opens model, data, label, or benchmark tasks.
3. Modal runs candidate training, SAR segmentation, or release evaluation off the user path.
4. Outputs return as shadow evidence and artifacts.
5. Scientists review deltas, failures, and claim impacts.
6. Only explicit promotion gates can change public claims or scoring.

## Safe Summary Line

Modal.com is the off-path compute backbone for candidate-model and SAR validation work. The active public forecast remains governed by the current promoted baseline until candidate paths earn promotion through scientist review and benchmark gates.
