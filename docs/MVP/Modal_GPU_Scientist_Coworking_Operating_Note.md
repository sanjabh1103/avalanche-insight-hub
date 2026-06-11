# Modal.com GPU Scientist Co-Working Operating Note

Status date: 2026-05-21

## Role

Modal.com is the off-path compute plane for heavy validation and candidate-model jobs. It is not the active public forecast engine and must not be described as already driving public predictions.

## Current Worker Surface

| Endpoint | Purpose | Compute posture | Promotion boundary |
|---|---|---|---|
| `/sar-segment` | SAR segmentation and held-out prediction masks | GPU-backed `T4` path when deployed with CUDA | Shadow evidence only unless release gates pass. |
| `/train-sar-unet` | SAR U-Net candidate training | GPU-backed `T4` training | Candidate checkpoint only. |
| `/train-mtslstm` | MTS-LSTM candidate training | GPU-backed `T4` training | Candidate evidence only. |
| `/infer-mtslstm` | Batch inference from candidate artifacts | Modal-backed CPU/memory-sized path today | Not the active public scorer. |
| `/evaluate-release` | Held-out release evaluation | Modal worker evaluation path | Gate evidence only; worker forces dry-run semantics for release evaluation. |

## When Modal Is Used

Modal is used when the task is too heavy or too environment-specific for the public app or normal CI runner:

- SAR segmentation
- SAR U-Net training
- MTS-LSTM candidate training
- release evaluation
- reproducible artifact reruns
- DEM/model/checkpoint volume access

Modal is not used for continuous public route serving in the current architecture.

## Scientist Co-Working Lifecycle

1. Scientist reviews a validation case or paired daily verification row.
2. The review creates governed action rows when evidence, labels, or models need follow-up.
3. Operators run Modal jobs only for scoped candidate training, SAR segmentation, or evaluation tasks.
4. Modal outputs return as artifacts, metrics, masks, or candidate manifests.
5. Scientists review whether the new evidence resolves the original action.
6. Promotion remains blocked unless the relevant benchmark, scientist, and release gates pass.

## Claim Boundaries

Do say:

- Modal.com supports off-path validation compute.
- Modal.com makes SAR and candidate-model experiments reproducible.
- GPU jobs can improve the evidence base before scientist review.

Do not say:

- Modal GPU drives the public forecast.
- European SAR evidence proves Himalayan accuracy.
- SAR or MTS-LSTM is promoted because a Modal run completed.
- Release evaluation alone authorizes production scoring.

## Best-Practice Fit

This posture matches the scientist co-working model: models act as decision support and second-opinion systems, while scientists remain the benchmark authority. Modal provides scalable compute for experiments and evidence generation, not autonomous operational approval.
